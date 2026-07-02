from datetime import UTC, datetime, timedelta

from app.schemas.planetary import EarthquakeFeature, EarthquakeFeed
from app.schemas.solar_system import (
    EarthEvent,
    EarthEventFeed,
    FlareEvent,
    KpEntry,
    NeoApproach,
    NeoFeed,
    SolarWindPoint,
    SpaceWeather,
    XrayFluxPoint,
)
from app.services import spot_detections

NOW = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


def build_weather(
    flux: float | None = None,
    kp: float | None = None,
    wind: SolarWindPoint | None = None,
    flare: FlareEvent | None = None,
    protons: float | None = None,
) -> SpaceWeather:
    xray = [XrayFluxPoint(time_tag=NOW, flux_watts_m2=flux)] if flux is not None else []
    return SpaceWeather(
        source="test",
        generated_at=NOW,
        cache_expires_at=NOW,
        xray_flux=xray,
        current_xray_class=spot_detections.classify_xray_flux(flux) if flux is not None else None,
        latest_flare=flare,
        kp_index=[KpEntry(time_tag=NOW, kp=kp)] if kp is not None else [],
        current_kp=kp,
        solar_wind=[wind] if wind is not None else [],
        current_solar_wind=wind,
        proton_flux_10mev_pfu=protons,
    )


def quake(magnitude: float, minutes_ago: int = 30) -> EarthquakeFeature:
    return EarthquakeFeature(
        id=f"us{magnitude}",
        title=f"M {magnitude} - somewhere",
        magnitude=magnitude,
        occurred_at=NOW - timedelta(minutes=minutes_ago),
        longitude=140.1,
        latitude=35.6,
        depth_km=10.0,
        detail_url=None,
        tsunami=False,
        place="somewhere",
    )


def quake_feed(*features: EarthquakeFeature) -> EarthquakeFeed:
    return EarthquakeFeed(
        source="test",
        generated_at=NOW,
        cache_expires_at=NOW,
        count=len(features),
        earthquakes=list(features),
    )


def neo(distance_lunar: float, h: float | None = 25.0) -> NeoApproach:
    return NeoApproach(
        designation="2026 AB",
        close_approach_at=NOW + timedelta(days=2),
        distance_au=distance_lunar * 0.00256955529,
        distance_lunar=distance_lunar,
        velocity_km_s=12.5,
        absolute_magnitude_h=h,
        estimated_diameter_m=140.0,
    )


def neo_feed(*approaches: NeoApproach) -> NeoFeed:
    return NeoFeed(
        source="test",
        generated_at=NOW,
        cache_expires_at=NOW,
        lookahead_days=7,
        count=len(approaches),
        approaches=list(approaches),
    )


def test_xray_classification_covers_all_bands() -> None:
    assert spot_detections.classify_xray_flux(3.0e-9) == "A0.3"
    assert spot_detections.classify_xray_flux(5.0e-7) == "B5.0"
    assert spot_detections.classify_xray_flux(2.5e-6) == "C2.5"
    assert spot_detections.classify_xray_flux(5.2e-5) == "M5.2"
    assert spot_detections.classify_xray_flux(1.4e-4) == "X1.4"
    assert spot_detections.classify_xray_flux(9.0e-3) == "X9.9"


def test_flare_detector_thresholds() -> None:
    assert spot_detections.detect_solar_flares(build_weather(flux=5e-8)) == []
    watch = spot_detections.detect_solar_flares(build_weather(flux=2e-6))
    assert [item.severity for item in watch] == ["watch"]
    critical = spot_detections.detect_solar_flares(build_weather(flux=2e-4))
    assert [item.severity for item in critical] == ["critical"]
    assert critical[0].metrics["xray_class"] == "X2.0"


def test_flare_event_detection_reports_in_progress_state() -> None:
    flare = FlareEvent(
        began_at=NOW - timedelta(minutes=15),
        peaked_at=NOW - timedelta(minutes=5),
        ended_at=None,
        max_class="M3.4",
        in_progress=True,
    )
    detections = spot_detections.detect_solar_flares(build_weather(flare=flare))
    assert len(detections) == 1
    assert detections[0].severity == "warning"
    assert "in progress" in detections[0].title


