import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.config import Settings
from app.main import app
from app.schemas.planetary import EarthquakeFeed
from app.services import solar_system as solar_system_module
from app.services.feeds import FeedError, clear_feed_cache
from app.services.planetary import PlanetaryOperationsService
from app.services.solar_system import SolarSystemService, estimated_diameter_m

SETTINGS = Settings(environment="test")

XRAY_PAYLOAD = [
    {"time_tag": "2026-07-02T11:58:00Z", "flux": 1.1e-6, "energy": "0.05-0.4nm"},
    {"time_tag": "2026-07-02T11:58:00Z", "flux": 3.0e-6, "energy": "0.1-0.8nm"},
    {"time_tag": "2026-07-02T11:59:00Z", "flux": 6.2e-5, "energy": "0.1-0.8nm"},
]
FLARE_PAYLOAD = [
    {
        "begin_time": "2026-07-02T11:40:00Z",
        "max_time": "2026-07-02T11:55:00Z",
        "end_time": "Unk",
        "max_class": "M6.2",
    }
]
# Solar-wind timestamps must be fresh: stale readings are dropped from "current".
RECENT = (datetime.now(UTC) - timedelta(minutes=10)).replace(microsecond=0)
RECENT_TAG = RECENT.strftime("%Y-%m-%d %H:%M:%S.000")
PLASMA_PAYLOAD = [
    ["time_tag", "density", "speed", "temperature"],
    [RECENT_TAG, "8.2", "642.0", "250000"],
]
MAG_PAYLOAD = [
    ["time_tag", "bx_gsm", "by_gsm", "bz_gsm", "lon_gsm", "lat_gsm", "bt"],
    [RECENT_TAG, "1.0", "-3.0", "-12.5", "120.0", "-10.0", "13.1"],
]
# Live dict-row format; the header-row table format is covered separately below.
KP_PAYLOAD = [
    {"time_tag": "2026-07-02T09:00:00", "Kp": 3.67, "a_running": 18, "station_count": 8},
    {"time_tag": "2026-07-02T12:00:00", "Kp": 5.33, "a_running": 27, "station_count": 8},
]
PROTON_PAYLOAD = [
    {"time_tag": "2026-07-02T11:55:00Z", "flux": 0.31, "energy": ">=1 MeV"},
    {"time_tag": "2026-07-02T11:55:00Z", "flux": 12.0, "energy": ">=10 MeV"},
]
CAD_PAYLOAD = {
    "fields": [
        "des",
        "orbit_id",
        "jd",
        "cd",
        "dist",
        "dist_min",
        "dist_max",
        "v_rel",
        "v_inf",
        "t_sigma_f",
        "h",
    ],
    "data": [
        [
            "2026 AB",
            "1",
            "2461234.5",
            "2026-Jul-04 03:12",
            "0.00206",
            "0.002",
            "0.0021",
            "8.44",
            "8.40",
            "< 00:01",
            "24.3",
        ],
        ["broken", "1", "x", "not a date", "0.01", "0.01", "0.01", "5.0", "5.0", "< 00:01", None],
    ],
}
EONET_PAYLOAD = {
    "events": [
        {
            "id": "EONET_100",
            "title": "Example Wildfire",
            "categories": [{"id": "wildfires", "title": "Wildfires"}],
            "sources": [{"id": "IRWIN", "url": "https://example.org/fire"}],
            "geometry": [
                {"date": "2026-07-01T00:00:00Z", "type": "Point", "coordinates": [-121.5, 40.2]}
            ],
        },
        {
            "id": "EONET_200",
            "title": "Example Storm",
            "categories": [{"id": "severeStorms", "title": "Severe Storms"}],
            "sources": [],
            "geometry": [
                {
                    "date": "2026-07-02T06:00:00Z",
                    "type": "Point",
                    "coordinates": [-70.0, 24.0],
                    "magnitudeValue": 100.0,
                    "magnitudeUnit": "kts",
                }
            ],
        },
    ]
}


def fake_fetcher(
    overrides: dict[str, Any] | None = None,
) -> Callable[[Settings, str, float], Coroutine[Any, Any, Any]]:
    async def fetch(settings: Settings, url: str, ttl: float) -> Any:
        del settings, ttl
        table: dict[str, Any] = {
            "xrays-6-hour": XRAY_PAYLOAD,
            "xray-flares-latest": FLARE_PAYLOAD,
            "plasma-3-day": PLASMA_PAYLOAD,
            "mag-3-day": MAG_PAYLOAD,
            "planetary-k-index": KP_PAYLOAD,
            "integral-protons": PROTON_PAYLOAD,
            "cad.api": CAD_PAYLOAD,
            "eonet": EONET_PAYLOAD,
        }
        if overrides:
            table = {**table, **overrides}
        for fragment, payload in table.items():
            if fragment in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"Unexpected URL in test: {url}")

    return fetch


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_feed_cache()


def test_space_weather_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solar_system_module, "fetch_json_cached", fake_fetcher())
    weather = asyncio.run(SolarSystemService(SETTINGS).space_weather())
    assert weather.current_xray_class == "M6.2"
    assert [point.flux_watts_m2 for point in weather.xray_flux] == [3.0e-6, 6.2e-5]
    assert weather.latest_flare is not None
    assert weather.latest_flare.in_progress is True
    assert weather.current_kp == 5.33
    assert weather.current_solar_wind is not None
    assert weather.current_solar_wind.speed_km_s == 642.0
    assert weather.current_solar_wind.bz_nt == -12.5
    assert weather.proton_flux_10mev_pfu == 12.0


