from decimal import Decimal
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from django.utils import timezone
from core.models import (
    Site,
    BudgetWindow,
    SiteSyncLease,
    ForecastSnapshot,
    SyncAttempt,
    LAGOS_TZ,
)
from core.services.provider import FixtureProvider
from core.services.sync_service import (
    sync_site,
    get_current_lagos_date,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def site_lekki(db):
    return Site.objects.create(
        name="Lekki Phase 1 Depot",
        latitude=Decimal("6.447400"),
        longitude=Decimal("3.472300"),
        is_active=True,
    )


@pytest.mark.django_db(transaction=True)
def test_identical_responses_create_two_attempts_one_snapshot(site_lekki):
    """
    Ticket 05 check: two identical responses create two successful attempts,
    one snapshot, and a newer last-successful-retrieval time.
    """
    provider = FixtureProvider(FIXTURES_DIR / "normal_7day.json")

    # First sync
    t1 = timezone.now() - timedelta(minutes=10)
    res1 = sync_site(site_lekki, provider=provider, force=True, now=t1)
    assert res1.outcome == "success"
    assert ForecastSnapshot.objects.filter(site=site_lekki).count() == 1
    assert SyncAttempt.objects.filter(site=site_lekki).count() == 1

    site_lekki.refresh_from_db()
    first_sync_time = site_lekki.last_successful_sync_at
    assert first_sync_time is not None

    # An older unverified copy of this content becomes trusted only after a
    # fresh provider retrieval confirms it.
    old_snapshot = ForecastSnapshot.objects.get(site=site_lekki)
    old_snapshot.source_kind = 'unknown'
    old_snapshot.save(update_fields=['source_kind'])

    # Second sync with identical fixture payload
    t2 = timezone.now()
    res2 = sync_site(site_lekki, provider=provider, force=True, now=t2)
    assert res2.outcome == "success"
    old_snapshot.refresh_from_db()
    assert old_snapshot.source_kind == 'provider'

    # Invariant checks:
    # 1. Deduplicated snapshot: still only 1 snapshot in database
    assert ForecastSnapshot.objects.filter(site=site_lekki).count() == 1
    # 2. Both attempts link to the same snapshot
    attempts = list(SyncAttempt.objects.filter(site=site_lekki).order_by('started_at'))
    assert len(attempts) == 2
    assert attempts[0].snapshot == attempts[1].snapshot
    # 3. Newer last-successful-retrieval time on the site
    site_lekki.refresh_from_db()
    assert site_lekki.last_successful_sync_at > first_sync_time


@pytest.mark.django_db(transaction=True)
def test_budget_cap_enforcement_and_deferral(site_lekki, settings):
    """
    Ticket 04 check: budget cap is strictly respected and calls above cap
    are recorded as deferred sync attempts.
    """
    settings.DAILY_PROVIDER_BUDGET = 3 # Small cap for testing
    provider = FixtureProvider(FIXTURES_DIR / "normal_7day.json")

    # 3 successful calls consume the budget
    for i in range(3):
        res = sync_site(site_lekki, provider=provider, force=True)
        assert res.outcome == "success"

    # 4th call must be deferred
    res_deferred = sync_site(site_lekki, provider=provider, force=True)
    assert res_deferred.outcome == "deferred"
    assert res_deferred.attempt is not None
    assert res_deferred.attempt.outcome == "deferred"
    assert res_deferred.attempt.failure_category == "budget_exhausted"

    today_lagos = get_current_lagos_date()
    window = BudgetWindow.objects.get(lagos_date=today_lagos)
    assert window.reserved_calls == 3
    assert window.deferred_calls == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_budget_reservation_thread_safety():
    """
    Ticket 04 check: parallel threads attempting to reserve slots under a cap
    strictly never overspend the cap.
    """
    today_lagos = get_current_lagos_date()
    BudgetWindow.objects.get_or_create(lagos_date=today_lagos)
    cap = 8

    def try_reserve(idx):
        from django.db import connection
        try:
            reserved, _ = BudgetWindow.reserve_slot(today_lagos, cap=cap)
            return reserved
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(try_reserve, range(16)))

    successes = sum(1 for r in results if r is True)
    deferrals = sum(1 for r in results if r is False)

    assert successes == cap
    assert deferrals == 16 - cap

    window = BudgetWindow.objects.get(lagos_date=today_lagos)
    assert window.reserved_calls == cap
    assert window.deferred_calls == (16 - cap)


@pytest.mark.django_db(transaction=True)
def test_site_sync_lease_prevents_duplicate_parallel_sync(site_lekki):
    """
    Ticket 04 check: active lease prevents another worker from running
    the same due sync concurrently.
    """
    token = SiteSyncLease.acquire(site_lekki)
    assert token is not None

    # Another worker attempting to acquire fails
    second_token = SiteSyncLease.acquire(site_lekki)
    assert second_token is None

    # Sync attempt returns already_in_progress
    provider = FixtureProvider(FIXTURES_DIR / "normal_7day.json")
    res = sync_site(site_lekki, provider=provider, force=True)
    assert res.outcome == "already_in_progress"

    # Release lease and verify it can now be acquired
    SiteSyncLease.release(site_lekki, token)
    res_after = sync_site(site_lekki, provider=provider, force=True)
    assert res_after.outcome == "success"


@pytest.mark.django_db
def test_site_is_due_interval(site_lekki):
    """Verify that sites are due every 3 hours since last success."""
    now = timezone.now()

    # Never synced -> due
    site_lekki.last_successful_sync_at = None
    assert site_lekki.is_due(now) is True

    # Synced 2 hours ago -> not due
    site_lekki.last_successful_sync_at = now - timedelta(hours=2)
    assert site_lekki.is_due(now) is True  # Timestamp alone is not proof of a provider sync.
    ForecastSnapshot.objects.create(
        site=site_lekki,
        content_hash='verified-sync-for-due-test',
        returned_latitude=site_lekki.latitude,
        returned_longitude=site_lekki.longitude,
        hourly_data={},
        coverage_start=now,
        coverage_end=now,
        hours_count=0,
    )
    SyncAttempt.objects.create(
        site=site_lekki,
        planned_at=site_lekki.last_successful_sync_at,
        started_at=site_lekki.last_successful_sync_at,
        completed_at=site_lekki.last_successful_sync_at,
        outcome='success',
        snapshot=ForecastSnapshot.objects.get(site=site_lekki),
    )
    assert site_lekki.is_due(now) is False

    # Synced 3 hours 1 second ago -> due
    site_lekki.last_successful_sync_at = now - timedelta(hours=3, seconds=1)
    assert site_lekki.is_due(now) is True