def test_geomagnetic_storm_scale_mapping() -> None:
    assert spot_detections.detect_geomagnetic_storm(build_weather(kp=4.0)) == []
    g1 = spot_detections.detect_geomagnetic_storm(build_weather(kp=5.0))
    assert g1[0].severity == "watch" and g1[0].metrics["noaa_scale"] == "G1"
    g3 = spot_detections.detect_geomagnetic_storm(build_weather(kp=7.3))
    assert g3[0].severity == "warning" and g3[0].metrics["noaa_scale"] == "G3"
    g5 = spot_detections.detect_geomagnetic_storm(build_weather(kp=9.0))
    assert g5[0].severity == "critical" and g5[0].metrics["noaa_scale"] == "G5"


def test_solar_wind_detector_flags_speed_and_southward_bz() -> None:
    calm = SolarWindPoint(time_tag=NOW, speed_km_s=420.0, bz_nt=2.0)
    assert spot_detections.detect_solar_wind_anomaly(build_weather(wind=calm)) == []
    stormy = SolarWindPoint(time_tag=NOW, speed_km_s=820.0, bz_nt=-22.0, bt_nt=25.0)
    detections = spot_detections.detect_solar_wind_anomaly(build_weather(wind=stormy))
    severities = {item.id.split(":")[1]: item.severity for item in detections}
    assert severities == {"speed": "critical", "bz": "warning"}


def test_radiation_storm_scale() -> None:
    assert spot_detections.detect_radiation_storm(build_weather(protons=2.0)) == []
    s1 = spot_detections.detect_radiation_storm(build_weather(protons=15.0))
    assert s1[0].metrics["noaa_scale"] == "S1" and s1[0].severity == "watch"
    s3 = spot_detections.detect_radiation_storm(build_weather(protons=5000.0))
    assert s3[0].metrics["noaa_scale"] == "S3" and s3[0].severity == "warning"


def test_earthquake_detector_thresholds_and_recency() -> None:
    feed = quake_feed(
        quake(4.0),
        quake(4.8),
        quake(5.9),
        quake(7.1),
        quake(7.9, minutes_ago=60 * 30),  # older than 24 hours
    )
    detections = spot_detections.detect_significant_earthquakes(feed, NOW)
    assert [item.severity for item in detections] == ["watch", "warning", "critical"]
    assert all(item.latitude == 35.6 for item in detections)


def test_neo_detector_uses_distance_and_size() -> None:
    far_small = neo(distance_lunar=15.0, h=26.0)
    assert spot_detections.detect_neo_close_approaches(neo_feed(far_small)) == []
    inside_moon = neo(distance_lunar=0.8)
    close = neo(distance_lunar=4.0)
    large_far = neo(distance_lunar=15.0, h=21.0)
    detections = spot_detections.detect_neo_close_approaches(
        neo_feed(inside_moon, close, large_far)
    )
    assert [item.severity for item in detections] == ["warning", "watch", "watch"]


def test_earth_event_detector_maps_categories() -> None:
    feed = EarthEventFeed(
        source="test",
        generated_at=NOW,
        cache_expires_at=NOW,
        lookback_days=14,
        count=2,
        events=[
            EarthEvent(
                id="EONET_1",
                title="Example Fire",
                category_id="wildfires",
                category_title="Wildfires",
                longitude=-120.0,
                latitude=39.0,
                observed_at=NOW,
                magnitude_value=None,
                magnitude_unit=None,
                source_url=None,
            ),
            EarthEvent(
                id="EONET_2",
                title="Hurricane Example",
                category_id="severeStorms",
                category_title="Severe Storms",
                longitude=-75.0,
                latitude=25.0,
                observed_at=NOW,
                magnitude_value=105.0,
                magnitude_unit="kts",
                source_url=None,
            ),
        ],
    )
    detections = spot_detections.detect_earth_surface_events(feed)
    by_id = {item.id: item for item in detections}
    assert by_id["earth-event:EONET_1"].severity == "watch"
    assert by_id["earth-event:EONET_2"].severity == "critical"


def test_run_all_detectors_sorts_by_severity_then_recency() -> None:
    weather = build_weather(flux=2e-6)  # watch
    quakes = quake_feed(quake(7.0))  # critical
    detections = spot_detections.run_all_detectors(weather, quakes, None, None, NOW)
    assert [item.severity for item in detections] == ["critical", "watch"]
    assert detections[0].category == "earthquake"


def test_run_all_detectors_tolerates_missing_feeds() -> None:
    assert spot_detections.run_all_detectors(None, None, None, None) == []
