from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path
import pytest
from django.utils import timezone
from core.models import Site, SyncAttempt, ProviderCircuitState, BudgetWindow
from core.services.provider import ForecastProvider, TransientProviderError, PermanentProviderError, FixtureProvider
from core.services.sync_service import sync_site, check_and_sync_all_due_sites, get_current_lagos_date
from core.services.freshness import get_freshness_state, get_effective_planning_display
from core.services.retry_policy import calculate_retry_delay

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class FailingProvider(ForecastProvider):
    def __init__(self, error_type="transient", status_code=500, retry_after=None):
        self.error_type = error_type
        self.status_code = status_code
        self.retry_after = retry_after
        self.call_count = 0

    def fetch(self, latitude: float, longitude: float, now=None) -> dict:
        self.call_count += 1
        if self.error_type == "transient":
            raise TransientProviderError(f"Transient HTTP {self.status_code}", status_code=self.status_code, retry_after=self.retry_after)
        elif self.error_type == "permanent":
            raise PermanentProviderError(f"Permanent HTTP {self.status_code}", status_code=self.status_code)
        elif self.error_type == "timeout":
            raise TransientProviderError("Connection timed out", status_code=None)
        raise RuntimeError("Unknown error")


@pytest.fixture
def test_site(db):
    return Site.objects.create(
        name="Ikeja Industrial Hub",
        latitude=Decimal("6.600000"),
        longitude=Decimal("3.350000"),
        is_active=True,
    )


@pytest.fixture(autouse=True)
def reset_circuit(db):
    circuit = ProviderCircuitState.get_instance()
    circuit.state = 'CLOSED'
    circuit.consecutive_transient_failures = 0
    circuit.opened_at = None
    circuit.save()


def test_freshness_classification_and_suitable_suppression():
    """Ticket 07: fresh, stale, and expired transitions with suitable suppression."""
    now = timezone.now()

    # 1. Fresh (2 hours old)
    fresh_time = now - timedelta(hours=2)
    state, age = get_freshness_state(fresh_time, now=now)
    assert state == 'fresh'
    disp_fresh = get_effective_planning_display('suitable', state)
    assert disp_fresh['actionable_status'] == 'suitable'
    assert disp_fresh['is_stale'] is False
    assert disp_fresh['is_expired'] is False

    # 2. Stale (6 hours old)
    stale_time = now - timedelta(hours=6)
    state_stale, _ = get_freshness_state(stale_time, now=now)
    assert state_stale == 'stale'

    # Suitable MUST be suppressed when stale
    disp_stale_suitable = get_effective_planning_display('suitable', state_stale)
    assert disp_stale_suitable['actionable_status'] is None # Suppressed!
    assert disp_stale_suitable['is_stale'] is True
    assert disp_stale_suitable['suppressed_suitable'] is True

    # Unsuitable/Caution preserved as historical context when stale
    disp_stale_caution = get_effective_planning_display('caution', state_stale)
    assert disp_stale_caution['actionable_status'] == 'caution'
    assert 'Historical' in disp_stale_caution['display_status']

    # 3. Expired (> 12 hours old)
    expired_time = now - timedelta(hours=14)
    state_expired, _ = get_freshness_state(expired_time, now=now)
    assert state_expired == 'expired'
    disp_expired = get_effective_planning_display('suitable', state_expired)
    assert disp_expired['actionable_status'] is None
    assert disp_expired['is_expired'] is True
    assert disp_expired['display_status'] == 'No current recommendation'


def test_missing_forecast_copy_distinguishes_pending_from_expired():
    pending = get_effective_planning_display(None, 'pending')
    assert pending['actionable_status'] is None
    assert pending['is_expired'] is False
    assert 'first forecast' in pending['banner_message']
    assert 'too old' not in pending['banner_message']

    unavailable = get_effective_planning_display(None, 'fresh')
    assert unavailable['is_expired'] is False
    assert 'No forecast evaluation' in unavailable['banner_message']


@pytest.mark.django_db(transaction=True)
def test_transient_retry_delay_and_budget_inclusion(test_site):
    """Ticket 07: transient failure includes budget reservation and sets next retry."""
    provider = FailingProvider(error_type="transient", status_code=429, retry_after=45)
    now = timezone.now()

    res = sync_site(test_site, provider=provider, now=now, attempt_number=1, force=True)
    assert res.outcome == "transient_failure"
    assert res.attempt is not None
    assert res.attempt.http_status == 429
    assert res.attempt.next_retry_at is not None
    # Next retry should be at least 45s from now (honoring Retry-After)
    assert res.attempt.next_retry_at >= now + timedelta(seconds=45)

    # Budget window must record the reserved attempt
    today_lagos = get_current_lagos_date(now)
    window = BudgetWindow.objects.get(lagos_date=today_lagos)
    assert window.reserved_calls >= 1
    assert window.failed_calls >= 1


