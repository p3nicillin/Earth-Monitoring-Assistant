"""Live solar-system situational awareness built from keyless public feeds.

Feeds: NOAA SWPC space weather, JPL SSD close-approach data, NASA EONET
open natural events, USGS earthquakes (via the planetary service), and an
in-process planetary ephemeris. Each upstream is cached with its own TTL
and one failing feed degrades the overview instead of failing it.
"""

import asyncio
import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.learning.anomalies import detect_adaptive_anomalies
from app.schemas.insights import MetricBaseline
from app.schemas.planetary import EarthquakeFeed
from app.schemas.solar_system import (
    DetectionFeed,
    EarthEvent,
    EarthEventFeed,
    EphemerisSnapshot,
    FeedStatus,
    FlareEvent,
    KpEntry,
    NeoApproach,
    NeoFeed,
    SolarImage,
    SolarSystemOverview,
    SolarWindPoint,
    SpaceWeather,
    XrayFluxPoint,
)
from app.services import spot_detections
from app.services.ephemeris import compute_ephemeris
from app.services.feeds import FeedError, fetch_json_cached
from app.services.planetary import PlanetaryFeedError, PlanetaryOperationsService

logger = logging.getLogger(__name__)

_LUNAR_DISTANCE_AU = 0.00256955529
_MAX_SERIES_POINTS = 240
_SOLAR_WIND_STALE_SECONDS = 7200

SOLAR_IMAGES: tuple[SolarImage, ...] = (
    SolarImage(
        key="aia-193",
        title="Corona 19.3 nm",
        description="SDO/AIA extreme ultraviolet corona; flares and coronal holes.",
        url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_512_0193.jpg",
        source="NASA SDO/AIA",
    ),
    SolarImage(
        key="aia-304",
        title="Chromosphere 30.4 nm",
        description="SDO/AIA helium-II line; filaments and prominences.",
        url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_512_0304.jpg",
        source="NASA SDO/AIA",
    ),
    SolarImage(
        key="aia-171",
        title="Quiet corona 17.1 nm",
        description="SDO/AIA coronal loops above active regions.",
        url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_512_0171.jpg",
        source="NASA SDO/AIA",
    ),
    SolarImage(
        key="hmi-continuum",
        title="Visible surface",
        description="SDO/HMI intensitygram; sunspot groups in white light.",
        url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_512_HMIIC.jpg",
        source="NASA SDO/HMI",
    ),
    SolarImage(
        key="hmi-magnetogram",
        title="Magnetogram",
        description="SDO/HMI line-of-sight magnetic field polarity.",
        url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_512_HMIB.jpg",
        source="NASA SDO/HMI",
    ),
    SolarImage(
        key="lasco-c3",
        title="Outer corona (C3)",
        description="SOHO/LASCO C3 coronagraph; CMEs leaving the Sun.",
        url="https://soho.nascom.nasa.gov/data/realtime/c3/512/latest.jpg",
        source="ESA/NASA SOHO",
    ),
)


