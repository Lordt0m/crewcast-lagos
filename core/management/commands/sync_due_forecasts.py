from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import ScheduledForecastRun
from core.services.sync_service import check_and_sync_all_due_sites


class Command(BaseCommand):
    help = "Synchronize due forecast sites once, then exit (for scheduled runners)."

    def handle(self, *args, **options):
        run = ScheduledForecastRun.objects.create(started_at=timezone.now())
        try:
            results = check_and_sync_all_due_sites()
        except Exception as exc:
            run.status = ScheduledForecastRun.Status.FAILED
            run.completed_at = timezone.now()
            run.error_type = type(exc).__name__
            run.save(update_fields=['status', 'completed_at', 'error_type'])
            raise

        run.status = ScheduledForecastRun.Status.COMPLETED
        run.completed_at = timezone.now()
        run.attempt_count = len(results)
        run.save(update_fields=['status', 'completed_at', 'attempt_count'])
        self.stdout.write(self.style.SUCCESS(f"Forecast check complete: {len(results)} site attempts."))
