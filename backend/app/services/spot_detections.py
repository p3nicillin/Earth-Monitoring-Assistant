"""Rule-based spot detections over live solar-system feeds.

Every detector is a pure function from normalized feed data to
`SpotDetection` records, so thresholds are unit-testable without network
access. Detection identifiers are deterministic: re-running a detector over
the same upstream state yields the same ids, which lets clients deduplicate
across refreshes. Rules follow published NOAA scales (R/G/S) where one
exists; they signal operating conditions, not verified ground truth.
"""

from datetime import UTC, datetime, timedelta

from app.schemas.planetary import EarthquakeFeed
from app.schemas.solar_system import (
    EarthEvent,
    EarthEventFeed,
    NeoFeed,
    Severity,
    SpaceWeather,
    SpotDetection,
)

DETECTOR_VERSION = "1.0.0"

SEVERITY_RANK: dict[Severity, int] = {"critical": 0, "warning": 1, "watch": 2, "info": 3}

_XRAY_CLASSES = (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7))
_KP_G_SCALE: tuple[tuple[float, str, Severity], ...] = (
    (9.0, "G5", "critical"),
    (8.0, "G4", "critical"),
    (7.0, "G3", "warning"),
    (6.0, "G2", "warning"),
    (5.0, "G1", "watch"),
)
_PROTON_S_SCALE: tuple[tuple[float, str, Severity], ...] = (
    (1e5, "S5", "critical"),
    (1e4, "S4", "critical"),
    (1e3, "S3", "warning"),
    (1e2, "S2", "warning"),
    (10.0, "S1", "watch"),
)
_EONET_CATEGORY_SEVERITY: dict[str, Severity] = {
    "wildfires": "watch",
    "volcanoes": "watch",
    "severeStorms": "warning",
    "floods": "warning",
    "seaLakeIce": "info",
    "earthquakes": "watch",
    "landslides": "watch",
    "drought": "info",
    "dustHaze": "info",
    "manmade": "info",
    "snow": "info",
    "waterColor": "info",
    "tempExtremes": "watch",
}


def classify_xray_flux(flux_watts_m2: float) -> str:
    """GOES X-ray flux to flare class string, e.g. 5.2e-5 -> 'M5.2'."""
    for letter, base in _XRAY_CLASSES:
        if flux_watts_m2 >= base:
            return f"{letter}{min(flux_watts_m2 / base, 9.9):.1f}"
    return f"A{min(flux_watts_m2 / 1e-8, 9.9):.1f}"


def _flare_severity(xray_class: str) -> Severity | None:
    letter = xray_class[:1].upper()
    if letter == "X":
        return "critical"
    if letter == "M":
        return "warning"
    if letter == "C":
        return "watch"
    return None


def detect_solar_flares(weather: SpaceWeather) -> list[SpotDetection]:
    detections: list[SpotDetection] = []
    if weather.current_xray_class is not None and weather.xray_flux:
        severity = _flare_severity(weather.current_xray_class)
        latest = weather.xray_flux[-1]
        if severity is not None:
            detections.append(
                SpotDetection(
                    id=f"solar-flare:flux:{latest.time_tag.isoformat()}",
                    detector="goes-xray-flux",
                    detector_version=DETECTOR_VERSION,
                    category="solar_flare",
                    severity=severity,
                    body="sun",
                    title=f"Solar X-ray flux at {weather.current_xray_class}",
                    summary=(
                        f"GOES long-band X-ray flux is {latest.flux_watts_m2:.2e} W/m^2 "
                        f"({weather.current_xray_class}); R-scale radio blackout conditions "
                        "are possible on the sunlit side."
                    ),
                    observed_at=latest.time_tag,
                    source="NOAA SWPC GOES X-ray flux",
                    metrics={
                        "flux_watts_m2": latest.flux_watts_m2,
                        "xray_class": weather.current_xray_class,
                    },
                )
            )
    flare = weather.latest_flare
    if flare is not None and flare.max_class:
        severity = _flare_severity(flare.max_class)
        anchor = flare.peaked_at or flare.began_at
        if severity is not None and anchor is not None:
            state = "in progress" if flare.in_progress else "peaked"
            detections.append(
                SpotDetection(
                    id=f"solar-flare:event:{anchor.isoformat()}",
                    detector="goes-xray-flare-event",
                    detector_version=DETECTOR_VERSION,
                    category="solar_flare",
                    severity=severity,
                    body="sun",
                    title=f"{flare.max_class} flare {state}",
                    summary=(
                        f"GOES registered a {flare.max_class} flare "
                        f"({state}, peak {anchor.strftime('%H:%M UTC')})."
                    ),
                    observed_at=anchor,
                    source="NOAA SWPC GOES flare list",
                    metrics={"max_class": flare.max_class, "in_progress": flare.in_progress},
                )
            )
    return detections


