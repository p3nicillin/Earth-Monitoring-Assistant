"""Adaptive anomaly detections driven by learned baselines.

These complement (never replace) the published-scale static detectors in
app/services/spot_detections.py: a reading must exceed the *learned*
threshold, which by construction is at least as strict as the published
floor. Severity upgrades to "warning" only when the reading also clears the
static floor, so tightened local thresholds surface early warnings without
inflating alarm levels.
"""

from datetime import datetime

from app.learning.metrics import METRICS_BY_KEY
from app.schemas.insights import MetricBaseline
from app.schemas.solar_system import Severity, SpaceWeather, SpotDetection

DETECTOR_NAME = "adaptive-baseline"
DETECTOR_VERSION = "1.0.0"


def _current_reading(weather: SpaceWeather, metric: str) -> tuple[datetime, float] | None:
    if metric == "kp" and weather.kp_index:
        entry = weather.kp_index[-1]
        return entry.time_tag, entry.kp
    if metric == "xray_long_wm2" and weather.xray_flux:
        point = weather.xray_flux[-1]
        return point.time_tag, point.flux_watts_m2
    wind = weather.current_solar_wind
    if metric == "solar_wind_speed_kms" and wind is not None and wind.speed_km_s is not None:
        return wind.time_tag, wind.speed_km_s
    if metric == "solar_wind_bz_nt" and wind is not None and wind.bz_nt is not None:
        return wind.time_tag, wind.bz_nt
    if metric == "proton_flux_10mev_pfu" and weather.proton_flux_10mev_pfu is not None:
        return weather.generated_at, weather.proton_flux_10mev_pfu
    return None


def detect_adaptive_anomalies(
    weather: SpaceWeather, baselines: list[MetricBaseline]
) -> list[SpotDetection]:
    detections: list[SpotDetection] = []
    for baseline in baselines:
        spec = METRICS_BY_KEY.get(baseline.metric)
        threshold = baseline.adaptive_threshold
        if spec is None or threshold is None:
            continue
        reading = _current_reading(weather, baseline.metric)
        if reading is None:
            continue
        observed_at, value = reading
        if spec.direction == "high":
            anomalous = value >= threshold
            beyond_floor = value >= spec.published_floor
        else:
            anomalous = value <= threshold
            beyond_floor = value <= spec.published_floor
        if not anomalous:
            continue
        severity: Severity = "warning" if beyond_floor else "watch"
        detections.append(
            SpotDetection(
                id=f"adaptive:{baseline.metric}:{observed_at.isoformat()}",
                detector=DETECTOR_NAME,
                detector_version=DETECTOR_VERSION,
                category="adaptive_anomaly",
                severity=severity,
                body=spec.body,
                title=f"{spec.title} beyond learned baseline",
                summary=(
                    f"{spec.title} is {value:g} {spec.unit}, beyond the learned "
                    f"{baseline.window_days}-day threshold of {threshold:g} {spec.unit} "
                    f"(from {baseline.sample_count} locally recorded samples)."
                ),
                observed_at=observed_at,
                source="TerraLens adaptive baseline (local archive)",
                metrics={
                    "value": value,
                    "learned_threshold": threshold,
                    "published_floor": spec.published_floor,
                    "sample_count": baseline.sample_count,
                    "baseline_maturity": baseline.maturity,
                },
            )
        )
    return detections
