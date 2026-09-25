import logging
from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
from .services.sync_service import check_and_sync_all_due_sites

logger = logging.getLogger(__name__)

WORKER_HEARTBEAT_CACHE_KEY = 'crewcast:worker:heartbeat'
SCHEDULER_HEARTBEAT_CACHE_KEY = 'crewcast:scheduler:heartbeat'

@shared_task(name='core.tasks.record_worker_heartbeat_task')
def record_worker_heartbeat_task():
    """Task executed periodically by Celery Worker to record worker liveness."""
    now_iso = timezone.now().isoformat()
    try:
        cache.set(WORKER_HEARTBEAT_CACHE_KEY, now_iso, timeout=300)
    except Exception as exc:
        logger.warning(f"Failed to record worker heartbeat to cache: {exc}")
    return now_iso

@shared_task(name='core.tasks.record_scheduler_heartbeat_task')
def record_scheduler_heartbeat_task():
    """Task executed periodically by Celery Beat to record scheduler liveness."""
    now_iso = timezone.now().isoformat()
    try:
        cache.set(SCHEDULER_HEARTBEAT_CACHE_KEY, now_iso, timeout=300)
    except Exception as exc:
        logger.warning(f"Failed to record scheduler heartbeat to cache: {exc}")
    return now_iso

@shared_task(name='core.tasks.check_due_sites_task')
def check_due_sites_task():
    """Periodic Celery Beat task that evaluates and synchronizes all due sites."""
    logger.info("Running check_due_sites_task")
    now_iso = timezone.now().isoformat()
    try:
        cache.set(SCHEDULER_HEARTBEAT_CACHE_KEY, now_iso, timeout=300)
    except Exception as exc:
        logger.warning(f"Failed to update scheduler heartbeat during check_due_sites: {exc}")

    results = check_and_sync_all_due_sites()
    logger.info(f"check_due_sites_task completed with {len(results)} site synchronizations.")
    return len(results)
