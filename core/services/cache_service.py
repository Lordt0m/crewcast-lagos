import logging
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

BOARD_CACHE_VERSION_KEY = 'crewcast:board:cache_version'
BOARD_CACHE_TTL_SECONDS = 1800  # 30 minutes


def get_board_cache_version() -> int:
    """Returns the current monotonic version integer for board cache keys."""
    try:
        ver = cache.get(BOARD_CACHE_VERSION_KEY)
        if ver is None:
            cache.set(BOARD_CACHE_VERSION_KEY, 1, timeout=None)
            return 1
        return int(ver)
    except Exception as exc:
        logger.warning(f"Failed to read board cache version: {exc}")
        return 1


def invalidate_board_cache() -> None:
    """Invalidates the cached job board data across all dates."""
    try:
        try:
            cache.incr(BOARD_CACHE_VERSION_KEY)
        except Exception:
            cache.set(BOARD_CACHE_VERSION_KEY, int(timezone.now().timestamp()), timeout=None)
        logger.info("Board cache invalidated.")
    except Exception as exc:
        logger.warning(f"Failed to invalidate board cache: {exc}")