def _parse_swpc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value or value.lower().startswith("unk"):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_cad_timestamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%b-%d %H:%M").replace(tzinfo=UTC)
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decimate(points: list[Any], max_points: int = _MAX_SERIES_POINTS) -> list[Any]:
    if len(points) <= max_points:
        return points
    stride = max(1, len(points) // max_points)
    sampled = points[::stride]
    if points and sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


def estimated_diameter_m(absolute_magnitude_h: float | None) -> float | None:
    """Diameter estimate from H assuming 0.14 albedo (order-of-magnitude only)."""
    if absolute_magnitude_h is None:
        return None
    return 1329.0 / math.sqrt(0.14) * math.pow(10.0, -absolute_magnitude_h / 5.0) * 1000.0


class SolarSystemService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def _fetch_or_none(self, url: str, ttl: float) -> Any:
        """One flaky SWPC product must degrade its section, not all space weather."""
        try:
            return await fetch_json_cached(self.settings, url, ttl)
        except FeedError:
            logger.warning("Space weather sub-feed unavailable: %s", url)
            return None

    async def _fetch_solar_wind_product(self, kind: str, ttl: float) -> Any:
        """SWPC windowed product files intermittently 404 or serve header-only."""
        base = self.settings.swpc_base_url.rstrip("/")
        for window in ("3-day", "7-day"):
            payload = await self._fetch_or_none(
                f"{base}/products/solar-wind/{kind}-{window}.json", ttl
            )
            if payload is not None and self._product_rows(payload):
                return payload
        return None

    async def space_weather(self) -> SpaceWeather:
        base = self.settings.swpc_base_url.rstrip("/")
        ttl = self.settings.space_weather_cache_seconds
        xray_raw, flare_raw, plasma_raw, mag_raw, kp_raw, proton_raw = await asyncio.gather(
            self._fetch_or_none(f"{base}/json/goes/primary/xrays-6-hour.json", ttl),
            self._fetch_or_none(f"{base}/json/goes/primary/xray-flares-latest.json", ttl),
            self._fetch_solar_wind_product("plasma", ttl),
            self._fetch_solar_wind_product("mag", ttl),
            self._fetch_or_none(f"{base}/products/noaa-planetary-k-index.json", ttl),
            self._fetch_or_none(f"{base}/json/goes/primary/integral-protons-1-day.json", ttl),
        )
        if all(
            raw is None for raw in (xray_raw, flare_raw, plasma_raw, mag_raw, kp_raw, proton_raw)
        ):
            raise FeedError("All SWPC space weather feeds are unavailable")
        xray_flux = self._normalize_xray(xray_raw)
        kp_index = self._normalize_kp(kp_raw)
        solar_wind = self._normalize_solar_wind(plasma_raw, mag_raw)
        now = datetime.now(UTC)
        # A reading only counts as "current" while fresh; RTSW has multi-hour
        # gaps and stale values must not drive anomaly detections.
        current_wind = (
            solar_wind[-1]
            if solar_wind
            and (now - solar_wind[-1].time_tag).total_seconds() <= _SOLAR_WIND_STALE_SECONDS
            else None
        )
        return SpaceWeather(
            source="NOAA Space Weather Prediction Center",
            generated_at=now,
            cache_expires_at=now + timedelta(seconds=ttl),
            xray_flux=_decimate(xray_flux),
            current_xray_class=(
                spot_detections.classify_xray_flux(xray_flux[-1].flux_watts_m2)
                if xray_flux
                else None
            ),
            latest_flare=self._normalize_flare(flare_raw),
            kp_index=kp_index,
            current_kp=kp_index[-1].kp if kp_index else None,
            solar_wind=_decimate(solar_wind),
            current_solar_wind=current_wind,
            proton_flux_10mev_pfu=self._normalize_protons(proton_raw),
        )

    async def neo_feed(self) -> NeoFeed:
        days = self.settings.neo_lookahead_days
        url = (
            f"{self.settings.cad_api_url}?date-min=now&date-max=%2B{days}"
            f"&dist-max={self.settings.neo_max_distance_au}&sort=dist"
        )
        payload = await fetch_json_cached(self.settings, url, self.settings.neo_cache_seconds)
        approaches = self._normalize_neo(payload)
        now = datetime.now(UTC)
        return NeoFeed(
            source="JPL SSD/CNEOS close-approach data API",
            generated_at=now,
            cache_expires_at=now + timedelta(seconds=self.settings.neo_cache_seconds),
            lookahead_days=days,
            count=len(approaches),
            approaches=approaches,
        )

    async def earth_events(self) -> EarthEventFeed:
        days = self.settings.earth_events_lookback_days
        url = f"{self.settings.eonet_events_url}?status=open&days={days}"
        payload = await fetch_json_cached(
            self.settings, url, self.settings.earth_events_cache_seconds
        )
        events = self._normalize_earth_events(payload)
        now = datetime.now(UTC)
        return EarthEventFeed(
            source="NASA EONET v3",
            generated_at=now,
            cache_expires_at=now + timedelta(seconds=self.settings.earth_events_cache_seconds),
            lookback_days=days,
            count=len(events),
            events=events,
        )

    def ephemeris(self, moment: datetime | None = None) -> EphemerisSnapshot:
        return compute_ephemeris(moment)

    async def overview(self, baselines: list[MetricBaseline] | None = None) -> SolarSystemOverview:
        planetary = PlanetaryOperationsService(self.settings)
        results = await asyncio.gather(
            self.space_weather(),
            planetary.earthquake_feed(),
            self.neo_feed(),
            self.earth_events(),
            return_exceptions=True,
        )
        names = ("space-weather", "earthquakes", "neo-close-approaches", "earth-events")
        feed_status: list[FeedStatus] = []
        values: list[Any] = []
        for name, result in zip(names, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, (FeedError, PlanetaryFeedError)):
                    raise result
                logger.warning("Live feed %s unavailable: %s", name, result)
                feed_status.append(FeedStatus(name=name, ok=False, detail=str(result)))
                values.append(None)
            else:
                feed_status.append(FeedStatus(name=name, ok=True))
                values.append(result)
        weather: SpaceWeather | None = values[0]
        earthquakes: EarthquakeFeed | None = values[1]
        neo: NeoFeed | None = values[2]
        earth_events: EarthEventFeed | None = values[3]
        now = datetime.now(UTC)
        detections = spot_detections.run_all_detectors(weather, earthquakes, neo, earth_events)
        if weather is not None and baselines:
            adaptive = detect_adaptive_anomalies(weather, baselines)
            if adaptive:
                existing_ids = {detection.id for detection in detections}
                detections.extend(item for item in adaptive if item.id not in existing_ids)
                detections.sort(key=lambda item: item.observed_at, reverse=True)
                detections.sort(key=lambda item: spot_detections.SEVERITY_RANK[item.severity])
        return SolarSystemOverview(
            generated_at=now,
            feed_status=feed_status,
            space_weather=weather,
            ephemeris=self.ephemeris(),
            neo=neo,
            earth_events=earth_events,
            solar_images=list(SOLAR_IMAGES),
            detections=DetectionFeed(
                generated_at=now, count=len(detections), detections=detections
            ),
        )

    def _normalize_xray(self, payload: Any) -> list[XrayFluxPoint]:
        if not isinstance(payload, list):
            return []
        points: list[XrayFluxPoint] = []
        for raw in payload:
            if not isinstance(raw, dict) or raw.get("energy") != "0.1-0.8nm":
                continue
            time_tag = _parse_swpc_timestamp(raw.get("time_tag"))
            flux = _to_float(raw.get("flux"))
            if time_tag is None or flux is None or flux <= 0:
                continue
            points.append(XrayFluxPoint(time_tag=time_tag, flux_watts_m2=flux))
        points.sort(key=lambda point: point.time_tag)
        return points

    def _normalize_flare(self, payload: Any) -> FlareEvent | None:
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
            return None
        raw = payload[0]
        max_class = raw.get("max_class") or raw.get("current_class")
        ended_at = _parse_swpc_timestamp(raw.get("end_time"))
        began_at = _parse_swpc_timestamp(raw.get("begin_time"))
        if began_at is None and max_class is None:
            return None
        return FlareEvent(
            began_at=began_at,
            peaked_at=_parse_swpc_timestamp(raw.get("max_time")),
            ended_at=ended_at,
            max_class=str(max_class) if max_class else None,
            in_progress=began_at is not None and ended_at is None,
        )

    def _normalize_kp(self, payload: Any) -> list[KpEntry]:
        """SWPC has served this feed both as dict rows and as a header-row table."""
        rows: list[dict[str, Any]]
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            rows = [row for row in payload if isinstance(row, dict)]
        else:
            rows = self._product_rows(payload)
        entries: list[KpEntry] = []
        for row in rows:
            time_tag = _parse_swpc_timestamp(row.get("time_tag"))
            kp = _to_float(row.get("Kp") if "Kp" in row else row.get("kp_index"))
            if time_tag is None or kp is None:
                continue
            entries.append(KpEntry(time_tag=time_tag, kp=kp))
        entries.sort(key=lambda entry: entry.time_tag)
        return entries

    def _normalize_solar_wind(self, plasma: Any, mag: Any) -> list[SolarWindPoint]:
        merged: dict[datetime, SolarWindPoint] = {}
        for row in self._product_rows(plasma):
            time_tag = _parse_swpc_timestamp(row.get("time_tag"))
            if time_tag is None:
                continue
            speed = _to_float(row.get("speed"))
            density = _to_float(row.get("density"))
            if speed is None and density is None:
                continue
            merged[time_tag] = SolarWindPoint(
                time_tag=time_tag, speed_km_s=speed, density_p_cm3=density
            )
        for row in self._product_rows(mag):
            time_tag = _parse_swpc_timestamp(row.get("time_tag"))
            if time_tag is None:
                continue
            bz = _to_float(row.get("bz_gsm"))
            bt = _to_float(row.get("bt"))
            if bz is None and bt is None:
                continue
            existing = merged.get(time_tag)
            if existing is not None:
                merged[time_tag] = existing.model_copy(update={"bz_nt": bz, "bt_nt": bt})
            else:
                merged[time_tag] = SolarWindPoint(time_tag=time_tag, bz_nt=bz, bt_nt=bt)
        return [merged[key] for key in sorted(merged)]

    def _normalize_protons(self, payload: Any) -> float | None:
        if not isinstance(payload, list):
            return None
        latest: tuple[datetime, float] | None = None
        for raw in payload:
            if not isinstance(raw, dict) or raw.get("energy") != ">=10 MeV":
                continue
            time_tag = _parse_swpc_timestamp(raw.get("time_tag"))
            flux = _to_float(raw.get("flux"))
            if time_tag is None or flux is None:
                continue
            if latest is None or time_tag > latest[0]:
                latest = (time_tag, flux)
        return latest[1] if latest else None

    def _product_rows(self, payload: Any) -> list[dict[str, Any]]:
        """SWPC 'products' feeds are a header row followed by value rows."""
        if not isinstance(payload, list) or len(payload) < 2:
            return []
        header = payload[0]
        if not isinstance(header, list):
            return []
        columns = [str(column) for column in header]
        rows: list[dict[str, Any]] = []
        for raw in payload[1:]:
            if isinstance(raw, list) and len(raw) == len(columns):
                rows.append(dict(zip(columns, raw, strict=True)))
        return rows

    def _normalize_neo(self, payload: Any) -> list[NeoApproach]:
        if not isinstance(payload, dict):
            return []
        fields = payload.get("fields")
        data = payload.get("data")
        if not isinstance(fields, list) or not isinstance(data, list):
            return []
        approaches: list[NeoApproach] = []
        for raw in data:
            if not isinstance(raw, list) or len(raw) != len(fields):
                continue
            record = dict(zip([str(field) for field in fields], raw, strict=True))
            close_approach_at = _parse_cad_timestamp(str(record.get("cd", "")))
            distance_au = _to_float(record.get("dist"))
            velocity = _to_float(record.get("v_rel"))
            if close_approach_at is None or distance_au is None or velocity is None:
                continue
            magnitude = _to_float(record.get("h"))
            approaches.append(
                NeoApproach(
                    designation=str(record.get("des", "unknown")),
                    close_approach_at=close_approach_at,
                    distance_au=distance_au,
                    distance_lunar=distance_au / _LUNAR_DISTANCE_AU,
                    velocity_km_s=velocity,
                    absolute_magnitude_h=magnitude,
                    estimated_diameter_m=estimated_diameter_m(magnitude),
                )
            )
        approaches.sort(key=lambda item: item.close_approach_at)
        return approaches

    def _normalize_earth_events(self, payload: Any) -> list[EarthEvent]:
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            return []
        events: list[EarthEvent] = []
        for raw in payload["events"]:
            if not isinstance(raw, dict):
                continue
            categories = raw.get("categories") or [{}]
            category = categories[0] if isinstance(categories[0], dict) else {}
            geometry_list = raw.get("geometry") or []
            latest_geometry = (
                geometry_list[-1] if geometry_list and isinstance(geometry_list[-1], dict) else {}
            )
            longitude, latitude = self._geometry_point(latest_geometry)
            sources = raw.get("sources") or []
            source_url = sources[0].get("url") if sources and isinstance(sources[0], dict) else None
            events.append(
                EarthEvent(
                    id=str(raw.get("id", "unknown")),
                    title=str(raw.get("title", "Untitled event")),
                    category_id=str(category.get("id", "unknown")),
                    category_title=str(category.get("title", "Unknown")),
                    longitude=longitude,
                    latitude=latitude,
                    observed_at=_parse_swpc_timestamp(latest_geometry.get("date")),
                    magnitude_value=_to_float(latest_geometry.get("magnitudeValue")),
                    magnitude_unit=(
                        str(latest_geometry["magnitudeUnit"])
                        if latest_geometry.get("magnitudeUnit")
                        else None
                    ),
                    source_url=str(source_url) if source_url else None,
                )
            )
        return events

    def _geometry_point(self, geometry: dict[str, Any]) -> tuple[float | None, float | None]:
        coordinates = geometry.get("coordinates")
        if geometry.get("type") == "Point" and isinstance(coordinates, list):
            longitude = _to_float(coordinates[0]) if len(coordinates) > 0 else None
            latitude = _to_float(coordinates[1]) if len(coordinates) > 1 else None
            return longitude, latitude
        if geometry.get("type") == "Polygon" and isinstance(coordinates, list) and coordinates:
            ring = coordinates[0]
            if isinstance(ring, list) and ring:
                points = [point for point in ring if isinstance(point, list) and len(point) > 1]
                longitudes = [point[0] for point in points]
                latitudes = [point[1] for point in points]
                if longitudes and latitudes:
                    return (
                        sum(longitudes) / len(longitudes),
                        sum(latitudes) / len(latitudes),
                    )
        return None, None
