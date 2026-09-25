import json
from datetime import datetime, timedelta
from pathlib import Path

fixtures_dir = Path(__file__).resolve().parent

# Base start: 2026-09-25T00:00
start = datetime(2026, 9, 25, 0, 0)
hours_168 = [start + timedelta(hours=i) for i in range(168)]
times = [h.strftime("%Y-%m-%dT%H:%M") for h in hours_168]

# 1. normal_7day.json
normal_7day = {
    "latitude": 6.45,
    "longitude": 3.45,
    "generationtime_ms": 0.245,
    "utc_offset_seconds": 3600,
    "timezone": "Africa/Lagos",
    "timezone_abbreviation": "WAT",
    "elevation": 10.0,
    "hourly_units": {
        "time": "iso8601",
        "precipitation_probability": "%",
        "precipitation": "mm",
        "wind_gusts_10m": "km/h",
        "apparent_temperature": "°C"
    },
    "hourly": {
        "time": times,
        "precipitation_probability": [(i * 7) % 85 for i in range(168)],
        "precipitation": [round(((i % 12) * 0.4), 2) for i in range(168)],
        "wind_gusts_10m": [round(15.0 + ((i % 24) * 0.8), 1) for i in range(168)],
        "apparent_temperature": [round(25.0 + ((i % 24) * 0.4), 1) for i in range(168)]
    }
}
with open(fixtures_dir / "normal_7day.json", "w") as f:
    json.dump(normal_7day, f, indent=2)

# 2. partial_coverage.json (only 48 hours instead of 168)
partial_coverage = {
    "latitude": 6.45,
    "longitude": 3.45,
    "generationtime_ms": 0.111,
    "timezone": "Africa/Lagos",
    "elevation": 10.0,
    "hourly_units": normal_7day["hourly_units"],
    "hourly": {
        "time": times[:48],
        "precipitation_probability": normal_7day["hourly"]["precipitation_probability"][:48],
        "precipitation": normal_7day["hourly"]["precipitation"][:48],
        "wind_gusts_10m": normal_7day["hourly"]["wind_gusts_10m"][:48],
        "apparent_temperature": normal_7day["hourly"]["apparent_temperature"][:48]
    }
}
with open(fixtures_dir / "partial_coverage.json", "w") as f:
    json.dump(partial_coverage, f, indent=2)

# 3. malformed_schema.json (mismatched array length)
malformed_schema = {
    "latitude": 6.45,
    "longitude": 3.45,
    "hourly_units": normal_7day["hourly_units"],
    "hourly": {
        "time": times[:24],
        "precipitation_probability": [10, 20], # Length 2 vs 24
        "precipitation": [0.0] * 24,
        "wind_gusts_10m": [15.0] * 24,
        "apparent_temperature": [28.0] * 24
    }
}
with open(fixtures_dir / "malformed_schema.json", "w") as f:
    json.dump(malformed_schema, f, indent=2)

# 4. drift_payload.json (same timestamps, changed values to test hash differentiation)
drift_payload = json.loads(json.dumps(normal_7day))
drift_payload["generationtime_ms"] = 99.999 # Should NOT affect hash
drift_payload["hourly"]["precipitation_probability"][10] = 95 # Changed weather value
with open(fixtures_dir / "drift_payload.json", "w") as f:
    json.dump(drift_payload, f, indent=2)

print("Generated all fixtures successfully.")
