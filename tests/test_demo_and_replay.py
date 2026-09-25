from decimal import Decimal
from datetime import timedelta
import pytest
from django.conf import settings
from django.core.management import call_command
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from core.models import Site, Job, ForecastSnapshot, WeatherPolicyVersion, LAGOS_TZ
from core.services.provider import OpenMeteoProvider


@pytest.fixture
def manager_client(db):
    user = User.objects.create_user(username="dispatcher", password="testpassword123")
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_seed_demo_data_command():
    """Verify that seed_demo_data populates 6 Lagos sites, jobs, and canned snapshots."""
    call_command('seed_demo_data', clear=True)

    # 1. Sites
    sites = Site.objects.filter(is_active=True)
    assert sites.count() == 6
    for s in sites:
        assert Decimal("6.38") <= s.latitude <= Decimal("6.72")
        assert Decimal("3.12") <= s.longitude <= Decimal("3.68")
        assert s.last_successful_sync_at is not None

    # 2. Jobs
    jobs = Job.objects.all()
    assert jobs.count() >= 10
    now_lagos = timezone.now().astimezone(LAGOS_TZ)
    for j in jobs:
        start_lagos = j.start_time.astimezone(LAGOS_TZ)
        assert start_lagos.date() >= now_lagos.date()

    # 3. Snapshots
    assert ForecastSnapshot.objects.count() >= 6

    # 4. User
    assert User.objects.filter(username="dispatcher").exists()


@pytest.mark.django_db
def test_demo_mode_blocks_all_mutations_server_side(manager_client, settings):
    """
    Ticket 10 Check: every public write and force-sync attempt fails
    server-side when DEMO_MODE is True, including for signed-in managers.
    """
    settings.DEMO_MODE = True

    site = Site.objects.create(
        name="Test Depot", latitude=Decimal("6.450000"), longitude=Decimal("3.400000")
    )
    now_lagos = timezone.now().astimezone(LAGOS_TZ)
    start_str = (now_lagos + timedelta(days=1)).strftime("%Y-%m-%dT09:00")
    end_str = (now_lagos + timedelta(days=1)).strftime("%Y-%m-%dT12:00")

    # 1. Job Create Blocked
    res_job_create = manager_client.post('/jobs/new/', {
        'site': site.pk,
        'title': 'Blocked Job',
        'start_time': start_str,
        'end_time': end_str,
    })
    assert res_job_create.status_code == 403
    assert not Job.objects.filter(title='Blocked Job').exists()

    # 2. JSON AJAX request receives 403 JSON
    res_ajax = manager_client.post('/jobs/new/', {
        'site': site.pk,
        'title': 'Blocked AJAX Job',
        'start_time': start_str,
        'end_time': end_str,
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    assert res_ajax.status_code == 403
    assert 'State-changing actions are disabled' in res_ajax.json()['error']

    # 3. Site Create Blocked
    res_site = manager_client.post('/sites/new/', {
        'name': 'Blocked Site',
        'latitude': '6.500000',
        'longitude': '3.400000',
    })
    assert res_site.status_code == 403

    # 4. Policy Edit Blocked
    res_policy = manager_client.post('/policy/', {
        'rain_prob_caution': 35,
        'rain_prob_stop': 65,
        'precip_caution_mm': '1.50',
        'precip_stop_mm': '4.50',
        'gust_caution_kmh': '20.00',
        'gust_stop_kmh': '35.00',
        'apparent_temp_caution_c': '28.00',
        'apparent_temp_stop_c': '33.00',
    })
    assert res_policy.status_code == 403


@pytest.mark.django_db
def test_demo_mode_banner_displayed_in_ui(client, settings):
    """Verify demo mode warning banner is present in base HTML when active."""
    settings.DEMO_MODE = True
    response = client.get('/')
    assert response.status_code == 200
    assert "Demo Mode:" in response.content.decode('utf-8')


@pytest.mark.django_db
def test_demo_replay_scenarios_render_without_db_mutations(client, db):
    """
    Ticket 10 Check: replay is visibly labelled simulation,
    historical reasons match fixtures, and zero database mutations occur.
    """
    initial_job_count = Job.objects.count()
    initial_snap_count = ForecastSnapshot.objects.count()

    scenarios = ['normal', 'caution', 'unsuitable', 'timeout_retry', 'stale', 'expired', 'circuit_recovery']

    for sc in scenarios:
        res = client.get(f'/demo/replay/?scenario={sc}')
        assert res.status_code == 200
        html = res.content.decode('utf-8')

        # Visible simulation label
        assert "Simulation Only" in html
        assert "Auditable Resilience Evidence" in html

        # Scenario-specific content
        if sc == 'normal':
            assert "Normal Success" in html
            assert "Suitable" in html
        elif sc == 'caution':
            assert "Caution" in html
            assert "Rain probability reached 55%" in html
        elif sc == 'unsuitable':
            assert "Stop Work" in html
            assert "Precipitation reached 7.5 mm/h" in html
        elif sc == 'timeout_retry':
            assert "HTTP 504 Gateway Timeout" in html
            assert "Exponential Backoff" in html
        elif sc == 'stale':
            assert "Historical context (Stale)" in html
            assert "Suitable Suppression" in html
        elif sc == 'expired':
            assert "No current recommendation" in html
            assert "Zero Planning Signal" in html
        elif sc == 'circuit_recovery':
            assert "CLOSED" in html
            assert "HALF_OPEN" in html
            assert "OPEN" in html

    # Strict invariant: replay never mutates shared DB
    assert Job.objects.count() == initial_job_count
    assert ForecastSnapshot.objects.count() == initial_snap_count


@pytest.mark.django_db
def test_normal_page_views_send_no_provider_requests(client, monkeypatch):
    """Ticket 10 Check: normal page views send no provider requests."""
    def mock_forbidden_fetch(*args, **kwargs):
        raise AssertionError("OpenMeteoProvider.fetch called during web page load!")

    monkeypatch.setattr(OpenMeteoProvider, "fetch", mock_forbidden_fetch)

    assert client.get('/').status_code == 200
    assert client.get('/operations/').status_code == 200
    assert client.get('/demo/replay/').status_code == 200
