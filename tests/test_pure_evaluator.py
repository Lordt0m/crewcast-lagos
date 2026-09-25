from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone
import pytest
from zoneinfo import ZoneInfo
from django.utils import timezone
from core.evaluator import evaluate_forecast, get_intersecting_hour_instants
from core.models import Site, Job, WeatherPolicyVersion, ForecastSnapshot, Recommendation, LAGOS_TZ
from core.services.evaluation_service import evaluate_and_record_job

# Synthetic test hourly data generator
def create_test_hourly_data(start_utc: datetime, hours: int = 48, default_values: dict = None):
    data = {}
    vals = default_values or {
        "precipitation_probability": 10,
        "precipitation": 0.0,
        "wind_gusts_10m": 15.0,
        "apparent_temperature": 27.0,
    }
    for i in range(hours):
        t = start_utc + timedelta(hours=i)
        data[t.isoformat()] = dict(vals)
    return data


@pytest.fixture
def default_thresholds():
    return {
        "rain_prob_caution": 40,
        "rain_prob_stop": 70,
        "precip_caution_mm": 2.0,
        "precip_stop_mm": 5.0,
        "gust_caution_kmh": 25.0,
        "gust_stop_kmh": 40.0,
        "apparent_temp_caution_c": 30.0,
        "apparent_temp_stop_c": 35.0,
    }


def test_intersecting_hours_boundaries_and_partials():
    """Verify conservative inclusion of all intersecting hourly intervals."""
    # 1. Exact 1 hour: 10:00 to 11:00 UTC
    t_start = datetime(2026, 9, 25, 10, 0, tzinfo=dt_timezone.utc)
    t_end = datetime(2026, 9, 25, 11, 0, tzinfo=dt_timezone.utc)
    instants = get_intersecting_hour_instants(t_start, t_end)
    assert len(instants) == 2
    assert instants[0] == t_start
    assert instants[1] == t_end

    # 2. Partial hours: 10:15 to 11:45 UTC
    p_start = datetime(2026, 9, 25, 10, 15, tzinfo=dt_timezone.utc)
    p_end = datetime(2026, 9, 25, 11, 45, tzinfo=dt_timezone.utc)
    instants_p = get_intersecting_hour_instants(p_start, p_end)
    # Includes 10:00, 11:00, 12:00
    assert len(instants_p) == 3
    assert instants_p[0] == datetime(2026, 9, 25, 10, 0, tzinfo=dt_timezone.utc)
    assert instants_p[2] == datetime(2026, 9, 25, 12, 0, tzinfo=dt_timezone.utc)


def test_evaluator_suitable_when_all_below_caution(default_thresholds):
    start = datetime(2026, 9, 25, 8, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 25, 12, 0, tzinfo=dt_timezone.utc)
    hourly = create_test_hourly_data(start - timedelta(hours=2), 24, {
        "precipitation_probability": 15,
        "precipitation": 0.5,
        "wind_gusts_10m": 18.0,
        "apparent_temperature": 28.0,
    })

    result = evaluate_forecast(start, end, default_thresholds, hourly)
    assert result.status == "suitable"
    assert len(result.reasons) == 0
    assert result.max_metrics["precipitation_probability"] == 15
    assert result.max_metrics["precipitation"] == 0.5


def test_evaluator_caution_threshold_crossed(default_thresholds):
    start = datetime(2026, 9, 25, 10, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 25, 14, 0, tzinfo=dt_timezone.utc)
    hourly = create_test_hourly_data(start - timedelta(hours=2), 24)

    # Spike wind gusts to 28.0 km/h (caution is 25.0, stop is 40.0) at 12:00
    peak_time = (datetime(2026, 9, 25, 12, 0, tzinfo=dt_timezone.utc)).isoformat()
    hourly[peak_time]["wind_gusts_10m"] = 28.0

    result = evaluate_forecast(start, end, default_thresholds, hourly)
    assert result.status == "caution"
    assert len(result.reasons) == 1
    assert result.reasons[0]["metric"] == "wind_gusts_10m"
    assert result.reasons[0]["level"] == "caution"
    assert result.reasons[0]["observed_value"] == 28.0
    assert result.max_metrics["wind_gusts_10m"] == 28.0


def test_evaluator_stop_threshold_crossed(default_thresholds):
    start = datetime(2026, 9, 25, 9, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 25, 13, 0, tzinfo=dt_timezone.utc)
    hourly = create_test_hourly_data(start - timedelta(hours=2), 24)

    # Spike rain probability to 75% (stop is 70%) at 11:00
    peak_time = (datetime(2026, 9, 25, 11, 0, tzinfo=dt_timezone.utc)).isoformat()
    hourly[peak_time]["precipitation_probability"] = 75

    result = evaluate_forecast(start, end, default_thresholds, hourly)
    assert result.status == "unsuitable"
    assert len(result.reasons) == 1
    assert result.reasons[0]["metric"] == "precipitation_probability"
    assert result.reasons[0]["level"] == "stop"
    assert result.reasons[0]["observed_value"] == 75.0