def test_kp_normalization_accepts_header_row_table(monkeypatch: pytest.MonkeyPatch) -> None:
    table = [
        ["time_tag", "Kp", "a_running", "station_count"],
        ["2026-07-02 09:00:00.000", "2.33", "9", "8"],
        ["2026-07-02 12:00:00.000", "6.00", "40", "8"],
    ]
    monkeypatch.setattr(
        solar_system_module, "fetch_json_cached", fake_fetcher({"planetary-k-index": table})
    )
    weather = asyncio.run(SolarSystemService(SETTINGS).space_weather())
    assert weather.current_kp == 6.0
    assert [entry.kp for entry in weather.kp_index] == [2.33, 6.0]


def test_stale_solar_wind_is_kept_in_series_but_not_current(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_tag = (datetime.now(UTC) - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S.000")
    stale_plasma = [PLASMA_PAYLOAD[0], [stale_tag, "4.0", "300.0", "80000"]]
    stale_mag = [MAG_PAYLOAD[0], [stale_tag, "1.0", "1.0", "2.0", "10.0", "5.0", "4.0"]]
    monkeypatch.setattr(
        solar_system_module,
        "fetch_json_cached",
        fake_fetcher({"plasma-3-day": stale_plasma, "mag-3-day": stale_mag}),
    )
    weather = asyncio.run(SolarSystemService(SETTINGS).space_weather())
    assert weather.current_solar_wind is None
    assert len(weather.solar_wind) == 1


def test_neo_feed_normalization_discards_invalid_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solar_system_module, "fetch_json_cached", fake_fetcher())
    feed = asyncio.run(SolarSystemService(SETTINGS).neo_feed())
    assert feed.count == 1
    approach = feed.approaches[0]
    assert approach.designation == "2026 AB"
    assert approach.close_approach_at == datetime(2026, 7, 4, 3, 12, tzinfo=UTC)
    assert approach.distance_lunar == pytest.approx(0.8017, abs=1e-3)
    assert approach.estimated_diameter_m == pytest.approx(48.6, abs=1.0)


def test_earth_events_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solar_system_module, "fetch_json_cached", fake_fetcher())
    feed = asyncio.run(SolarSystemService(SETTINGS).earth_events())
    assert feed.count == 2
    fire = feed.events[0]
    assert fire.category_id == "wildfires"
    assert fire.longitude == -121.5
    assert fire.source_url == "https://example.org/fire"
    storm = feed.events[1]
    assert storm.magnitude_value == 100.0


def test_overview_runs_detectors_and_degrades_gracefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solar_system_module,
        "fetch_json_cached",
        fake_fetcher({"eonet": FeedError("eonet down")}),
    )

    async def empty_quakes(self: PlanetaryOperationsService) -> EarthquakeFeed:
        now = datetime.now(UTC)
        return EarthquakeFeed(
            source="test", generated_at=now, cache_expires_at=now, count=0, earthquakes=[]
        )

    monkeypatch.setattr(PlanetaryOperationsService, "earthquake_feed", empty_quakes)
    overview = asyncio.run(SolarSystemService(SETTINGS).overview())
    status = {item.name: item.ok for item in overview.feed_status}
    assert status == {
        "space-weather": True,
        "earthquakes": True,
        "neo-close-approaches": True,
        "earth-events": False,
    }
    assert overview.earth_events is None
    assert overview.space_weather is not None
    assert len(overview.ephemeris.planets) == 9
    assert len(overview.solar_images) >= 5
    categories = {item.category for item in overview.detections.detections}
    expected = {"solar_flare", "solar_wind", "geomagnetic_storm", "radiation_storm", "neo_approach"}
    assert expected <= categories
    severity_ranks = [
        {"critical": 0, "warning": 1, "watch": 2, "info": 3}[item.severity]
        for item in overview.detections.detections
    ]
    assert severity_ranks == sorted(severity_ranks)


def test_estimated_diameter_matches_reference_points() -> None:
    assert estimated_diameter_m(None) is None
    value = estimated_diameter_m(22.0)
    assert value is not None
    assert value == pytest.approx(141.0, abs=2.0)


def test_solar_system_routes_are_registered_and_protected() -> None:
    schema = app.openapi()
    for path in (
        "/api/v1/solar-system/overview",
        "/api/v1/solar-system/space-weather",
        "/api/v1/solar-system/ephemeris",
        "/api/v1/solar-system/neo",
        "/api/v1/solar-system/earth-events",
        "/api/v1/solar-system/detections",
        "/api/v1/solar-system/stream",
    ):
        assert path in schema["paths"], path
    with TestClient(app) as client:
        response = client.get("/api/v1/solar-system/overview")
    assert response.status_code == 401


def test_ephemeris_endpoint_serves_snapshot_for_authenticated_user() -> None:
    app.dependency_overrides[get_current_user] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/solar-system/ephemeris")
            rejected = client.get(
                "/api/v1/solar-system/ephemeris", params={"at": "2026-07-02T00:00:00"}
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    payload = response.json()
    names = [planet["name"] for planet in payload["planets"]]
    assert names[:4] == ["mercury", "venus", "earth", "mars"]
    assert rejected.status_code == 422