def detect_geomagnetic_storm(weather: SpaceWeather) -> list[SpotDetection]:
    if weather.current_kp is None or not weather.kp_index:
        return []
    latest = weather.kp_index[-1]
    for threshold, scale, severity in _KP_G_SCALE:
        if weather.current_kp >= threshold:
            return [
                SpotDetection(
                    id=f"geomagnetic-storm:{latest.time_tag.isoformat()}",
                    detector="kp-index",
                    detector_version=DETECTOR_VERSION,
                    category="geomagnetic_storm",
                    severity=severity,
                    body="earth",
                    title=f"Geomagnetic storm {scale} (Kp {weather.current_kp:.1f})",
                    summary=(
                        f"Planetary K-index is {weather.current_kp:.1f}, NOAA scale {scale}. "
                        "Expect auroral expansion and possible GNSS/grid effects."
                    ),
                    observed_at=latest.time_tag,
                    source="NOAA SWPC planetary K-index",
                    metrics={"kp": weather.current_kp, "noaa_scale": scale},
                )
            ]
    return []


def detect_solar_wind_anomaly(weather: SpaceWeather) -> list[SpotDetection]:
    point = weather.current_solar_wind
    if point is None:
        return []
    detections: list[SpotDetection] = []
    if point.speed_km_s is not None and point.speed_km_s >= 600.0:
        severity: Severity = "critical" if point.speed_km_s >= 800.0 else "warning"
        detections.append(
            SpotDetection(
                id=f"solar-wind:speed:{point.time_tag.isoformat()}",
                detector="solar-wind-plasma",
                detector_version=DETECTOR_VERSION,
                category="solar_wind",
                severity=severity,
                body="interplanetary",
                title=f"High-speed solar wind ({point.speed_km_s:.0f} km/s)",
                summary=(
                    f"L1 solar wind speed is {point.speed_km_s:.0f} km/s, consistent with a "
                    "coronal-hole stream or CME passage."
                ),
                observed_at=point.time_tag,
                source="NOAA SWPC real-time solar wind",
                metrics={"speed_km_s": point.speed_km_s},
            )
        )
    if point.bz_nt is not None and point.bz_nt <= -10.0:
        severity = "warning" if point.bz_nt <= -20.0 else "watch"
        detections.append(
            SpotDetection(
                id=f"solar-wind:bz:{point.time_tag.isoformat()}",
                detector="solar-wind-imf",
                detector_version=DETECTOR_VERSION,
                category="solar_wind",
                severity=severity,
                body="interplanetary",
                title=f"Strong southward IMF (Bz {point.bz_nt:.1f} nT)",
                summary=(
                    f"Interplanetary magnetic field Bz is {point.bz_nt:.1f} nT southward, "
                    "which couples efficiently with the magnetosphere."
                ),
                observed_at=point.time_tag,
                source="NOAA SWPC real-time solar wind",
                metrics={"bz_nt": point.bz_nt, "bt_nt": point.bt_nt},
            )
        )
    return detections


def detect_radiation_storm(weather: SpaceWeather) -> list[SpotDetection]:
    flux = weather.proton_flux_10mev_pfu
    if flux is None:
        return []
    for threshold, scale, severity in _PROTON_S_SCALE:
        if flux >= threshold:
            return [
                SpotDetection(
                    id=f"radiation-storm:{weather.generated_at.isoformat()}",
                    detector="goes-proton-flux",
                    detector_version=DETECTOR_VERSION,
                    category="radiation_storm",
                    severity=severity,
                    body="earth",
                    title=f"Solar radiation storm {scale}",
                    summary=(
                        f">=10 MeV proton flux is {flux:.0f} pfu (NOAA scale {scale}); "
                        "polar HF and satellite operations may be affected."
                    ),
                    observed_at=weather.generated_at,
                    source="NOAA SWPC GOES integral protons",
                    metrics={"proton_flux_pfu": flux, "noaa_scale": scale},
                )
            ]
    return []


