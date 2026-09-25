import pytest
from django.core.cache import cache
import redis


@pytest.fixture(autouse=True)
def configure_test_cache(settings):
    """
    If a real Redis instance is running at settings.REDIS_URL, use it.
    Otherwise (e.g. local Windows development without Redis daemon), use LocMemCache
    so unit tests run deterministically and fast without external dependencies.
    """
    redis_available = False
    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.2)
        r.ping()
        redis_available = True
    except Exception:
        redis_available = False

    if not redis_available:
        settings.CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'crewcast-test-cache',
            }
        }
        from django.core.cache import caches
        caches.close_all()
        try:
            del caches['default']
        except Exception:
            pass
    yield
