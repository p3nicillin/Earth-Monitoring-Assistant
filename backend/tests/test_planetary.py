from app.core.config import Settings
from app.services.planetary import PlanetaryOperationsService, mission_profile


def omm(name: str, catalog_id: int) -> dict[str, object]:
    return {
        "OBJECT_NAME": name,
        "OBJECT_ID": f"2020-{catalog_id % 1000:03d}A",
        "EPOCH": "2026-07-01T03:08:19.35312",
        "MEAN_MOTION": 14.3,
        "ECCENTRICITY": 0.0001,
        "INCLINATION": 98.5,
        "RA_OF_ASC_NODE": 256.7,
        "ARG_OF_PERICENTER": 95.2,
        "MEAN_ANOMALY": 264.8,
        "EPHEMERIS_TYPE": 0,
        "CLASSIFICATION_TYPE": "U",
        "NORAD_CAT_ID": catalog_id,
        "ELEMENT_SET_NO": 999,
        "REV_AT_EPOCH": 57572,
        "BSTAR": -3.4e-5,
        "MEAN_MOTION_DOT": -1.3e-6,
        "MEAN_MOTION_DDOT": 0,
    }


def test_mission_profiles_expose_instrument_and_swath_metadata() -> None:
    sentinel = mission_profile("SENTINEL-2A")
    goes = mission_profile("GOES 19")
    assert sentinel.instruments == ["MSI"]
    assert sentinel.nominal_swath_km == 290
    assert goes.instruments == ["ABI", "GLM"]
    assert goes.orbit_class == "Geostationary"


def test_catalog_selection_filters_and_balances_planet_constellations() -> None:
    settings = Settings(planet_satellite_limit=10)
    service = PlanetaryOperationsService(settings)
    records = [omm("SENTINEL-2A", 40697), omm("UNRELATED SAT", 50000)]
    records.extend(omm(f"SKYSAT-C{index}", 51000 + index) for index in range(12))
    records.extend(omm(f"FLOCK-4P-{index}", 52000 + index) for index in range(5))
    selected = service._select_satellites([records])
    names = {satellite.name for satellite in selected}
    assert "SENTINEL-2A" in names
    assert "UNRELATED SAT" not in names
    assert sum(name.startswith("SKYSAT") for name in names) == 8
    assert sum(name.startswith("FLOCK") for name in names) == 2


def test_usgs_geojson_is_normalized_to_bounded_features() -> None:
    service = PlanetaryOperationsService(Settings())
    payload = {
        "features": [
            {
                "id": "quake-1",
                "geometry": {"coordinates": [-122.4, 37.8, 12.5]},
                "properties": {
                    "title": "M 4.2 - Test",
                    "mag": 4.2,
                    "time": 1_782_860_400_000,
                    "url": "https://earthquake.usgs.gov/example",
                    "tsunami": 0,
                    "place": "Test region",
                    "sig": 300,
                },
            },
            {"id": "invalid"},
        ]
    }
    features = service._normalize_earthquakes(payload)
    assert len(features) == 1
    assert features[0].magnitude == 4.2
    assert features[0].depth_km == 12.5
    assert features[0].tsunami is False
