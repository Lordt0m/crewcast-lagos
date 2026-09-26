from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import (
    Site,
    Job,
    WeatherPolicyVersion,
    ForecastSnapshot,
    SyncAttempt,
    LAGOS_TZ,
)
from core.services.cache_service import invalidate_board_cache


class Command(BaseCommand):
    help = "Seeds example Lagos sites and jobs. Weather remains pending until a real background sync."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing sites, jobs, snapshots, and attempts before seeding.',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write("Clearing existing data...")
            Job.objects.all().delete()
            SyncAttempt.objects.all().delete()
            ForecastSnapshot.objects.all().delete()
            Site.objects.all().delete()

        now = timezone.now()
        now_lagos = now.astimezone(LAGOS_TZ)
        today_lagos = now_lagos.date()

        # 1. Ensure default policy exists
        policy = WeatherPolicyVersion.get_latest_default()
        self.stdout.write(f"Using weather policy version {policy.pk}")

        # 2. Define 6 example Lagos sites
        sites_def = [
            ("Victoria Island Financial Center", Decimal("6.428100"), Decimal("3.421900")),
            ("Lekki Phase 1 Logistics Base", Decimal("6.447400"), Decimal("3.484200")),
            ("Ikeja Industrial Estate", Decimal("6.592500"), Decimal("3.342100")),
            ("Yaba Silicon Yard", Decimal("6.516700"), Decimal("3.375000")),
            ("Marina Commercial Port", Decimal("6.452000"), Decimal("3.391000")),
            ("Epe Substation Facility", Decimal("6.550000"), Decimal("3.650000")),
        ]

        created_sites = []
        for name, lat, lon in sites_def:
            site, _ = Site.objects.get_or_create(
                name=name,
                defaults={
                    'latitude': lat,
                    'longitude': lon,
                    'is_active': True,
                }
            )
            created_sites.append(site)
        self.stdout.write(self.style.SUCCESS(f"Configured {len(created_sites)} active Lagos sites."))

        # 3. Seed example jobs across the 7-day horizon
        job_templates = [
            ("HVAC Chiller Maintenance", 0, 9, 13, 0),        # Today 09:00 - 13:00 at Site 0
            ("Rooftop Solar Array Inspection", 0, 14, 17, 1),   # Today 14:00 - 17:00 at Site 1
            ("Facade Window Washing", 1, 8, 12, 0),           # Tomorrow 08:00 - 12:00 at Site 0 (Suitable morning)
            ("Afternoon Mast Servicing", 1, 14, 17, 1),        # Tomorrow 14:00 - 17:00 at Site 1 (Storm / Unsuitable)
            ("Microwave Dish Realignment", 2, 9, 14, 2),       # Day +2 09:00 - 14:00 at Site 2
            ("Generator Canopy Waterproofing", 2, 11, 15, 3),   # Day +2 11:00 - 15:00 at Site 3
            ("Fiber Optic Gantry Inspection", 3, 8, 11, 4),    # Day +3 08:00 - 11:00 at Site 4
            ("Telecom Mast Structural Check", 3, 13, 16, 2),   # Day +3 13:00 - 16:00 at Site 2
            ("Substation Transformer Testing", 4, 9, 13, 5),   # Day +4 09:00 - 13:00 at Site 5
            ("Exterior Cable Conduit Fitting", 4, 14, 18, 5),  # Day +4 14:00 - 18:00 at Site 5 (Unsuitable)
            ("Rooftop Lightning Arrestor Check", 5, 10, 14, 3), # Day +5 10:00 - 14:00 at Site 3
            ("High-Voltage Insulator Cleaning", 6, 8, 12, 5),   # Day +6 08:00 - 12:00 at Site 5
        ]

        created_jobs_count = 0
        for title, day_offset, start_hour, end_hour, site_idx in job_templates:
            target_site = created_sites[site_idx % len(created_sites)]
            job_date = today_lagos + timedelta(days=day_offset)
            job_start = datetime(job_date.year, job_date.month, job_date.day, start_hour, 0, tzinfo=LAGOS_TZ)
            job_end = datetime(job_date.year, job_date.month, job_date.day, end_hour, 0, tzinfo=LAGOS_TZ)

            _, j_created = Job.objects.get_or_create(
                site=target_site,
                title=title,
                defaults={
                    'start_time': job_start.astimezone(dt_timezone.utc),
                    'end_time': job_end.astimezone(dt_timezone.utc),
                    'policy_version': policy,
                }
            )
            if j_created:
                created_jobs_count += 1

        invalidate_board_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(created_sites)} example sites and {created_jobs_count} new jobs. "
            "Forecasts and recommendations remain pending until a real provider sync."
        ))
