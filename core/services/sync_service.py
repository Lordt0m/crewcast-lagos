import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from django.db import transaction, IntegrityError
from core.models import (
    Site,
    BudgetWindow,
    SiteSyncLease,
    ForecastSnapshot,
    SyncAttempt,
    ProviderCircuitState,
    LAGOS_TZ,
    DUE_INTERVAL_HOURS,
)
from core.services.provider import (
    ForecastProvider,
    OpenMeteoProvider,
    TransientProviderError,
    PermanentProviderError,
)
from core.services.normalizer import normalize_forecast_payload
from core.services.retry_policy import calculate_retry_delay, MAX_SYNC_ATTEMPTS

logger = logging.getLogger(__name__)


class SyncResult:
    def __init__(self, outcome: str, attempt: SyncAttempt | None = None, snapshot: ForecastSnapshot | None = None, reason: str = ""):
        self.outcome = outcome
        self.attempt = attempt
        self.snapshot = snapshot
        self.reason = reason

    def __repr__(self):
        return f"<SyncResult outcome={self.outcome} reason={self.reason}>"


def get_current_lagos_date(now: datetime = None):
    if now is None:
        now = timezone.now()
    return now.astimezone(LAGOS_TZ).date()


@dataclass(frozen=True)
class SyncPlan:
    planned_at: datetime
    attempt_number: int


def due_sync_plan(site: Site, now: datetime) -> SyncPlan | None:
    """Respect retry deadlines, daily budget deferrals, and exhausted cycles."""
    if not site.is_due(now):
        return None

    latest = SyncAttempt.objects.filter(site=site, source_kind='worker').order_by('-pk').first()
    if latest and latest.outcome == 'deferred':
        if (latest.failure_category == 'budget_exhausted'
                and get_current_lagos_date(latest.started_at) == get_current_lagos_date(now)):
            return None
        if latest.next_retry_at and now < latest.next_retry_at:
            return None
        if latest.failure_category == 'budget_exhausted':
            return SyncPlan(planned_at=now, attempt_number=1)
        latest = (
            SyncAttempt.objects.filter(site=site, source_kind='worker')
            .exclude(outcome='deferred').order_by('-pk').first()
        )

    if latest and latest.outcome == 'transient_failure':
        if latest.attempt_number < MAX_SYNC_ATTEMPTS and latest.next_retry_at:
            if now < latest.next_retry_at:
                return None
            return SyncPlan(planned_at=latest.planned_at, attempt_number=latest.attempt_number + 1)

    if latest and latest.outcome in ('transient_failure', 'permanent_failure'):
        last_finished = latest.completed_at or latest.started_at
        if now < last_finished + timedelta(hours=DUE_INTERVAL_HOURS):
            return None

    return SyncPlan(planned_at=now, attempt_number=1)


