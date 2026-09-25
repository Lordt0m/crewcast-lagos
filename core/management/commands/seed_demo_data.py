import hashlib
import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone
from core.models import (
    Site,
    Job,
    WeatherPolicyVersion,
    ForecastSnapshot,
    BudgetWindow,
    SyncAttempt,
    LAGOS_TZ,
)
from core.services.evaluation_service import evaluate_and_record_job
from core.services.cache_service import invalidate_board_cache


class Command(BaseCommand):
    help = "Seeds synthetic Lagos sites, policies, jobs, and canned forecast snapshots for realistic demo."

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

        # 1. Create or get manager user
        user, user_created = User.objects.get_or_create(
            username="dispatcher",
            defaults={'email': 'dispatcher@crewcast.ng'}
        )
        if user_created:
            user.set_password("crewcast2026")
            user.save()
            self.stdout.write(self.style.SUCCESS("Created demo manager: dispatcher / crewcast2026"))

        # 2. Ensure default policy exists
        policy = WeatherPolicyVersion.get_latest_default()
        self.stdout.write(f"Using weather policy version {policy.pk}")

        # 3. Define 6 realistic Lagos sites
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
                    'last_successful_sync_at': now - timedelta(hours=1, minutes=15),
                }
            )
            created_sites.append(site)
        self.stdout.write(self.style.SUCCESS(f"Configured {len(created_sites)} active Lagos sites."))

        # 4. Generate realistic canned 7-day forecast snapshots for each site
        # 168 hours covering today 00:00 UTC through next 7 days
        snap_start = datetime(today_lagos.year, today_lagos.month, today_lagos.day, 0, 0, tzinfo=LAGOS_TZ).astimezone(dt_timezone.utc)
        
        for idx, site in enumerate(created_sites):
            hourly_data = {}
            for h in range(168):
                t_dt = snap_start + timedelta(hours=h)
                t_key = t_dt.isoformat()
                t_wat = t_dt.astimezone(LAGOS_TZ)
                hour_of_day = t_wat.hour
                day_offset = (t_wat.date() - today_lagos).days

                # Create realistic tropical weather patterns:
                # Afternoon thermal rain / convection around 14:00 - 17:00
                if 14 <= hour_of_day <= 17 and (day_offset in (1, 4)):
                    # Convective afternoon downpour scenario on day 1 and 4
                    prob = 78
                    precip = 6.2
                    gusts = 42.0
                    temp = 32.5
                elif 12 <= hour_of_day <= 16:
                    # Warm tropical afternoon with moderate caution wind/temp
                    prob = 45 + (idx * 5) % 25
                    precip = 1.2
                    gusts = 26.0
                    temp = 31.0
                elif 0 <= hour_of_day <= 6:
                    # Cool night / morning
                    prob = 10
                    precip = 0.0
                    gusts = 12.0
                    temp = 25.0
                else:
                    # Standard fair weather work morning
                    prob = 20
                    precip = 0.2
                    gusts = 18.0
                    temp = 28.5

                hourly_data[t_key] = {
                    "precipitation_probability": prob,
                    "precipitation": precip,
                    "wind_gusts_10m": gusts,
                    "apparent_temperature": temp,
                }

            raw_bytes = json.dumps(hourly_data, sort_keys=True).encode('utf-8')
            content_hash = hashlib.sha256(raw_bytes).hexdigest()

            snapshot, snap_created = ForecastSnapshot.objects.get_or_create(
                site=site,
                content_hash=content_hash,
                defaults={
                    'returned_latitude': site.latitude,
                    'returned_longitude': site.longitude,
                    'returned_elevation': 12.0,
                    'hourly_data': hourly_data,
                    'coverage_start': snap_start,
                    'coverage_end': snap_start + timedelta(hours=167),
                    'hours_count': 168,
                }
            )

            # Record a successful sync attempt
            SyncAttempt.objects.get_or_create(
                site=site,
                snapshot=snapshot,
                defaults={
                    'planned_at': now - timedelta(hours=1, minutes=15),
                    'started_at': now - timedelta(hours=1, minutes=15),
                    'completed_at': now - timedelta(hours=1, minutes=14, seconds=45),
                    'attempt_number': 1,
                    'outcome': 'success',
                    'http_status': 200,
                }
            )

        # 5. Seed realistic jobs across the 7-day horizon
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

            job, j_created = Job.objects.get_or_create(
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
                # Evaluate job against site's snapshot
                site_snap = ForecastSnapshot.objects.filter(site=target_site).order_by('-first_retrieved_at').first()
                if site_snap:
                    evaluate_and_record_job(job, site_snap)

        # 6. Initialize Today's Budget Window
        budget, _ = BudgetWindow.objects.get_or_create(
            lagos_date=today_lagos,
            defaults={
                'reserved_calls': 18,
                'successful_calls': 18,
                'failed_calls': 0,
                'deferred_calls': 0,
            }
        )

        invalidate_board_cache()
        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded demo data: {len(created_sites)} sites, {created_jobs_count} new jobs, "
            f"and budget tracking for {today_lagos}."
        ))