def test_evaluator_midnight_crossing_in_lagos(default_thresholds):
    """Job from 22:00 WAT to 02:00 WAT next day."""
    lagos_tz = ZoneInfo("Africa/Lagos")
    start_lagos = datetime(2026, 9, 25, 22, 0, tzinfo=lagos_tz)
    end_lagos = datetime(2026, 9, 26, 2, 0, tzinfo=lagos_tz)
    start_utc = start_lagos.astimezone(dt_timezone.utc)
    end_utc = end_lagos.astimezone(dt_timezone.utc)

    hourly = create_test_hourly_data(start_utc - timedelta(hours=2), 24)
    # Cross apparent temp stop at 01:00 WAT (00:00 UTC)
    spike_utc = datetime(2026, 9, 26, 0, 0, tzinfo=dt_timezone.utc).isoformat()
    hourly[spike_utc]["apparent_temperature"] = 36.5 # Stop is 35.0

    result = evaluate_forecast(start_utc, end_utc, default_thresholds, hourly)
    assert result.status == "unsuitable"
    assert result.max_metrics["apparent_temperature"] == 36.5


def test_evaluator_incomplete_coverage_returns_unavailable(default_thresholds):
    start = datetime(2026, 9, 25, 10, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 25, 14, 0, tzinfo=dt_timezone.utc)
    # Hourly data only covers up to 11:00
    hourly = create_test_hourly_data(start, hours=2)

    result = evaluate_forecast(start, end, default_thresholds, hourly)
    assert result.status == "unavailable"
    assert len(result.missing_hours_utc) > 0
    assert result.max_metrics["precipitation_probability"] is None


def test_evaluator_missing_metric_value_returns_unavailable(default_thresholds):
    start = datetime(2026, 9, 25, 10, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 25, 12, 0, tzinfo=dt_timezone.utc)
    hourly = create_test_hourly_data(start - timedelta(hours=1), 5)
    # Null out one metric
    key = start.isoformat()
    hourly[key]["precipitation"] = None

    result = evaluate_forecast(start, end, default_thresholds, hourly)
    assert result.status == "unavailable"


@pytest.mark.django_db
def test_duplicate_inputs_create_no_duplicate_recommendation():
    """Ticket 06 check: repeating same inputs creates no duplicate history."""
    site = Site.objects.create(name="Yaba Yard", latitude=Decimal("6.510000"), longitude=Decimal("3.380000"))
    policy = WeatherPolicyVersion.get_latest_default()
    start = timezone.now() + timedelta(days=1)
    end = start + timedelta(hours=3)
    job = Job.objects.create(site=site, title="Cabling Setup", start_time=start, end_time=end, policy_version=policy)

    hourly = create_test_hourly_data(start - timedelta(hours=2), 24)
    snapshot = ForecastSnapshot.objects.create(
        site=site,
        content_hash="abc123hash",
        returned_latitude=Decimal("6.51"),
        returned_longitude=Decimal("3.38"),
        hourly_data=hourly,
        coverage_start=start - timedelta(hours=2),
        coverage_end=start + timedelta(hours=22),
        hours_count=24,
    )

    # First evaluation
    rec1, created1 = evaluate_and_record_job(job, snapshot)
    assert created1 is True
    assert Recommendation.objects.filter(job=job).count() == 1

    # Second evaluation with identical inputs
    rec2, created2 = evaluate_and_record_job(job, snapshot)
    assert created2 is False
    assert Recommendation.objects.filter(job=job).count() == 1
    assert rec1.pk == rec2.pk


@pytest.mark.django_db
def test_job_edit_creates_new_recommendation_preserving_history():
    """Editing job revision produces new recommendation without deleting prior one."""
    site = Site.objects.create(name="VI Substation", latitude=Decimal("6.430000"), longitude=Decimal("3.420000"))
    policy = WeatherPolicyVersion.get_latest_default()
    start = timezone.now() + timedelta(days=1)
    end = start + timedelta(hours=3)
    job = Job.objects.create(site=site, title="Transformer Oil Check", start_time=start, end_time=end, policy_version=policy)

    hourly = create_test_hourly_data(start - timedelta(hours=2), 24)
    snapshot = ForecastSnapshot.objects.create(
        site=site,
        content_hash="snaphash999",
        returned_latitude=Decimal("6.43"),
        returned_longitude=Decimal("3.42"),
        hourly_data=hourly,
        coverage_start=start - timedelta(hours=2),
        coverage_end=start + timedelta(hours=22),
        hours_count=24,
    )

    rec_rev1, _ = evaluate_and_record_job(job, snapshot)
    assert rec_rev1.job_revision == 1

    # Edit job -> revision becomes 2
    job.title = "Transformer Comprehensive Check"
    job.save()
    assert job.revision == 2

    rec_rev2, created = evaluate_and_record_job(job, snapshot)
    assert created is True
    assert rec_rev2.job_revision == 2

    # Both history records survive
    assert Recommendation.objects.filter(job=job).count() == 2
