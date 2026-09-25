from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Any

LAGOS_TZ = ZoneInfo("Africa/Lagos")


@dataclass(frozen=True)
class CrossedThresholdReason:
    metric: str
    level: str  # "caution" or "stop"
    observed_value: float
    threshold_value: float
    unit: str
    hour_label_wat: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "level": self.level,
            "observed_value": self.observed_value,
            "threshold_value": self.threshold_value,
            "unit": self.unit,
            "hour_label_wat": self.hour_label_wat,
            "message": self.message,
        }


@dataclass(frozen=True)
class EvaluationResult:
    status: str  # "suitable", "caution", "unsuitable", "unavailable"
    reasons: list[dict[str, Any]]
    max_metrics: dict[str, float | None]
    evaluated_hours_wat: list[str]
    missing_hours_utc: list[str] = field(default_factory=list)


def get_intersecting_hour_instants(job_start_utc: datetime, job_end_utc: datetime) -> list[datetime]:
    """
    Computes all UTC hourly forecast instants that overlap the job window [start, end].
    Each hourly forecast point at T represents either:
    - the preceding hour interval (T - 1h to T) for precipitation and gusts
    - the instant T for apparent temperature
    Conservatively includes any hourly slot that intersects [job_start_utc, job_end_utc].
    """
    if job_start_utc.tzinfo is None:
        job_start_utc = job_start_utc.replace(tzinfo=dt_timezone.utc)
    else:
        job_start_utc = job_start_utc.astimezone(dt_timezone.utc)

    if job_end_utc.tzinfo is None:
        job_end_utc = job_end_utc.replace(tzinfo=dt_timezone.utc)
    else:
        job_end_utc = job_end_utc.astimezone(dt_timezone.utc)

    # Floor start to previous full hour, ceil end to next full hour
    start_hour = job_start_utc.replace(minute=0, second=0, microsecond=0)
    
    # If job ends exactly on the hour, that hour is the end boundary; otherwise step to next hour
    if job_end_utc.minute == 0 and job_end_utc.second == 0 and job_end_utc.microsecond == 0:
        end_hour = job_end_utc
    else:
        end_hour = job_end_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    instants = []
    curr = start_hour
    while curr <= end_hour:
        instants.append(curr)
        curr += timedelta(hours=1)

    return instants


