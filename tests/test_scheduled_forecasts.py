from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import Client, override_settings
from django.utils import timezone

from core.models import ScheduledForecastRun


@pytest.mark.django_db
def test_scheduled_command_records_success_even_when_no_site_is_due():
    output = StringIO()
    with patch('core.management.commands.sync_due_forecasts.check_and_sync_all_due_sites', return_value=[]):
        call_command('sync_due_forecasts', stdout=output)

    run = ScheduledForecastRun.objects.get()
    assert run.status == ScheduledForecastRun.Status.COMPLETED
    assert run.completed_at is not None
    assert run.attempt_count == 0
    assert '0 site attempts' in output.getvalue()


@pytest.mark.django_db
def test_scheduled_command_records_failure_and_propagates_it():
    with patch('core.management.commands.sync_due_forecasts.check_and_sync_all_due_sites', side_effect=RuntimeError('test failure')):
        with pytest.raises(RuntimeError, match='test failure'):
            call_command('sync_due_forecasts')

    run = ScheduledForecastRun.objects.get()
    assert run.status == ScheduledForecastRun.Status.FAILED
    assert run.error_type == 'RuntimeError'
    assert run.completed_at is not None


@pytest.mark.django_db
@override_settings(FORECAST_RUNNER='github_actions')
def test_scheduled_mode_reports_database_backed_run_instead_of_celery_heartbeats():
    ScheduledForecastRun.objects.create(
        started_at=timezone.now(),
        completed_at=timezone.now(),
        status=ScheduledForecastRun.Status.COMPLETED,
        attempt_count=1,
    )

    client = Client()
    health = client.get('/health/').json()
    assert health['components']['scheduled_forecast']['status'] == 'ok'
    assert 'worker_heartbeat' not in health['components']

    operations = client.get('/operations/')
    assert operations.status_code == 200
    assert 'Scheduled forecast check' in operations.content.decode()
    assert 'Celery Worker' not in operations.content.decode()


@pytest.mark.django_db
@override_settings(FORECAST_RUNNER='github_actions')
def test_scheduled_mode_marks_old_run_stale():
    from datetime import timedelta

    ScheduledForecastRun.objects.create(
        started_at=timezone.now() - timedelta(hours=3),
        completed_at=timezone.now() - timedelta(hours=3),
        status=ScheduledForecastRun.Status.COMPLETED,
    )
    health = Client().get('/health/').json()
    assert health['components']['scheduled_forecast']['status'] == 'stale'
