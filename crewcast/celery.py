import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crewcast.settings')

app = Celery('crewcast')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Celery Beat periodic tasks
app.conf.beat_schedule = {
    'check-due-sites-every-5-minutes': {
        'task': 'core.tasks.check_due_sites_task',
        'schedule': 300.0, # Every 5 minutes
    },
    'worker-heartbeat-every-minute': {
        'task': 'core.tasks.record_worker_heartbeat_task',
        'schedule': 60.0, # Every 60 seconds
    },
    'scheduler-heartbeat-every-minute': {
        'task': 'core.tasks.record_scheduler_heartbeat_task',
        'schedule': 60.0, # Every 60 seconds
    },
}
