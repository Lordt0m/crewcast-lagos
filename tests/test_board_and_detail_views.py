from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
import pytest
from django.utils import timezone
from django.contrib.auth.models import User
from django.test import Client
from core.models import Site, Job, WeatherPolicyVersion, ForecastSnapshot, SyncAttempt, Recommendation, LAGOS_TZ
from core.services.provider import OpenMeteoProvider
from core.services.evaluation_service import evaluate_and_record_job
from core.services.cache_service import invalidate_board_cache


@pytest.fixture
def manager_client(db, settings):
    settings.DEMO_MODE = False
    user = User.objects.create_user(username="lead_dispatcher", password="testpassword123")
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def seeded_data(db):
    invalidate_board_cache()
    site = Site.objects.create(
        name="Victoria Island Office Park",
        latitude=Decimal("6.428100"),
        longitude=Decimal("3.421900"),
        is_active=True,
    )
    policy = WeatherPolicyVersion.get_latest_default()
    now_lagos = timezone.now().astimezone(LAGOS_TZ)

    # Job 1: Tomorrow 09:00 - 12:00
    start1 = (now_lagos + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    end1 = (now_lagos + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    job1 = Job.objects.create(
        site=site,
        title="Rooftop HVAC Servicing",
        start_time=start1,
        end_time=end1,
        policy_version=policy,
    )

    # Create snapshot covering tomorrow
    hourly = {}
    snap_start = (now_lagos + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(24):
        t = (snap_start + timedelta(hours=i)).astimezone(dt_timezone.utc).isoformat()
        hourly[t] = {
            "precipitation_probability": 60, # Caution (caution is 40, stop is 70)
            "precipitation": 1.5,
            "wind_gusts_10m": 18.0,
            "apparent_temperature": 29.0,
        }

    snapshot = ForecastSnapshot.objects.create(
        site=site,
        content_hash="mockhashvi123",
        returned_latitude=Decimal("6.43"),
        returned_longitude=Decimal("3.42"),
        hourly_data=hourly,
        coverage_start=snap_start.astimezone(dt_timezone.utc),
        coverage_end=(snap_start + timedelta(hours=23)).astimezone(dt_timezone.utc),
        hours_count=24,
    )

    # Mark site retrieved 1 hour ago (fresh)
    site.last_successful_sync_at = timezone.now() - timedelta(hours=1)
    site.save()
    SyncAttempt.objects.create(
        site=site,
        planned_at=site.last_successful_sync_at,
        started_at=site.last_successful_sync_at,
        completed_at=site.last_successful_sync_at,
        outcome='success',
        snapshot=snapshot,
    )

    # Evaluate job
    evaluate_and_record_job(job1, snapshot)

    return {
        'site': site,
        'job': job1,
        'snapshot': snapshot,
        'policy': policy,
        'tomorrow_date_str': (now_lagos + timedelta(days=1)).date().isoformat(),
    }


@pytest.mark.django_db
def test_page_load_makes_zero_provider_calls(client, seeded_data, monkeypatch):
    """
    Ticket 08 check: a page load makes no provider call!
    """
    def mock_forbidden_fetch(*args, **kwargs):
        raise AssertionError("OpenMeteoProvider.fetch was invoked during a web page load! Zero live calls are allowed.")

    monkeypatch.setattr(OpenMeteoProvider, "fetch", mock_forbidden_fetch)

    # 1. Job Board
    response_board = client.get(f"/?date={seeded_data['tomorrow_date_str']}")
    assert response_board.status_code == 200

    # 2. Job Detail
    response_detail = client.get(f"/jobs/{seeded_data['job'].pk}/")
    assert response_detail.status_code == 200


@pytest.mark.django_db
def test_job_board_grouped_by_priority(client, seeded_data):
    """Verify jobs are grouped into priority sections on board."""
    url = f"/?date={seeded_data['tomorrow_date_str']}"
    response = client.get(url)
    assert response.status_code == 200
    html = response.content.decode('utf-8')

    # Rooftop HVAC Servicing has caution (prob=60%)
    assert "Rooftop HVAC Servicing" in html
    assert "Caution" in html
    assert "Victoria Island Office Park" in html


@pytest.mark.django_db
def test_public_gets_do_not_create_recommendations(client, seeded_data):
    Recommendation.objects.all().delete()
    assert client.get(f"/?date={seeded_data['tomorrow_date_str']}").status_code == 200
    assert client.get(f"/jobs/{seeded_data['job'].pk}/").status_code == 200
    assert Recommendation.objects.count() == 0


@pytest.mark.django_db
def test_unverified_legacy_forecast_is_not_presented_as_live(client, seeded_data):
    snapshot = seeded_data['snapshot']
    snapshot.source_kind = 'unknown'
    snapshot.save(update_fields=['source_kind'])
    invalidate_board_cache()

    board = client.get(f"/?date={seeded_data['tomorrow_date_str']}")
    detail = client.get(f"/jobs/{seeded_data['job'].pk}/")
    operations = client.get('/operations/')

    assert 'Waiting for first forecast' in board.content.decode('utf-8')
    assert 'No current recommendation' in board.content.decode('utf-8')
    assert 'Waiting for first sync' in detail.content.decode('utf-8')
    assert 'Evaluated conditions during job window' not in detail.content.decode('utf-8')
    assert 'Legacy quota records may also contain demo seed values' in operations.content.decode('utf-8')


@pytest.mark.django_db
def test_current_forecast_follows_latest_retrieval_when_content_returns_a_b_a(client, seeded_data):
    site = seeded_data['site']
    job = seeded_data['job']
    snapshot_a = seeded_data['snapshot']
    safe_hourly = {
        key: {
            'precipitation_probability': 0,
            'precipitation': 0.0,
            'wind_gusts_10m': 10.0,
            'apparent_temperature': 25.0,
        }
        for key in snapshot_a.hourly_data
    }
    snapshot_b = ForecastSnapshot.objects.create(
        site=site,
        content_hash='different-safe-content',
        returned_latitude=snapshot_a.returned_latitude,
        returned_longitude=snapshot_a.returned_longitude,
        hourly_data=safe_hourly,
        coverage_start=snapshot_a.coverage_start,
        coverage_end=snapshot_a.coverage_end,
        hours_count=snapshot_a.hours_count,
    )
    rec_b, _ = evaluate_and_record_job(job, snapshot_b)
    assert rec_b.status == 'suitable'

    retrieved_b_at = timezone.now() - timedelta(minutes=20)
    SyncAttempt.objects.create(
        site=site, planned_at=retrieved_b_at, started_at=retrieved_b_at,
        completed_at=retrieved_b_at, outcome='success', snapshot=snapshot_b,
    )
    invalidate_board_cache()
    board_b = client.get(f"/?date={seeded_data['tomorrow_date_str']}")
    detail_b = client.get(f'/jobs/{job.pk}/')
    assert any(item['job']['pk'] == job.pk for item in board_b.context['suitable_jobs'])
    assert detail_b.context['snapshot'].pk == snapshot_b.pk

    retrieved_a_again_at = timezone.now()
    SyncAttempt.objects.create(
        site=site, planned_at=retrieved_a_again_at, started_at=retrieved_a_again_at,
        completed_at=retrieved_a_again_at, outcome='success', snapshot=snapshot_a,
    )
    site.last_successful_sync_at = retrieved_a_again_at
    site.save(update_fields=['last_successful_sync_at'])
    invalidate_board_cache()

    board_a_again = client.get(f"/?date={seeded_data['tomorrow_date_str']}")
    detail_a_again = client.get(f'/jobs/{job.pk}/')
    assert any(item['job']['pk'] == job.pk for item in board_a_again.context['caution_jobs'])
    assert detail_a_again.context['snapshot'].pk == snapshot_a.pk
    assert detail_a_again.context['current_rec'].snapshot_id == snapshot_a.pk
    assert detail_a_again.context['hourly_evaluations'][0]['prob'] == 60


@pytest.mark.django_db
def test_labels_and_status_do_not_depend_on_color(client, seeded_data):
    """
    Ticket 08 check: labels and status do not depend on color alone;
    verified by textual badge names and embedded SVG icons.
    """
    url = f"/?date={seeded_data['tomorrow_date_str']}"
    response = client.get(url)
    html = response.content.decode('utf-8')

    # Card has SVG icon and distinct text
    assert "<svg" in html
    assert "badge status-caution" in html
    assert "Caution" in html


@pytest.mark.django_db
def test_job_detail_renders_all_reasons_and_history(client, seeded_data):
    """Verify job detail renders timestamps, reasons, and thresholds."""
    job = seeded_data['job']
    response = client.get(f"/jobs/{job.pk}/")
    assert response.status_code == 200
    html = response.content.decode('utf-8')

    assert job.title in html
    assert "Victoria Island Office Park" in html
    assert "Weather policy" in html
    assert "Rain probability" in html
    assert "Planning signal only" in html
    assert "Open-Meteo" in html


@pytest.mark.django_db
def test_empty_board_state_message(client):
    """Verify friendly empty state when no jobs are planned for the day."""
    # Pick date 5 days ahead where no jobs exist
    now_lagos = timezone.now().astimezone(LAGOS_TZ)
    target_date = (now_lagos + timedelta(days=5)).date().isoformat()

    response = client.get(f"/?date={target_date}")
    assert response.status_code == 200
    html = response.content.decode('utf-8')

    assert "No jobs planned for this day" in html
    assert "Add a job to compare its work window with the forecast" in html


@pytest.mark.django_db
def test_manager_flow_navigation(manager_client, seeded_data):
    """Verify complete manager navigation flow: create job -> see on board -> open detail."""
    site = seeded_data['site']
    now_lagos = timezone.now().astimezone(LAGOS_TZ)
    start_str = (now_lagos + timedelta(days=2)).strftime("%Y-%m-%dT10:00")
    end_str = (now_lagos + timedelta(days=2)).strftime("%Y-%m-%dT14:00")

    # 1. Create Job
    post_res = manager_client.post('/jobs/new/', {
        'site': site.pk,
        'title': 'Facade Window Wash',
        'start_time': start_str,
        'end_time': end_str,
    })
    assert post_res.status_code == 302 # Redirects to board

    new_job = Job.objects.get(title='Facade Window Wash')
    assert new_job.site == site

    # 2. View Detail
    detail_res = manager_client.get(f'/jobs/{new_job.pk}/')
    assert detail_res.status_code == 200
    assert 'Facade Window Wash' in detail_res.content.decode('utf-8')
