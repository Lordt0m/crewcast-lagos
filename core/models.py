import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

LAGOS_TZ = ZoneInfo("Africa/Lagos")

LAGOS_LAT_MIN = Decimal("6.200000")
LAGOS_LAT_MAX = Decimal("6.800000")
LAGOS_LON_MIN = Decimal("2.700000")
LAGOS_LON_MAX = Decimal("4.200000")
MAX_ACTIVE_SITES = 10
HORIZON_DAYS = 7
DUE_INTERVAL_HOURS = 3


class Site(models.Model):
    """A saved Lagos-area work location with coordinates used to request a forecast."""
    name = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def is_due(self, now: datetime = None) -> bool:
        """Determines if the site is due for a scheduled 3-hour forecast retrieval."""
        if not self.is_active:
            return False
        if self.last_successful_sync_at is None:
            return True
        # Older demo seeds populated this timestamp without a provider call.
        # Do not let that unverified timestamp postpone the first real sync.
        if not self.sync_attempts.filter(outcome='success', source_kind='worker').exists():
            return True
        if now is None:
            now = timezone.now()
        elapsed = now - self.last_successful_sync_at
        return elapsed >= timedelta(hours=DUE_INTERVAL_HOURS)

    @property
    def next_sync_due_at(self) -> datetime | None:
        """Computes next scheduled sync due instant (3 hours after last success)."""
        if self.last_successful_sync_at is None:
            return None
        return self.last_successful_sync_at + timedelta(hours=DUE_INTERVAL_HOURS)

    def clean(self):
        super().clean()
        if self.is_active:
            active_qs = Site.objects.filter(is_active=True)
            if self.pk:
                active_qs = active_qs.exclude(pk=self.pk)
            if active_qs.count() >= MAX_ACTIVE_SITES:
                raise ValidationError(f"A team may have at most {MAX_ACTIVE_SITES} active sites.")

        if not (LAGOS_LAT_MIN <= self.latitude <= LAGOS_LAT_MAX):
            raise ValidationError(
                f"Latitude must be within the Lagos area ({LAGOS_LAT_MIN} to {LAGOS_LAT_MAX})."
            )
        if not (LAGOS_LON_MIN <= self.longitude <= LAGOS_LON_MAX):
            raise ValidationError(
                f"Longitude must be within the Lagos area ({LAGOS_LON_MIN} to {LAGOS_LON_MAX})."
            )


class WeatherPolicyVersion(models.Model):
    """Immutable versioned caution and stop thresholds for weather metrics."""
    rain_prob_caution = models.PositiveSmallIntegerField(
        default=40, help_text="Rain probability caution threshold (%)"
    )
    rain_prob_stop = models.PositiveSmallIntegerField(
        default=70, help_text="Rain probability stop threshold (%)"
    )
    precip_caution_mm = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("2.00"),
        help_text="Precipitation caution threshold (mm/h)"
    )
    precip_stop_mm = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("5.00"),
        help_text="Precipitation stop threshold (mm/h)"
    )
    gust_caution_kmh = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("25.00"),
        help_text="Wind gusts caution threshold (km/h)"
    )
    gust_stop_kmh = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("40.00"),
        help_text="Wind gusts stop threshold (km/h)"
    )
    apparent_temp_caution_c = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("30.00"),
        help_text="Apparent temperature caution threshold (°C)"
    )
    apparent_temp_stop_c = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("35.00"),
        help_text="Apparent temperature stop threshold (°C)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Policy v{self.pk} ({self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else 'new'})"

    def clean(self):
        super().clean()
        errors = {}
        if self.rain_prob_caution >= self.rain_prob_stop:
            errors['rain_prob_caution'] = "Rain probability caution threshold must be strictly less than stop threshold."
        if self.precip_caution_mm >= self.precip_stop_mm:
            errors['precip_caution_mm'] = "Precipitation caution threshold must be strictly less than stop threshold."
        if self.gust_caution_kmh >= self.gust_stop_kmh:
            errors['gust_caution_kmh'] = "Wind gusts caution threshold must be strictly less than stop threshold."
        if self.apparent_temp_caution_c >= self.apparent_temp_stop_c:
            errors['apparent_temp_caution_c'] = "Apparent temperature caution threshold must be strictly less than stop threshold."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.pk:
            existing = WeatherPolicyVersion.objects.get(pk=self.pk)
            threshold_fields = [
                'rain_prob_caution', 'rain_prob_stop',
                'precip_caution_mm', 'precip_stop_mm',
                'gust_caution_kmh', 'gust_stop_kmh',
                'apparent_temp_caution_c', 'apparent_temp_stop_c'
            ]
            has_changes = any(getattr(existing, f) != getattr(self, f) for f in threshold_fields)
            if has_changes:
                raise ValidationError("WeatherPolicyVersion is immutable. Create a new version instead of rewriting history.")
        super().save(*args, **kwargs)

    @classmethod
    def get_latest_default(cls):
        latest = cls.objects.first()
        if not latest:
            latest = cls.objects.create()
        return latest

    def get_thresholds_dict(self) -> dict:
        return {
            'rain_prob_caution': self.rain_prob_caution,
            'rain_prob_stop': self.rain_prob_stop,
            'precip_caution_mm': float(self.precip_caution_mm),
            'precip_stop_mm': float(self.precip_stop_mm),
            'gust_caution_kmh': float(self.gust_caution_kmh),
            'gust_stop_kmh': float(self.gust_stop_kmh),
            'apparent_temp_caution_c': float(self.apparent_temp_caution_c),
            'apparent_temp_stop_c': float(self.apparent_temp_stop_c),
        }


