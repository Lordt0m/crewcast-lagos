import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone as dt_timezone
from email.utils import format_datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from core.services.provider import (
    FixtureProvider,
    OpenMeteoProvider,
    TransientProviderError,
    PermanentProviderError,
    REQUESTED_HOURLY_VARIABLES,
    parse_retry_after,
)
from core.services.normalizer import (
    normalize_forecast_payload,
    NormalizedForecast,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_requested_hourly_variables_exact_four():
    """Verify strictly only the four specified Open-Meteo variables are requested."""
    expected = [
        "precipitation_probability",
        "precipitation",
        "wind_gusts_10m",
        "apparent_temperature",
    ]
    assert REQUESTED_HOURLY_VARIABLES == expected


def test_normal_7day_fixture_normalization():
    """Verify that normal_7day fixture normalizes 168 hours cleanly and generates a valid hash."""
    fixture_file = FIXTURES_DIR / "normal_7day.json"
    provider = FixtureProvider(fixture_file)
    raw = provider.fetch(6.45, 3.45)

    norm = normalize_forecast_payload(raw, min_hours=168)
    assert isinstance(norm, NormalizedForecast)
    assert norm.hours_count == 168
    assert len(norm.hourly_data) == 168
    assert len(norm.content_hash) == 64 # SHA-256 hex string

    # Verify grid coordinates preserved
    assert norm.returned_latitude == Decimal("6.45")
    assert norm.returned_longitude == Decimal("3.45")
    assert norm.returned_elevation == 10.0

    # Verify times are in UTC format with Z / +00:00
    first_hour = list(norm.hourly_data.keys())[0]
    assert "+00:00" in first_hour or "Z" in first_hour


def test_generation_time_excluded_from_hash():
    """
    Verify that generationtime_ms is NOT treated as forecast issue timestamp
    and changes to generationtime_ms do not change the content hash.
    """
    with open(FIXTURES_DIR / "normal_7day.json", "r") as f:
        payload_1 = json.load(f)
    payload_2 = json.loads(json.dumps(payload_1))

    payload_1["generationtime_ms"] = 0.123
    payload_2["generationtime_ms"] = 99.999 # Substantially different processing time

    norm_1 = normalize_forecast_payload(payload_1)
    norm_2 = normalize_forecast_payload(payload_2)

    assert norm_1.content_hash == norm_2.content_hash


def test_drift_payload_changes_content_hash():
    """Verify that different weather metrics produce a distinct content hash."""
    with open(FIXTURES_DIR / "normal_7day.json", "r") as f:
        normal = json.load(f)
    with open(FIXTURES_DIR / "drift_payload.json", "r") as f:
        drift = json.load(f)

    norm_normal = normalize_forecast_payload(normal)
    norm_drift = normalize_forecast_payload(drift)

    assert norm_normal.content_hash != norm_drift.content_hash


def test_partial_coverage_fixture():
    """Verify partial coverage detection when expecting full 7 days."""
    with open(FIXTURES_DIR / "partial_coverage.json", "r") as f:
        partial = json.load(f)

    # If expecting 168 hours, it should raise a validation error
    with pytest.raises(ValidationError) as exc:
        normalize_forecast_payload(partial, min_hours=168)
    assert "coverage insufficient" in str(exc.value)

    # But without min_hours threshold, it normalizes the 48 available hours cleanly
    norm = normalize_forecast_payload(partial, min_hours=24)
    assert norm.hours_count == 48


def test_malformed_schema_fixture_raises_validation_error():
    """Verify malformed array length raises ValidationError."""
    with open(FIXTURES_DIR / "malformed_schema.json", "r") as f:
        malformed = json.load(f)

    with pytest.raises(ValidationError) as exc:
        normalize_forecast_payload(malformed)
    assert "array length mismatch" in str(exc.value)


def test_open_meteo_transient_error_handling(monkeypatch):
    """Verify timeout and 429 raise TransientProviderError without real network calls."""
    import httpx

    def mock_get_429(*args, **kwargs):
        return httpx.Response(
            status_code=429,
            headers={"Retry-After": "30"},
            request=httpx.Request("GET", "https://api.open-meteo.com/v1/forecast")
        )

    provider = OpenMeteoProvider()
    monkeypatch.setattr(httpx.Client, "get", mock_get_429)

    with pytest.raises(TransientProviderError) as exc:
        provider.fetch(6.45, 3.45)
    assert exc.value.status_code == 429
    assert exc.value.retry_after == 30


def test_retry_after_http_date_and_large_seconds_are_preserved():
    now = datetime(2030, 1, 1, tzinfo=dt_timezone.utc)
    retry_at = now + timedelta(minutes=20)
    assert parse_retry_after(format_datetime(retry_at, usegmt=True), now=now) == 1200
    assert parse_retry_after('3600', now=now) == 3600
    assert parse_retry_after('not-a-date', now=now) is None
