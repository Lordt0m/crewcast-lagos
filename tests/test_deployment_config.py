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
