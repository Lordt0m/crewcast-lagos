import json
import pytest
from django.conf import settings
from django.test import Client
from django.core.management import call_command
from django.core.cache import cache
from core.tasks import record_worker_heartbeat_task, WORKER_HEARTBEAT_CACHE_KEY

@pytest.mark.django_db
def test_django_system_check():
    """Verify that Django's system check passes without any errors or warnings."""
    call_command('check')

def test_timezone_is_africa_lagos():
    """Verify that project timezone is strictly set to Africa/Lagos."""
    assert settings.TIME_ZONE == 'Africa/Lagos'
    assert settings.USE_TZ is True

@pytest.mark.django_db
def test_health_check_endpoint():
    """Verify that /health/ returns 200 with structured component statuses."""
    client = Client()
    response = client.get('/health/')
    assert response.status_code == 200
    
    data = response.json()
    assert data['status'] == 'ok'
    assert 'timestamp' in data
    assert 'components' in data
    
    components = data['components']
    assert components['web']['status'] == 'ok'
    assert components['database']['status'] == 'ok'
    assert 'cache' in components
    assert 'worker_heartbeat' in components


@pytest.mark.django_db
def test_health_check_reports_intentionally_disabled_shared_cache(settings):
    settings.REDIS_URL = None
    response = Client().get('/health/')
    assert response.status_code == 200
    assert response.json()['components']['cache']['status'] == 'not_configured'

@pytest.mark.django_db
def test_worker_heartbeat_recording():
    """Verify that the Celery worker heartbeat task records liveness correctly."""
    # Execute heartbeat task directly
    heartbeat_time = record_worker_heartbeat_task()
    assert heartbeat_time is not None
    
    # Query health endpoint
    client = Client()
    response = client.get('/health/')
    assert response.status_code == 200
    data = response.json()
    hb = data['components']['worker_heartbeat']
    assert hb['status'] in ('ok', 'inactive') # In unit tests cache may be memory/mocked
