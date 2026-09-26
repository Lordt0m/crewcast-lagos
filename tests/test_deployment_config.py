import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ('overrides', 'expected'),
    [
        ({'SECRET_KEY': None}, 'Set a unique SECRET_KEY'),
        ({'SECRET_KEY': 'django-insecure-old-key'}, 'Set a unique SECRET_KEY'),
        ({'SECRET_KEY': 'insecure-development-key-change-in-production-lagos-weather-planning'}, 'Set a unique SECRET_KEY'),
        ({'ALLOWED_HOSTS': None}, 'Set ALLOWED_HOSTS'),
        ({'ALLOWED_HOSTS': '*'}, 'ALLOWED_HOSTS must list explicit'),
        ({'DATABASE_URL': None}, 'Set a PostgreSQL DATABASE_URL'),
        ({'DATABASE_URL': 'sqlite:///db.sqlite3'}, 'DATABASE_URL must use a PostgreSQL URL'),
    ],
)
def test_production_settings_fail_closed(overrides, expected):
    env = os.environ.copy()
    env.update({
        'DEBUG': 'False',
        'SECRET_KEY': 'unique-test-secret-key-not-for-deployment',
        'ALLOWED_HOSTS': 'crewcast.example.com',
        'DATABASE_URL': 'postgresql://user:password@localhost:5432/crewcast',
        'DJANGO_SETTINGS_MODULE': 'crewcast.settings',
    })
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    result = subprocess.run(
        [sys.executable, '-c', 'import django; django.setup()'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert expected in result.stderr


def test_production_settings_accept_explicit_configuration():
    env = os.environ.copy()
    env.update({
        'DEBUG': 'False',
        'SECRET_KEY': 'unique-test-secret-key-not-for-deployment',
        'ALLOWED_HOSTS': 'crewcast.example.com',
        'DATABASE_URL': 'postgresql://user:password@localhost:5432/crewcast',
        'DJANGO_SETTINGS_MODULE': 'crewcast.settings',
    })
    result = subprocess.run(
        [sys.executable, '-c', 'import django; django.setup()'],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_postgres_url_keeps_tls_options_and_decodes_credentials():
    env = os.environ.copy()
    env.update({
        'DEBUG': 'False',
        'SECRET_KEY': 'unique-test-secret-key-not-for-deployment',
        'ALLOWED_HOSTS': 'crewcast.example.com',
        'DATABASE_URL': 'postgresql://crewcast:p%40ssword@db.example.com/crewcast?sslmode=require&channel_binding=require',
        'DJANGO_SETTINGS_MODULE': 'crewcast.settings',
    })
    result = subprocess.run(
        [sys.executable, '-c', "import django; django.setup(); from django.conf import settings; print(settings.DATABASES['default']['PASSWORD']); print(settings.DATABASES['default']['OPTIONS'])"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert 'p@ssword' in result.stdout
    assert "'sslmode': 'require'" in result.stdout
    assert "'channel_binding': 'require'" in result.stdout


def test_forecast_sync_workflow_configuration():
    workflow_file = ROOT / '.github' / 'workflows' / 'forecast-sync.yml'
    assert workflow_file.is_file(), "Forecast sync workflow file must exist"

    content = workflow_file.read_text(encoding='utf-8')

    # 1. Schedule trigger with off-peak minute cron
    assert 'schedule:' in content
    assert 'cron: "17 * * * *"' in content

    # 2. Manual trigger enabled
    assert 'workflow_dispatch:' in content

    # 3. Concurrency and gating variable
    assert 'group: crewcast-forecast-refresh' in content
    assert "vars.CREWCAST_FORECAST_ENABLED == 'true'" in content

    # 4. Command execution
    assert 'python manage.py sync_due_forecasts' in content


def test_cache_configuration_redis_optional():
    # Without shared Redis, a separate scheduled worker cannot invalidate a
    # process-local board cache. Use no cache so every request reads the DB.
    env_no_redis = os.environ.copy()
    env_no_redis.pop('REDIS_URL', None)
    res_no_redis = subprocess.run(
        [sys.executable, '-c', "import django; django.setup(); from django.conf import settings; from django.core.cache import cache; print(settings.CACHES['default']['BACKEND']); cache.set('crewcast:test', 'old'); print(cache.get('crewcast:test'))"],
        cwd=ROOT,
        env=env_no_redis,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_no_redis.returncode == 0, res_no_redis.stderr
    assert 'DummyCache' in res_no_redis.stdout
    assert res_no_redis.stdout.splitlines()[-1] == 'None'

    # 2. With REDIS_URL -> RedisCache
    env_redis = os.environ.copy()
    env_redis['REDIS_URL'] = 'redis://localhost:6379/0'
    res_redis = subprocess.run(
        [sys.executable, '-c', "import django; django.setup(); from django.conf import settings; print(settings.CACHES['default']['BACKEND'])"],
        cwd=ROOT,
        env=env_redis,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_redis.returncode == 0, res_redis.stderr
    assert 'RedisCache' in res_redis.stdout