def sync_site(
    site: Site,
    provider: ForecastProvider = None,
    planned_at: datetime = None,
    force: bool = False,
    now: datetime = None,
    attempt_number: int = 1,
) -> SyncResult:
    """
    Executes a synchronized forecast retrieval for a single site with:
    1. Active & due validation.
    2. Circuit breaker check (defers call if circuit is OPEN).
    3. Site lease claim.
    4. Atomic budget reservation (capped at 300/day).
    5. Provider fetch, error classification, and backoff next_retry calculation.
    6. Snapshot deduplication and job re-evaluation.
    7. Circuit state update (record_success / record_transient_failure).
    """
    if now is None:
        now = timezone.now()
    if planned_at is None:
        planned_at = now

    if not site.is_active:
        return SyncResult(outcome="skipped", reason="Site is inactive")

    if not force:
        plan = due_sync_plan(site, now)
        if plan is None:
            return SyncResult(outcome="skipped", reason="Site is not due or is waiting for its retry deadline")
        planned_at = plan.planned_at
        attempt_number = plan.attempt_number

    # 1. Circuit breaker check
    can_attempt, circuit_reason = ProviderCircuitState.can_attempt(now=now)
    if not can_attempt:
        logger.warning(f"Provider circuit prevents outbound fetch: {circuit_reason}")
        circuit = ProviderCircuitState.objects.filter(id=1).first()
        next_retry = now + timedelta(minutes=5)
        if circuit and circuit.state == 'OPEN' and circuit.opened_at:
            cooloff_end = circuit.opened_at + timedelta(seconds=circuit.cooloff_seconds)
            next_retry = max(next_retry, cooloff_end)
        attempt = SyncAttempt.objects.create(
            site=site,
            planned_at=planned_at,
            started_at=now,
            completed_at=now,
            attempt_number=attempt_number,
            outcome="deferred",
            failure_category="circuit_open",
            error_message=f"Provider circuit breaker is {circuit_reason}",
            next_retry_at=next_retry,
        )
        return SyncResult(outcome="deferred", attempt=attempt, reason=f"Circuit open: {circuit_reason}")

    # 2. Acquire exclusive site lease
    lease_token = SiteSyncLease.acquire(site)
    if not lease_token:
        logger.info(f"Sync lease already held for site {site.name}")
        return SyncResult(outcome="already_in_progress", reason="Active lease held by another worker")

    try:
        lagos_date = get_current_lagos_date(now)
        daily_cap = getattr(settings, 'DAILY_PROVIDER_BUDGET', 300)

        # 3. Reserve budget slot
        reserved, budget_window = BudgetWindow.reserve_slot(lagos_date, cap=daily_cap)
        if not reserved:
            logger.warning(f"Daily provider budget ({daily_cap}) exhausted for date {lagos_date}")
            attempt = SyncAttempt.objects.create(
                site=site,
                planned_at=planned_at,
                started_at=now,
                completed_at=now,
                attempt_number=attempt_number,
                outcome="deferred",
                failure_category="budget_exhausted",
                error_message=f"Daily provider budget of {daily_cap} calls exhausted.",
            )
            return SyncResult(outcome="deferred", attempt=attempt, reason="Daily budget exhausted")

        # 4. Outbound provider fetch
        if provider is None:
            provider = OpenMeteoProvider()

        started_at = timezone.now()
        try:
            raw_payload = provider.fetch(float(site.latitude), float(site.longitude), now=now)
            norm = normalize_forecast_payload(raw_payload)

            completed_at = timezone.now()

            with transaction.atomic():
                snapshot, created = ForecastSnapshot.objects.get_or_create(
                    site=site,
                    content_hash=norm.content_hash,
                    defaults={
                        'source_kind': 'provider',
                        'returned_latitude': norm.returned_latitude,
                        'returned_longitude': norm.returned_longitude,
                        'returned_elevation': norm.returned_elevation,
                        'hourly_data': norm.hourly_data,
                        'coverage_start': norm.coverage_start,
                        'coverage_end': norm.coverage_end,
                        'hours_count': norm.hours_count,
                    }
                )

                # A genuine retrieval can verify content retained from an older
                # installation where snapshot origin was not recorded.
                if snapshot.source_kind != 'provider':
                    snapshot.source_kind = 'provider'
                    snapshot.save(update_fields=['source_kind'])

                attempt = SyncAttempt.objects.create(
                    site=site,
                    planned_at=planned_at,
                    started_at=started_at,
                    completed_at=completed_at,
                    attempt_number=attempt_number,
                    outcome="success",
                    snapshot=snapshot,
                )

                site.last_successful_sync_at = completed_at
                site.save(update_fields=['last_successful_sync_at'])

                BudgetWindow.record_outcome(lagos_date, success=True)
                ProviderCircuitState.record_success()

            from .evaluation_service import evaluate_all_jobs_for_site
            from .cache_service import invalidate_board_cache
            # The active content version changed at commit. Do not serve a
            # cached recommendation for the previous version while evaluation runs.
            invalidate_board_cache()
            evaluate_all_jobs_for_site(site, snapshot)

            invalidate_board_cache()

            logger.info(f"Sync succeeded for site '{site.name}'. Snapshot created={created}, hash={norm.content_hash[:8]}")
            return SyncResult(outcome="success", attempt=attempt, snapshot=snapshot)

        except TransientProviderError as exc:
            completed_at = timezone.now()
            delay_sec = calculate_retry_delay(attempt_number, retry_after=exc.retry_after)
            next_retry = completed_at + timedelta(seconds=delay_sec) if attempt_number < MAX_SYNC_ATTEMPTS else None

            attempt = SyncAttempt.objects.create(
                site=site,
                planned_at=planned_at,
                started_at=started_at,
                completed_at=completed_at,
                attempt_number=attempt_number,
                outcome="transient_failure",
                failure_category="transient_provider_error",
                http_status=exc.status_code,
                error_message=str(exc),
                next_retry_at=next_retry,
            )
            BudgetWindow.record_outcome(lagos_date, success=False)
            ProviderCircuitState.record_transient_failure(now=completed_at)
            return SyncResult(outcome="transient_failure", attempt=attempt, reason=str(exc))

        except PermanentProviderError as exc:
            completed_at = timezone.now()
            attempt = SyncAttempt.objects.create(
                site=site,
                planned_at=planned_at,
                started_at=started_at,
                completed_at=completed_at,
                attempt_number=attempt_number,
                outcome="permanent_failure",
                failure_category="permanent_provider_error",
                http_status=exc.status_code,
                error_message=str(exc),
                next_retry_at=None,
            )
            BudgetWindow.record_outcome(lagos_date, success=False)
            return SyncResult(outcome="permanent_failure", attempt=attempt, reason=str(exc))

        except Exception as exc:
            completed_at = timezone.now()
            attempt = SyncAttempt.objects.create(
                site=site,
                planned_at=planned_at,
                started_at=started_at,
                completed_at=completed_at,
                attempt_number=attempt_number,
                outcome="permanent_failure",
                failure_category="unexpected_error",
                error_message=str(exc),
                next_retry_at=None,
            )
            BudgetWindow.record_outcome(lagos_date, success=False)
            return SyncResult(outcome="permanent_failure", attempt=attempt, reason=str(exc))

    finally:
        SiteSyncLease.release(site, lease_token)


def check_and_sync_all_due_sites(provider: ForecastProvider = None, now: datetime = None) -> list[SyncResult]:
    """Synchronize active sites whose normal or retry window is due."""
    if now is None:
        now = timezone.now()

    results = []
    for site in Site.objects.filter(is_active=True):
        res = sync_site(site, provider=provider, now=now)
        if res.outcome != 'skipped':
            results.append(res)
    return results