def detect_significant_earthquakes(
    feed: EarthquakeFeed, now: datetime | None = None
) -> list[SpotDetection]:
    reference = now or datetime.now(UTC)
    cutoff = reference - timedelta(hours=24)
    detections: list[SpotDetection] = []
    for quake in feed.earthquakes:
        if quake.magnitude is None or quake.occurred_at < cutoff:
            continue
        if quake.magnitude >= 6.5:
            severity: Severity = "critical"
        elif quake.magnitude >= 5.5:
            severity = "warning"
        elif quake.magnitude >= 4.5:
            severity = "watch"
        else:
            continue
        detections.append(
            SpotDetection(
                id=f"earthquake:{quake.id}",
                detector="usgs-significant-quake",
                detector_version=DETECTOR_VERSION,
                category="earthquake",
                severity=severity,
                body="earth",
                title=f"M{quake.magnitude:.1f} earthquake",
                summary=quake.title,
                observed_at=quake.occurred_at,
                source="USGS Earthquake Hazards Program",
                source_url=quake.detail_url,
                longitude=quake.longitude,
                latitude=quake.latitude,
                metrics={
                    "magnitude": quake.magnitude,
                    "depth_km": quake.depth_km,
                    "tsunami_flag": quake.tsunami,
                },
            )
        )
    return detections


def detect_neo_close_approaches(feed: NeoFeed) -> list[SpotDetection]:
    detections: list[SpotDetection] = []
    for approach in feed.approaches:
        large = approach.absolute_magnitude_h is not None and approach.absolute_magnitude_h <= 22.0
        if approach.distance_lunar <= 1.0:
            severity: Severity = "warning"
        elif approach.distance_lunar <= 5.0 or (large and approach.distance_lunar <= 19.5):
            severity = "watch"
        else:
            continue
        detections.append(
            SpotDetection(
                id=f"neo-approach:{approach.designation}:{approach.close_approach_at.isoformat()}",
                detector="jpl-close-approach",
                detector_version=DETECTOR_VERSION,
                category="neo_approach",
                severity=severity,
                body="interplanetary",
                title=f"{approach.designation} passes at {approach.distance_lunar:.2f} LD",
                summary=(
                    f"Near-Earth object {approach.designation} approaches within "
                    f"{approach.distance_lunar:.2f} lunar distances at "
                    f"{approach.velocity_km_s:.1f} km/s"
                    + (
                        f" (~{approach.estimated_diameter_m:.0f} m diameter est.)."
                        if approach.estimated_diameter_m is not None
                        else "."
                    )
                ),
                observed_at=approach.close_approach_at,
                source="JPL SSD close-approach data",
                source_url="https://cneos.jpl.nasa.gov/ca/",
                metrics={
                    "distance_lunar": approach.distance_lunar,
                    "distance_au": approach.distance_au,
                    "velocity_km_s": approach.velocity_km_s,
                    "estimated_diameter_m": approach.estimated_diameter_m,
                },
            )
        )
    return detections


def _earth_event_severity(event: EarthEvent) -> Severity:
    base = _EONET_CATEGORY_SEVERITY.get(event.category_id, "info")
    if (
        event.category_id == "severeStorms"
        and event.magnitude_value is not None
        and event.magnitude_unit == "kts"
        and event.magnitude_value >= 96.0
    ):
        return "critical"  # Saffir-Simpson category 3 and above
    return base


def detect_earth_surface_events(feed: EarthEventFeed) -> list[SpotDetection]:
    detections: list[SpotDetection] = []
    for event in feed.events:
        detections.append(
            SpotDetection(
                id=f"earth-event:{event.id}",
                detector="eonet-open-events",
                detector_version=DETECTOR_VERSION,
                category=event.category_id,
                severity=_earth_event_severity(event),
                body="earth",
                title=event.title,
                summary=f"{event.category_title} tracked as open by NASA EONET.",
                observed_at=event.observed_at or feed.generated_at,
                source="NASA EONET v3",
                source_url=event.source_url,
                longitude=event.longitude,
                latitude=event.latitude,
                metrics={
                    "magnitude_value": event.magnitude_value,
                    "magnitude_unit": event.magnitude_unit,
                },
            )
        )
    return detections


def run_all_detectors(
    weather: SpaceWeather | None,
    earthquakes: EarthquakeFeed | None,
    neo: NeoFeed | None,
    earth_events: EarthEventFeed | None,
    now: datetime | None = None,
) -> list[SpotDetection]:
    detections: list[SpotDetection] = []
    if weather is not None:
        detections.extend(detect_solar_flares(weather))
        detections.extend(detect_geomagnetic_storm(weather))
        detections.extend(detect_solar_wind_anomaly(weather))
        detections.extend(detect_radiation_storm(weather))
    if earthquakes is not None:
        detections.extend(detect_significant_earthquakes(earthquakes, now))
    if neo is not None:
        detections.extend(detect_neo_close_approaches(neo))
    if earth_events is not None:
        detections.extend(detect_earth_surface_events(earth_events))
    detections.sort(key=lambda item: item.observed_at, reverse=True)
    detections.sort(key=lambda item: SEVERITY_RANK[item.severity])
    return detections
