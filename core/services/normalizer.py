import hashlib
import json
from decimal import Decimal
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError

LAGOS_TZ = ZoneInfo("Africa/Lagos")

REQUIRED_HOURLY_FIELDS = [
    "time",
    "precipitation_probability",
    "precipitation",
    "wind_gusts_10m",
    "apparent_temperature",
]


class NormalizedForecast:
    """Holds normalized and validated forecast values ready for persistence or evaluation."""
    def __init__(
        self,
        content_hash: str,
        returned_latitude: Decimal,
        returned_longitude: Decimal,
        returned_elevation: float,
        hourly_data: dict,
        coverage_start: datetime,
        coverage_end: datetime,
        hours_count: int,
    ):
        self.content_hash = content_hash
        self.returned_latitude = returned_latitude
        self.returned_longitude = returned_longitude
        self.returned_elevation = returned_elevation
        self.hourly_data = hourly_data
        self.coverage_start = coverage_start
        self.coverage_end = coverage_end
        self.hours_count = hours_count

    def to_dict(self):
        return {
            'content_hash': self.content_hash,
            'returned_latitude': str(self.returned_latitude),
            'returned_longitude': str(self.returned_longitude),
            'returned_elevation': self.returned_elevation,
            'coverage_start': self.coverage_start.isoformat(),
            'coverage_end': self.coverage_end.isoformat(),
            'hours_count': self.hours_count,
            'hourly_data': self.hourly_data,
        }


def normalize_forecast_payload(raw_payload: dict, min_hours: int = 1) -> NormalizedForecast:
    """
    Validates and normalizes raw Open-Meteo forecast JSON response:
    - Verifies schema and required keys
    - Verifies array lengths match across all required metrics
    - Converts Africa/Lagos times to UTC-aware datetimes
    - Preserves returned grid coordinates separately
    - Does NOT use generationtime_ms as an issue timestamp
    - Generates a deterministic SHA-256 hash of the normalized hourly series
    """
    if not isinstance(raw_payload, dict):
        raise ValidationError("Raw payload must be a JSON dictionary.")

    for key in ("latitude", "longitude", "hourly"):
        if key not in raw_payload:
            raise ValidationError(f"Missing required top-level field: '{key}'.")

    hourly = raw_payload.get("hourly")
    if not isinstance(hourly, dict):
        raise ValidationError("Field 'hourly' must be a dictionary.")

    for field in REQUIRED_HOURLY_FIELDS:
        if field not in hourly:
            raise ValidationError(f"Missing required hourly field: '{field}'.")
        if not isinstance(hourly[field], list):
            raise ValidationError(f"Hourly field '{field}' must be a list.")

    times = hourly["time"]
    num_hours = len(times)

    if num_hours < min_hours:
        raise ValidationError(f"Forecast coverage insufficient: received {num_hours} hours, expected at least {min_hours}.")

    # Validate all array lengths match
    for field in REQUIRED_HOURLY_FIELDS:
        if len(hourly[field]) != num_hours:
            raise ValidationError(
                f"Hourly array length mismatch: 'time' has {num_hours} items but '{field}' has {len(hourly[field])} items."
            )

    returned_lat = Decimal(str(raw_payload["latitude"]))
    returned_lon = Decimal(str(raw_payload["longitude"]))
    returned_elev = float(raw_payload.get("elevation", 0.0))

    # Parse and normalize times to UTC-aware ISO timestamps
    normalized_hourly = {}
    parsed_datetimes = []

    for i in range(num_hours):
        time_str = times[i]
        # Open-Meteo returns 'YYYY-MM-DDTHH:MM' in requested timezone (Africa/Lagos)
        try:
            local_dt = datetime.fromisoformat(time_str)
            if local_dt.tzinfo is None:
                local_dt = local_dt.replace(tzinfo=LAGOS_TZ)
            utc_dt = local_dt.astimezone(dt_timezone.utc)
        except Exception as exc:
            raise ValidationError(f"Invalid timestamp format '{time_str}': {exc}")

        parsed_datetimes.append(utc_dt)
        utc_iso = utc_dt.isoformat()

        # Validate numeric metrics
        prob = hourly["precipitation_probability"][i]
        precip = hourly["precipitation"][i]
        gusts = hourly["wind_gusts_10m"][i]
        temp = hourly["apparent_temperature"][i]

        for val_name, val in (("precipitation_probability", prob),
                             ("precipitation", precip),
                             ("wind_gusts_10m", gusts),
                             ("apparent_temperature", temp)):
            if val is not None and not isinstance(val, (int, float)):
                raise ValidationError(f"Non-numeric value in '{val_name}' at index {i}: {val}")

        normalized_hourly[utc_iso] = {
            "precipitation_probability": prob,
            "precipitation": float(precip) if precip is not None else None,
            "wind_gusts_10m": float(gusts) if gusts is not None else None,
            "apparent_temperature": float(temp) if temp is not None else None,
        }

    # Verify timestamps are strictly ascending
    for i in range(1, len(parsed_datetimes)):
        if parsed_datetimes[i] <= parsed_datetimes[i-1]:
            raise ValidationError(f"Timestamps must be strictly ascending: {parsed_datetimes[i-1]} >= {parsed_datetimes[i]}")

    # Compute deterministic SHA-256 hash of canonical normalized hourly data
    # Notice: metadata like generationtime_ms is intentionally excluded from the content hash
    canonical_repr = json.dumps(normalized_hourly, sort_keys=True, separators=(',', ':'))
    content_hash = hashlib.sha256(canonical_repr.encode('utf-8')).hexdigest()

    coverage_start = parsed_datetimes[0]
    coverage_end = parsed_datetimes[-1]

    return NormalizedForecast(
        content_hash=content_hash,
        returned_latitude=returned_lat,
        returned_longitude=returned_lon,
        returned_elevation=returned_elev,
        hourly_data=normalized_hourly,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        hours_count=num_hours,
    )