def evaluate_forecast(
    job_start_utc: datetime,
    job_end_utc: datetime,
    policy_thresholds: dict[str, Any],
    hourly_data: dict[str, dict[str, Any]],
) -> EvaluationResult:
    """
    Pure evaluation function.
    - Takes job window (start, end in UTC), policy thresholds, and normalized hourly forecast dictionary.
    - Identifies all intersecting hours.
    - If any hour or metric is missing, returns 'unavailable'.
    - Aggregates maximum values across intersecting hours.
    - Compares against stop thresholds (unsuitable) and caution thresholds (caution).
    - Returns structured EvaluationResult with detailed reasons.
    """
    intersecting_instants = get_intersecting_hour_instants(job_start_utc, job_end_utc)

    # Check for missing coverage
    missing_hours = []
    evaluated_entries = []

    for instant in intersecting_instants:
        iso_key = instant.isoformat()
        # Handle trailing Z or +00:00 matching
        matched_key = None
        if iso_key in hourly_data:
            matched_key = iso_key
        else:
            # Try alternate UTC representations
            alt_key_z = iso_key.replace("+00:00", "Z")
            alt_key_offset = iso_key.replace("Z", "+00:00")
            if alt_key_z in hourly_data:
                matched_key = alt_key_z
            elif alt_key_offset in hourly_data:
                matched_key = alt_key_offset

        if not matched_key:
            missing_hours.append(instant.isoformat())
        else:
            entry = hourly_data[matched_key]
            # Ensure none of the 4 metrics are None
            if any(entry.get(m) is None for m in ("precipitation_probability", "precipitation", "wind_gusts_10m", "apparent_temperature")):
                missing_hours.append(instant.isoformat())
            else:
                evaluated_entries.append((instant, entry))

    if missing_hours:
        return EvaluationResult(
            status="unavailable",
            reasons=[{
                "metric": "coverage",
                "level": "unavailable",
                "message": "Forecast data does not cover the complete job window.",
                "observed_value": None,
                "threshold_value": None,
                "unit": "",
                "hour_label_wat": "",
            }],
            max_metrics={
                "precipitation_probability": None,
                "precipitation": None,
                "wind_gusts_10m": None,
                "apparent_temperature": None,
            },
            evaluated_hours_wat=[],
            missing_hours_utc=missing_hours,
        )

    # Aggregate maxima and collect crossed thresholds
    max_prob = -1.0
    max_precip = -1.0
    max_gusts = -1.0
    max_temp = -999.0

    stop_reasons: list[dict[str, Any]] = []
    caution_reasons: list[dict[str, Any]] = []
    evaluated_hours_wat = []

    # Threshold values from policy dict
    p_prob_c = float(policy_thresholds.get("rain_prob_caution", 40))
    p_prob_s = float(policy_thresholds.get("rain_prob_stop", 70))
    p_precip_c = float(policy_thresholds.get("precip_caution_mm", 2.0))
    p_precip_s = float(policy_thresholds.get("precip_stop_mm", 5.0))
    p_gust_c = float(policy_thresholds.get("gust_caution_kmh", 25.0))
    p_gust_s = float(policy_thresholds.get("gust_stop_kmh", 40.0))
    p_temp_c = float(policy_thresholds.get("apparent_temp_caution_c", 30.0))
    p_temp_s = float(policy_thresholds.get("apparent_temp_stop_c", 35.0))

    for instant, metrics in evaluated_entries:
        instant_lagos = instant.astimezone(LAGOS_TZ)
        hour_start_str = (instant_lagos - timedelta(hours=1)).strftime("%H:%M")
        hour_end_str = instant_lagos.strftime("%H:%M")
        hour_label = f"{hour_start_str}–{hour_end_str} WAT"
        evaluated_hours_wat.append(hour_label)

        prob = float(metrics["precipitation_probability"])
        precip = float(metrics["precipitation"])
        gusts = float(metrics["wind_gusts_10m"])
        temp = float(metrics["apparent_temperature"])

        if prob > max_prob:
            max_prob = prob
        if precip > max_precip:
            max_precip = precip
        if gusts > max_gusts:
            max_gusts = gusts
        if temp > max_temp:
            max_temp = temp

        # Check Stop thresholds
        if prob >= p_prob_s:
            stop_reasons.append(CrossedThresholdReason(
                metric="precipitation_probability", level="stop", observed_value=prob, threshold_value=p_prob_s,
                unit="%", hour_label_wat=hour_label,
                message=f"Rain probability reached {prob:.0f}% (stop: {p_prob_s:.0f}%) during {hour_label}"
            ).to_dict())
        elif prob >= p_prob_c:
            caution_reasons.append(CrossedThresholdReason(
                metric="precipitation_probability", level="caution", observed_value=prob, threshold_value=p_prob_c,
                unit="%", hour_label_wat=hour_label,
                message=f"Rain probability reached {prob:.0f}% (caution: {p_prob_c:.0f}%) during {hour_label}"
            ).to_dict())

        if precip >= p_precip_s:
            stop_reasons.append(CrossedThresholdReason(
                metric="precipitation", level="stop", observed_value=precip, threshold_value=p_precip_s,
                unit="mm/h", hour_label_wat=hour_label,
                message=f"Precipitation reached {precip:.1f} mm/h (stop: {p_precip_s:.1f} mm/h) during {hour_label}"
            ).to_dict())
        elif precip >= p_precip_c:
            caution_reasons.append(CrossedThresholdReason(
                metric="precipitation", level="caution", observed_value=precip, threshold_value=p_precip_c,
                unit="mm/h", hour_label_wat=hour_label,
                message=f"Precipitation reached {precip:.1f} mm/h (caution: {p_precip_c:.1f} mm/h) during {hour_label}"
            ).to_dict())

        if gusts >= p_gust_s:
            stop_reasons.append(CrossedThresholdReason(
                metric="wind_gusts_10m", level="stop", observed_value=gusts, threshold_value=p_gust_s,
                unit="km/h", hour_label_wat=hour_label,
                message=f"Wind gusts reached {gusts:.1f} km/h (stop: {p_gust_s:.1f} km/h) during {hour_label}"
            ).to_dict())
        elif gusts >= p_gust_c:
            caution_reasons.append(CrossedThresholdReason(
                metric="wind_gusts_10m", level="caution", observed_value=gusts, threshold_value=p_gust_c,
                unit="km/h", hour_label_wat=hour_label,
                message=f"Wind gusts reached {gusts:.1f} km/h (caution: {p_gust_c:.1f} km/h) during {hour_label}"
            ).to_dict())

        if temp >= p_temp_s:
            stop_reasons.append(CrossedThresholdReason(
                metric="apparent_temperature", level="stop", observed_value=temp, threshold_value=p_temp_s,
                unit="°C", hour_label_wat=hour_label,
                message=f"Apparent temperature reached {temp:.1f} °C (stop: {p_temp_s:.1f} °C) during {hour_label}"
            ).to_dict())
        elif temp >= p_temp_c:
            caution_reasons.append(CrossedThresholdReason(
                metric="apparent_temperature", level="caution", observed_value=temp, threshold_value=p_temp_c,
                unit="°C", hour_label_wat=hour_label,
                message=f"Apparent temperature reached {temp:.1f} °C (caution: {p_temp_c:.1f} °C) during {hour_label}"
            ).to_dict())

    max_metrics = {
        "precipitation_probability": max_prob,
        "precipitation": max_precip,
        "wind_gusts_10m": max_gusts,
        "apparent_temperature": max_temp,
    }

    if stop_reasons:
        return EvaluationResult(
            status="unsuitable",
            reasons=stop_reasons + caution_reasons,
            max_metrics=max_metrics,
            evaluated_hours_wat=evaluated_hours_wat,
        )
    elif caution_reasons:
        return EvaluationResult(
            status="caution",
            reasons=caution_reasons,
            max_metrics=max_metrics,
            evaluated_hours_wat=evaluated_hours_wat,
        )
    else:
        return EvaluationResult(
            status="suitable",
            reasons=[],
            max_metrics=max_metrics,
            evaluated_hours_wat=evaluated_hours_wat,
        )
