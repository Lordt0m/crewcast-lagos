from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import Job, Site, WeatherPolicyVersion, ForecastSnapshot, SyncAttempt, Recommendation, LAGOS_TZ
from core.services.cache_service import invalidate_board_cache
from core.services.evaluation_service import evaluate_and_record_job
from core.services.provider import OpenMeteoProvider


@pytest.fixture
def example(db):
    site = Site.objects.create(name='QA Lagos site', latitude=Decimal('6.45'), longitude=Decimal('3.42'))
    start = timezone.now().astimezone(LAGOS_TZ).replace(hour=9, minute=0, second=0, microsecond=0)
    policy = WeatherPolicyVersion.get_latest_default()
    job = Job.objects.create(title='QA outdoor job', site=site, start_time=start, end_time=start + timedelta(hours=3), policy_version=policy)
    hourly = {(start + timedelta(hours=i)).astimezone(dt_timezone.utc).isoformat(): {
        'precipitation_probability': 10, 'precipitation': 0.0,
        'wind_gusts_10m': 12.0, 'apparent_temperature': 27.0,
    } for i in range(4)}
    snapshot = ForecastSnapshot.objects.create(site=site, content_hash='qa-safe-weather', hourly_data=hourly,
        coverage_start=start, coverage_end=start + timedelta(hours=3), hours_count=4,
        returned_latitude=site.latitude, returned_longitude=site.longitude)
    retrieved = timezone.now() - timedelta(hours=1)
    attempt = SyncAttempt.objects.create(site=site, planned_at=retrieved, started_at=retrieved,
        completed_at=retrieved, outcome='success', snapshot=snapshot)
    rec, _ = evaluate_and_record_job(job, snapshot)
    invalidate_board_cache()
    return job, attempt, rec


@pytest.mark.django_db
@pytest.mark.parametrize('age,state,expected_review', [(1, 'fresh', 0), (7, 'stale', 1), (14, 'expired', 1)])
def test_review_counts_and_detail_do_not_promote_aged_favourable_signal(client, example, age, state, expected_review):
    job, attempt, rec = example
    assert rec.status == 'suitable'
    attempt.completed_at = timezone.now() - timedelta(hours=age)
    attempt.save(update_fields=['completed_at'])
    invalidate_board_cache()
    board = client.get('/')
    detail = client.get(f'/jobs/{job.pk}/')
    assert board.context['attention_count'] == expected_review
    assert detail.context['freshness_state'] == state
    html = detail.content.decode()
    assert 'Forecast provenance' in html
    assert 'datetime=' in html
    if state != 'fresh':
        assert 'All forecast metrics remain within caution thresholds' not in html
        assert 'favourable signal is suppressed' in html
        assert 'badge status-suitable' not in html


@pytest.mark.django_db
def test_public_workflows_are_complete_without_script_and_never_fetch(client, example, monkeypatch):
    job, _, _ = example
    def forbidden(*args, **kwargs):
        raise AssertionError('Page view attempted provider access')
    monkeypatch.setattr(OpenMeteoProvider, 'fetch', forbidden)
    before = (Job.objects.count(), ForecastSnapshot.objects.count(), SyncAttempt.objects.count(), Recommendation.objects.count())
    routes = ['/', f'/jobs/{job.pk}/', '/operations/']
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200
        html = response.content.decode()
        assert '<main' in html and 'Skip to content' in html
        assert 'Planning signal only' in html
        assert 'occupational safety clearances' in html
        assert '/demo/replay/' not in html
        assert 'Failure replay' not in html
        assert 'Demo Mode' not in html
        assert 'This demo' not in html
    assert before == (Job.objects.count(), ForecastSnapshot.objects.count(), SyncAttempt.objects.count(), Recommendation.objects.count())


@pytest.mark.django_db
def test_empty_demo_has_a_read_only_recovery_route(client, settings):
    settings.DEMO_MODE = True
    invalidate_board_cache()
    html = client.get('/').content.decode()
    assert 'No jobs planned for this day' in html
    assert 'Check site forecast health' in html
    assert 'Read-only access' in html
    assert 'Example comparison' in html
    assert 'href="/jobs/new/"' not in html


@pytest.mark.django_db
def test_retired_replay_follows_to_usable_planning_board(client):
    response = client.get('/demo/replay/?scenario=not-a-scenario', follow=True)
    assert response.status_code == 200
    assert response.redirect_chain == [('/#planning', 301)]
    assert 'data-planning-board' in response.content.decode()


@pytest.mark.django_db
def test_date_fragment_keeps_server_rules_and_native_anchor(client, example, monkeypatch):
    job, _, _ = example
    monkeypatch.setattr(OpenMeteoProvider, 'fetch', lambda *a, **kw: pytest.fail('Date selection fetched provider'))
    route = f'/?date={job.start_time.astimezone(LAGOS_TZ).date().isoformat()}'
    full = client.get(route)
    partial = client.get(route, HTTP_X_CREWCAST_BOARD='1')
    assert partial.status_code == 200
    html = partial.content.decode()
    assert '<html' not in html and 'data-planning-board' in html
    assert 'data-board-status' in html and '#planning' in html
    assert job.title in html
    assert partial.context['attention_count'] == full.context['attention_count']
    assert 'X-CrewCast-Board' in full['Vary'] and 'X-CrewCast-Board' in partial['Vary']
    assert len(partial.content) < len(full.content)


@pytest.mark.django_db
def test_operations_shell_has_clean_title_and_one_closed_page_wrapper(client):
    html = client.get('/operations/').content.decode()
    assert '<title>Forecast operations — CrewCast Lagos</title>' in html
    assert html.count('class="operations-page"') == 1
    assert '</section>\n</div>\n' in html