class Job(models.Model):
    """A planned outdoor work window at one site with a copied weather policy."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='jobs')
    title = models.CharField(max_length=150)
    start_time = models.DateTimeField(help_text="Job start time in UTC instant")
    end_time = models.DateTimeField(help_text="Job end time in UTC instant")
    revision = models.PositiveIntegerField(default=1)
    policy_version = models.ForeignKey(
        WeatherPolicyVersion, on_delete=models.PROTECT, related_name='jobs'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start_time', 'title']

    def __str__(self):
        return f"{self.title} at {self.site.name}"

    def clean(self):
        super().clean()
        if not self.start_time or not self.end_time:
            return

        if self.end_time <= self.start_time:
            raise ValidationError({'end_time': "Choose an end time after the start time."})

        now_lagos = timezone.now().astimezone(LAGOS_TZ)
        today_start_lagos = now_lagos.replace(hour=0, minute=0, second=0, microsecond=0)
        horizon_end_lagos = today_start_lagos + timedelta(days=HORIZON_DAYS + 1)

        start_lagos = self.start_time.astimezone(LAGOS_TZ)
        end_lagos = self.end_time.astimezone(LAGOS_TZ)

        if start_lagos < today_start_lagos:
            raise ValidationError({'start_time': "Job start time cannot be in the past before today."})

        if end_lagos > horizon_end_lagos:
            raise ValidationError({'end_time': f"Job window cannot exceed the 7-day planning horizon ({horizon_end_lagos.strftime('%Y-%m-%d %H:%M WAT')})."})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.pk:
            self.revision += 1
        super().save(*args, **kwargs)


class BudgetWindow(models.Model):
    """
    Atomic outbound provider call budget tracker per Lagos calendar day.
    Enforces a strict cap of 300 attempts per Lagos calendar day.
    """
    lagos_date = models.DateField(unique=True, help_text="Date in Africa/Lagos calendar")
    source_kind = models.CharField(
        max_length=10,
        choices=[('worker', 'Background worker'), ('unknown', 'Legacy / unverified')],
        default='worker',
    )
    reserved_calls = models.PositiveIntegerField(default=0)
    successful_calls = models.PositiveIntegerField(default=0)
    failed_calls = models.PositiveIntegerField(default=0)
    deferred_calls = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-lagos_date']

    def __str__(self):
        return f"Budget for {self.lagos_date}: {self.reserved_calls}/300 reserved"

    @classmethod
    def reserve_slot(cls, date_lagos, cap: int = 300, max_attempts: int = 20) -> tuple[bool, 'BudgetWindow']:
        """
        Atomically reserve an outbound call slot using row-level locking.
        Returns (True, window) if slot is reserved, or (False, window) if budget is exhausted.
        # ponytail: SQLite uses database-level locking requiring short backoff retries in tests; production uses PostgreSQL row locks.
        """
        import random
        import time
        from django.db.utils import OperationalError

        for attempt in range(max_attempts):
            try:
                with transaction.atomic():
                    cls.objects.get_or_create(lagos_date=date_lagos)
                    window = cls.objects.select_for_update().get(lagos_date=date_lagos)
                    if window.reserved_calls >= cap:
                        window.deferred_calls += 1
                        window.save(update_fields=['deferred_calls'])
                        return False, window
                    window.reserved_calls += 1
                    window.save(update_fields=['reserved_calls'])
                    return True, window
            except OperationalError as exc:
                if 'locked' in str(exc).lower() and attempt < max_attempts - 1:
                    time.sleep(min(0.03 * (attempt + 1), 0.25) + random.uniform(0, 0.02))
                    continue
                raise

    @classmethod
    def record_outcome(cls, date_lagos, success: bool):
        """Atomically record the completion of an attempt."""
        with transaction.atomic():
            cls.objects.get_or_create(lagos_date=date_lagos)
            window = cls.objects.select_for_update().get(lagos_date=date_lagos)
            if success:
                window.successful_calls += 1
                window.save(update_fields=['successful_calls'])
            else:
                window.failed_calls += 1
                window.save(update_fields=['failed_calls'])


class SiteSyncLease(models.Model):
    """
    Lease mechanism to prevent concurrent workers from synchronizing the same due site.
    """
    site = models.OneToOneField(Site, on_delete=models.CASCADE, primary_key=True, related_name='sync_lease')
    lease_token = models.CharField(max_length=64)
    acquired_at = models.DateTimeField(auto_now=True)

    @classmethod
    def acquire(cls, site: Site, ttl_seconds: int = 300) -> str | None:
        token = uuid.uuid4().hex
        now = timezone.now()
        expiry_threshold = now - timedelta(seconds=ttl_seconds)

        with transaction.atomic():
            lease = cls.objects.select_for_update().filter(site=site).first()
            if lease:
                if lease.acquired_at > expiry_threshold:
                    return None
                lease.lease_token = token
                lease.acquired_at = now
                lease.save()
                return token
            cls.objects.create(site=site, lease_token=token)
            return token

    @classmethod
    def release(cls, site: Site, token: str):
        with transaction.atomic():
            cls.objects.filter(site=site, lease_token=token).delete()


class ForecastSnapshot(models.Model):
    """
    An immutable, normalized set of hourly forecast values for one site and one content version.
    Deduplicated by (site, content_hash).
    """
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='snapshots')
    content_hash = models.CharField(max_length=64, db_index=True)
    source_kind = models.CharField(
        max_length=10,
        choices=[('provider', 'Provider retrieval'), ('unknown', 'Legacy / unverified')],
        default='provider',
    )
    returned_latitude = models.DecimalField(max_digits=9, decimal_places=6)
    returned_longitude = models.DecimalField(max_digits=9, decimal_places=6)
    returned_elevation = models.FloatField(default=0.0)
    first_retrieved_at = models.DateTimeField(auto_now_add=True)
    hourly_data = models.JSONField(help_text="Normalized hourly forecast values keyed by UTC ISO timestamp")
    coverage_start = models.DateTimeField()
    coverage_end = models.DateTimeField()
    hours_count = models.PositiveIntegerField()

    class Meta:
        unique_together = ('site', 'content_hash')
        ordering = ['-first_retrieved_at']

    def __str__(self):
        return f"Snapshot {self.content_hash[:8]} for {self.site.name} ({self.hours_count}h)"


class SyncAttempt(models.Model):
    """
    A recorded attempt to obtain a forecast for a site, whether it succeeds,
    fails, reuses identical forecast content, or is deferred.
    """
    OUTCOME_CHOICES = [
        ('success', 'Success'),
        ('transient_failure', 'Transient Failure'),
        ('permanent_failure', 'Permanent Failure'),
        ('deferred', 'Deferred'),
    ]

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='sync_attempts')
    source_kind = models.CharField(
        max_length=10,
        choices=[('worker', 'Background worker'), ('unknown', 'Legacy / unverified')],
        default='worker',
    )
    planned_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    outcome = models.CharField(max_length=30, choices=OUTCOME_CHOICES)
    failure_category = models.CharField(max_length=50, blank=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    snapshot = models.ForeignKey(
        ForecastSnapshot, null=True, blank=True, on_delete=models.SET_NULL, related_name='sync_attempts'
    )

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Attempt {self.attempt_number} for {self.site.name}: {self.outcome}"


class Recommendation(models.Model):
    """
    A recorded planning recommendation for one job revision, one policy version,
    and one forecast snapshot. Unique per input combination.
    """
    STATUS_CHOICES = [
        ('suitable', 'Suitable'),
        ('caution', 'Caution'),
        ('unsuitable', 'Unsuitable'),
        ('unavailable', 'Unavailable'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='recommendations')
    job_revision = models.PositiveIntegerField()
    policy_version = models.ForeignKey(
        WeatherPolicyVersion, on_delete=models.PROTECT, related_name='recommendations'
    )
    snapshot = models.ForeignKey(
        ForecastSnapshot, on_delete=models.CASCADE, related_name='recommendations'
    )
    evaluated_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    reasons = models.JSONField(default=list, help_text="List of crossed threshold reasons")
    metrics_summary = models.JSONField(default=dict, help_text="Observed maximum metrics")
    evaluated_hours = models.JSONField(default=list, help_text="List of evaluated hour labels in WAT")

    class Meta:
        unique_together = ('job', 'job_revision', 'policy_version', 'snapshot')
        ordering = ['-evaluated_at']

    def __str__(self):
        return f"Rec {self.status.upper()} for Job {self.job.pk} rev {self.job_revision}"


class ProviderCircuitState(models.Model):
    """
    Provider-wide circuit breaker state to protect upstream and prevent cascading timeouts.
    Trips to OPEN after 3 consecutive transient failures; cools off for 15 minutes before
    permitting 1 HALF_OPEN test probe.
    """
    CIRCUIT_STATES = [
        ('CLOSED', 'Closed (Healthy)'),
        ('OPEN', 'Open (Cooling Off)'),
        ('HALF_OPEN', 'Half-Open (Testing Probe)'),
    ]

    state = models.CharField(max_length=20, choices=CIRCUIT_STATES, default='CLOSED')
    consecutive_transient_failures = models.PositiveSmallIntegerField(default=0)
    opened_at = models.DateTimeField(null=True, blank=True)
    cooloff_seconds = models.PositiveIntegerField(default=900)
    last_probe_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Circuit {self.state} (Failures: {self.consecutive_transient_failures})"

    @classmethod
    def get_instance(cls) -> 'ProviderCircuitState':
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    @classmethod
    def can_attempt(cls, now: datetime = None) -> tuple[bool, str]:
        if now is None:
            now = timezone.now()
        with transaction.atomic():
            circuit = cls.objects.select_for_update().get_or_create(id=1)[0]
            if circuit.state == 'CLOSED':
                return True, 'CLOSED'

            if circuit.state == 'OPEN':
                if circuit.opened_at:
                    elapsed = (now - circuit.opened_at).total_seconds()
                    if elapsed >= circuit.cooloff_seconds:
                        circuit.state = 'HALF_OPEN'
                        circuit.last_probe_at = now
                        circuit.save(update_fields=['state', 'last_probe_at'])
                        return True, 'HALF_OPEN'
                    return False, f'OPEN (cooling off, {int(circuit.cooloff_seconds - elapsed)}s remaining)'
                return False, 'OPEN'

            if circuit.state == 'HALF_OPEN':
                # Already testing a probe; defer other workers
                return False, 'HALF_OPEN (probe in flight)'
        return False, 'UNKNOWN'

    @classmethod
    def record_success(cls):
        with transaction.atomic():
            circuit = cls.objects.select_for_update().get_or_create(id=1)[0]
            circuit.state = 'CLOSED'
            circuit.consecutive_transient_failures = 0
            circuit.opened_at = None
            circuit.save(update_fields=['state', 'consecutive_transient_failures', 'opened_at'])

    @classmethod
    def record_transient_failure(cls, now: datetime = None, trip_threshold: int = 3):
        if now is None:
            now = timezone.now()
        with transaction.atomic():
            circuit = cls.objects.select_for_update().get_or_create(id=1)[0]
            circuit.consecutive_transient_failures += 1
            if circuit.consecutive_transient_failures >= trip_threshold or circuit.state == 'HALF_OPEN':
                circuit.state = 'OPEN'
                circuit.opened_at = now
            circuit.save(update_fields=['state', 'consecutive_transient_failures', 'opened_at'])


class ScheduledForecastRun(models.Model):
    """Database-backed status for a short-lived scheduler without shared Redis."""

    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    attempt_count = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-started_at', '-pk']
