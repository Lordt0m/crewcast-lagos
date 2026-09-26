import json
import logging
from email.utils import parsedate_to_datetime
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone as dt_timezone
from math import ceil
import httpx
from django.conf import settings
from .normalizer import normalize_forecast_payload, NormalizedForecast

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUESTED_HOURLY_VARIABLES = [
    "precipitation_probability",
    "precipitation",
    "wind_gusts_10m",
    "apparent_temperature",
]


def parse_retry_after(value: str | None, now: datetime | None = None) -> int | None:
    """Accept Retry-After seconds or an HTTP date; ignore invalid values."""
    if not value:
        return None
    value = value.strip()
    if value.isdecimal():
        return int(value)
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=dt_timezone.utc)
    if now is None:
        now = datetime.now(dt_timezone.utc)
    return max(0, ceil((retry_at - now).total_seconds()))


class ForecastProviderError(Exception):
    """Base error for weather provider failures."""
    def __init__(self, message: str, status_code: Optional[int] = None, retry_after: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class TransientProviderError(ForecastProviderError):
    """Recoverable failure: timeout, 429 rate limit, or 5xx server error."""
    pass


class PermanentProviderError(ForecastProviderError):
    """Non-recoverable failure: 4xx (non-429), malformed response, or invalid coordinates."""
    pass


class ForecastProvider(ABC):
    """Abstract interface for forecast retrieval."""

    @abstractmethod
    def fetch(self, latitude: float, longitude: float, now: Optional[datetime] = None) -> dict:
        """Retrieve raw forecast payload."""
        pass


class OpenMeteoProvider(ForecastProvider):
    """Concrete adapter for Open-Meteo API using requested 4 hourly variables."""

    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def fetch(self, latitude: float, longitude: float, now: Optional[datetime] = None) -> dict:
        params = {
            "latitude": f"{latitude:.6f}",
            "longitude": f"{longitude:.6f}",
            "hourly": ",".join(REQUESTED_HOURLY_VARIABLES),
            "timezone": "Africa/Lagos",
            "forecast_days": 7,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(OPEN_METEO_URL, params=params)

                if response.status_code == 429:
                    retry_seconds = parse_retry_after(response.headers.get("Retry-After"))
                    if retry_seconds is None:
                        retry_seconds = 60
                    raise TransientProviderError(
                        f"Open-Meteo rate limit reached (HTTP 429). Retry after {retry_seconds}s.",
                        status_code=429,
                        retry_after=retry_seconds
                    )

                if 500 <= response.status_code < 600:
                    raise TransientProviderError(
                        f"Open-Meteo upstream error (HTTP {response.status_code}).",
                        status_code=response.status_code,
                        retry_after=parse_retry_after(response.headers.get("Retry-After")),
                    )

                if 400 <= response.status_code < 500:
                    raise PermanentProviderError(
                        f"Open-Meteo client error (HTTP {response.status_code}): {response.text}",
                        status_code=response.status_code
                    )

                response.raise_for_status()
                return response.json()

        except httpx.TimeoutException as exc:
            raise TransientProviderError(f"Open-Meteo request timed out: {exc}")
        except httpx.NetworkError as exc:
            raise TransientProviderError(f"Open-Meteo network error: {exc}")
        except json.JSONDecodeError as exc:
            raise PermanentProviderError(f"Failed to parse Open-Meteo response as JSON: {exc}")


class FixtureProvider(ForecastProvider):
    """Deterministic provider that reads saved fixture payloads without network access."""

    def __init__(self, fixture_path: Path):
        self.fixture_path = Path(fixture_path)

    def fetch(self, latitude: float, longitude: float, now: Optional[datetime] = None) -> dict:
        if not self.fixture_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {self.fixture_path}")
        with open(self.fixture_path, 'r', encoding='utf-8') as f:
            return json.load(f)