@pytest.mark.django_db(transaction=True)
def test_scheduler_waits_for_retry_after_and_increments_attempt(test_site):
    provider = FailingProvider(error_type='transient', status_code=429, retry_after=900)
    first = sync_site(test_site, provider=provider)
    assert first.outcome == 'transient_failure'
    assert first.attempt.attempt_number == 1
    assert first.attempt.next_retry_at >= first.attempt.completed_at + timedelta(seconds=900)

    before_deadline = first.attempt.next_retry_at - timedelta(seconds=1)
    assert check_and_sync_all_due_sites(provider=provider, now=before_deadline) == []
    assert sync_site(test_site, provider=provider, now=before_deadline).outcome == 'skipped'
    assert provider.call_count == 1
    assert SyncAttempt.objects.filter(site=test_site).count() == 1
    assert BudgetWindow.objects.get(lagos_date=get_current_lagos_date()).reserved_calls == 1

    results = check_and_sync_all_due_sites(provider=provider, now=first.attempt.next_retry_at)
    assert len(results) == 1
    assert results[0].outcome == 'transient_failure'
    assert results[0].attempt.attempt_number == 2
    assert results[0].attempt.planned_at == first.attempt.planned_at
    assert provider.call_count == 2


@pytest.mark.django_db(transaction=True)
def test_exhausted_retry_cycle_waits_before_restarting(test_site):
    finished_at = timezone.now() - timedelta(hours=1)
    SyncAttempt.objects.create(
        site=test_site,
        planned_at=finished_at - timedelta(minutes=5),
        started_at=finished_at - timedelta(seconds=1),
        completed_at=finished_at,
        attempt_number=3,
        outcome='transient_failure',
    )
    provider = FailingProvider(error_type='transient')

    assert check_and_sync_all_due_sites(provider=provider, now=finished_at + timedelta(hours=2)) == []
    assert provider.call_count == 0

    results = check_and_sync_all_due_sites(provider=provider, now=finished_at + timedelta(hours=3))
    assert len(results) == 1
    assert results[0].attempt.attempt_number == 1
    assert provider.call_count == 1


@pytest.mark.django_db(transaction=True)
def test_budget_deferral_is_not_repeated_on_every_scheduler_tick(test_site, settings):
    settings.DAILY_PROVIDER_BUDGET = 0
    provider = FailingProvider()
    now = timezone.now()

    first = check_and_sync_all_due_sites(provider=provider, now=now)
    assert len(first) == 1
    assert first[0].attempt.failure_category == 'budget_exhausted'
    assert check_and_sync_all_due_sites(provider=provider, now=now + timedelta(minutes=5)) == []
    assert SyncAttempt.objects.filter(site=test_site).count() == 1
    assert provider.call_count == 0

    next_day = check_and_sync_all_due_sites(provider=provider, now=now + timedelta(days=1))
    assert len(next_day) == 1
    assert next_day[0].attempt.attempt_number == 1
    assert next_day[0].attempt.failure_category == 'budget_exhausted'


@pytest.mark.django_db(transaction=True)
def test_circuit_deferral_waits_for_cooloff(test_site):
    now = timezone.now()
    circuit = ProviderCircuitState.get_instance()
    circuit.state = 'OPEN'
    circuit.opened_at = now
    circuit.cooloff_seconds = 900
    circuit.save(update_fields=['state', 'opened_at', 'cooloff_seconds'])
    provider = FailingProvider()

    first = check_and_sync_all_due_sites(provider=provider, now=now)
    assert len(first) == 1
    assert first[0].attempt.failure_category == 'circuit_open'
    assert first[0].attempt.next_retry_at >= now + timedelta(seconds=900)
    assert check_and_sync_all_due_sites(provider=provider, now=now + timedelta(minutes=5)) == []
    assert SyncAttempt.objects.filter(site=test_site).count() == 1
    assert provider.call_count == 0


def test_retry_after_is_not_capped_by_exponential_backoff_limit():
    assert calculate_retry_delay(1, retry_after=3600) == 3600


@pytest.mark.django_db(transaction=True)
def test_circuit_breaker_trip_and_probe_recovery(test_site):
    """
    Ticket 07: 3 consecutive transient failures trip circuit to OPEN;
    after cooloff, allows 1 HALF_OPEN probe and recovers to CLOSED on success.
    """
    failing_provider = FailingProvider(error_type="transient", status_code=503)
    now = timezone.now()

    # 1. Trigger 3 consecutive transient failures
    for i in range(3):
        res = sync_site(test_site, provider=failing_provider, force=True, now=now + timedelta(seconds=i*10))
        assert res.outcome == "transient_failure"

    circuit = ProviderCircuitState.get_instance()
    assert circuit.state == 'OPEN'
    assert circuit.opened_at is not None

    # 2. While circuit is OPEN, next sync is deferred immediately
    deferred_res = sync_site(test_site, provider=failing_provider, force=True, now=now + timedelta(minutes=5))
    assert deferred_res.outcome == "deferred"
    assert "Circuit open" in deferred_res.reason
    assert failing_provider.call_count == 3 # Provider was NOT called!

    # 3. Fast-forward past 15-minute cooloff and run sync probe
    future_now = now + timedelta(minutes=16)
    good_provider = FixtureProvider(FIXTURES_DIR / "normal_7day.json")
    success_res = sync_site(test_site, provider=good_provider, force=True, now=future_now)
    assert success_res.outcome == "success"

    circuit.refresh_from_db()
    assert circuit.state == 'CLOSED'
    assert circuit.consecutive_transient_failures == 0
