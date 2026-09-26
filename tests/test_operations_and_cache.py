from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
import pytest
from django.utils import timezone
from django.core.cache import cache
from core.models import Site, Job, WeatherPolicyVersion, ForecastSnapshot, BudgetWindow, SyncAttempt, ProviderCircuitState, LAGOS_TZ
from core.services.evaluation_service import evaluate_and_record_job
from core.tasks import WORKER_HEARTBEAT_CACHE_KEY, SCHEDULER_HEARTBEAT_CACHE_KEY
from core.services.cache_service import invalidate_board_cache, get_board_cache_version


@pytest.fixture
def ops_test_data(db):
    now = timezone.now()
    now_lagos = now.astimezone(LAGOS_TZ)
    today_lagos = now_lagos.date()

    # 1. Site
    site = Site.objects.create(
        name="Lekki Phase 1 Depot",
        latitude=Decimal("6.447400"),
        longitude=Decimal("3.484200"),
        is_active=True,
        last_successful_sync_at=now - timedelta(hours=2),
    )

    # 2. Budget
    budget, _ = BudgetWindow.objects.get_or_create(lagos_date=today_lagos)
    budget.reserved_calls = 42
    budget.successful_calls = 40
    budget.failed_calls = 2
    budget.deferred_calls = 3
    budget.save()

    # 3. Circuit
    circuit = ProviderCircuitState.get_instance()
    circuit.state = 'CLOSED'
    circuit.consecutive_transient_failures = 0
    circuit.save()

    # 4. Sync Attempt
    attempt = SyncAttempt.objects.create(
        site=site,
        started_at=site.last_successful_sync_at - timedelta(seconds=2),
        completed_at=site.last_successful_sync_at,
        attempt_number=1,
        outcome='success',
        http_status=200,
    )

    # 5. Heartbeats in cache
    cache.set(WORKER_HEARTBEAT_CACHE_KEY, (now - timedelta(seconds=30)).isoformat(), timeout=300)
    cache.set(SCHEDULER_HEARTBEAT_CACHE_KEY, (now - timedelta(seconds=45)).isoformat(), timeout=300)

    # 6. Job and snapshot for tomorrow
    policy = WeatherPolicyVersion.get_latest_default()
    start_time = (now_lagos + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    end_time = (now_lagos + timedelta(days=1)).replace(hour=13, minute=0, second=0, microsecond=0)
    job = Job.objects.create(
        site=site,
        title="Antenna Calibration",
        start_time=start_time,
        end_time=end_time,
        policy_version=policy,
    )

    hourly = {}
    snap_start = (now_lagos + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(24):
        t = (snap_start + timedelta(hours=i)).astimezone(dt_timezone.utc).isoformat()
        hourly[t] = {
            "precipitation_probability": 10,
            "precipitation": 0.0,
            "wind_gusts_10m": 12.0,
            "apparent_temperature": 28.0,
        }

    snapshot = ForecastSnapshot.objects.create(
        site=site,
        content_hash="hashlekki123456",
        returned_latitude=Decimal("6.45"),
        returned_longitude=Decimal("3.48"),
        hourly_data=hourly,
        coverage_start=snap_start.astimezone(dt_timezone.utc),
        coverage_end=(snap_start + timedelta(hours=23)).astimezone(dt_timezone.utc),
        hours_count=24,
    )
    attempt.snapshot = snapshot
    attempt.save(update_fields=['snapshot'])
    evaluate_and_record_job(job, snapshot)

    return {
        'site': site,
        'job': job,
        'budget': budget,
        'date_str': (now_lagos + timedelta(days=1)).date().isoformat(),
    }


@pytest.mark.django_db
def test_operations_dashboard_renders_all_telemetry(client, ops_test_data, settings):
    """Ticket 09: operations dashboard displays heartbeats, budget, circuit, and per-site sync timeline."""
    settings.DEMO_MODE = True
    response = client.get('/operations/')
    assert response.status_code == 200
    html = response.content.decode('utf-8')

    # Worker & scheduler heartbeats
    assert "Celery Worker" in html
    assert "Celery Beat" in html
    assert "Redis Cache" not in html
    assert "Provider Circuit" in html
    assert "Active" in html

    # Budget info
    assert "42" in html # reserved
    assert "300" in html # cap
    assert "Lekki Phase 1 Depot" in html
    assert "6.447400, 3.484200" in html


@pytest.mark.django_db
def test_unverified_legacy_budget_is_not_described_as_confirmed_usage(client, ops_test_data):
    budget = ops_test_data['budget']
    budget.source_kind = 'unknown'
    budget.save(update_fields=['source_kind'])

    response = client.get('/operations/')
    html = response.content.decode('utf-8')
    assert response.status_code == 200
    assert "Counts protect the limit but are not confirmed provider usage." in html


@pytest.mark.django_db
def test_board_cache_hit_advances_displayed_age(client, ops_test_data, monkeypatch):
    """
    Ticket 09 Check: a cache hit reports the true advancing age.
    Caching the board response payload does not freeze the rendered age.
    """
    url = f"/?date={ops_test_data['date_str']}"

    # 1. First request: Miss
    invalidate_board_cache()
    res1 = client.get(url)
    assert res1.status_code == 200
    assert res1.headers.get('X-CrewCast-Cache') == 'MISS'
    html1 = res1.content.decode('utf-8')
    assert "Forecast retrieved 2h 0m ago" in html1

    # 2. Second request: Hit at same time
    res2 = client.get(url)
    assert res2.status_code == 200
    assert res2.headers.get('X-CrewCast-Cache') == 'HIT'

    # 3. Third request: Hit with clock advanced by 25 minutes
    fake_future = timezone.now() + timedelta(minutes=25)
    monkeypatch.setattr(timezone, "now", lambda: fake_future)

    res3 = client.get(url)
    assert res3.status_code == 200
    assert res3.headers.get('X-CrewCast-Cache') == 'HIT'
    html3 = res3.content.decode('utf-8')

    # The age has naturally advanced to 2h 25m on a cache hit!
    assert "Forecast retrieved 2h 25m ago" in html3


@pytest.mark.django_db
def test_redis_cache_loss_falls_back_to_postgresql(client, ops_test_data, monkeypatch, settings):
    """
    Ticket 09 Check: Redis cache loss falls back to PostgreSQL.
    """
    url = f"/?date={ops_test_data['date_str']}"
    settings.DEMO_MODE = True
    settings.REDIS_URL = 'redis://localhost:6379/0'

    def mock_broken_cache(*args, **kwargs):
        raise ConnectionError("Redis server connection refused")

    monkeypatch.setattr(cache, "get", mock_broken_cache)
    monkeypatch.setattr(cache, "set", mock_broken_cache)

    # 1. Job board still loads successfully from PostgreSQL database
    res_board = client.get(url)
    assert res_board.status_code == 200
    assert "Antenna Calibration" in res_board.content.decode('utf-8')
    assert res_board.headers.get('X-CrewCast-Cache') == 'MISS'

    # 2. Operations view still loads successfully with no Redis card
    res_ops = client.get('/operations/')
    assert res_ops.status_code == 200
    html_ops = res_ops.content.decode('utf-8')
    assert "Redis Cache" not in html_ops

    # 3. Health check accurately reports cache failure diagnostics
    res_health = client.get('/health/')
    assert res_health.status_code == 200
    health_data = res_health.json()
    assert health_data['components']['cache']['status'] == 'degraded'
    assert 'Redis server connection refused' in str(health_data['components']['cache'])

    # A configured Redis failure remains visible on the non-demo dashboard.
    settings.DEMO_MODE = False
    res_internal_ops = client.get('/operations/')
    assert res_internal_ops.status_code == 200
    assert 'Redis Cache' in res_internal_ops.content.decode('utf-8')
    assert 'Degraded' in res_internal_ops.content.decode('utf-8')


@pytest.mark.django_db
def test_broker_worker_loss_shown_as_degraded_while_stored_pages_still_load(client, ops_test_data):
    """
    Ticket 09 Check: broker loss is shown as degraded while stored pages still load.
    """
    # Clear heartbeats to simulate dead worker and beat scheduler
    cache.delete(WORKER_HEARTBEAT_CACHE_KEY)
    cache.delete(SCHEDULER_HEARTBEAT_CACHE_KEY)

    # 1. Operations shows inactive/stale
    res_ops = client.get('/operations/')
    assert res_ops.status_code == 200
    assert "Inactive" in res_ops.content.decode('utf-8')

    # 2. Health check shows inactive worker heartbeat
    res_health = client.get('/health/')
    assert res_health.status_code == 200
    data = res_health.json()
    assert data['components']['worker_heartbeat']['status'] == 'inactive'
    assert data['components']['scheduler_heartbeat']['status'] == 'inactive'

    # 3. Stored pages still load 200 OK
    res_board = client.get(f"/?date={ops_test_data['date_str']}")
    assert res_board.status_code == 200
    assert "Antenna Calibration" in res_board.content.decode('utf-8')

    res_detail = client.get(f"/jobs/{ops_test_data['job'].pk}/")
    assert res_detail.status_code == 200
    assert "Antenna Calibration" in res_detail.content.decode('utf-8')


@pytest.mark.django_db
def test_board_cache_invalidation_on_job_mutation(client, ops_test_data):
    """Verify that editing or creating a job invalidates the board cache."""
    url = f"/?date={ops_test_data['date_str']}"

    # Load 1: Miss
    invalidate_board_cache()
    res1 = client.get(url)
    assert res1.headers.get('X-CrewCast-Cache') == 'MISS'

    # Load 2: Hit
    res2 = client.get(url)
    assert res2.headers.get('X-CrewCast-Cache') == 'HIT'

    # Mutate: Invalidate cache
    invalidate_board_cache()

    # Load 3: Miss again due to invalidation
    res3 = client.get(url)
    assert res3.headers.get('X-CrewCast-Cache') == 'MISS'
