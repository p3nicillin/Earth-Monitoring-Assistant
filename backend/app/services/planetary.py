import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.planetary import (
    EarthquakeFeature,
    EarthquakeFeed,
    MissionProfile,
    OrbitalElementSet,
    SatelliteCatalog,
    TrackedSatellite,
)

logger = logging.getLogger(__name__)


class PlanetaryFeedError(RuntimeError):
    """A bounded upstream orbital or hazard-feed failure."""


@dataclass(frozen=True)
class CacheEntry:
    value: object
    expires_monotonic: float


_satellite_cache: CacheEntry | None = None
_earthquake_cache: CacheEntry | None = None
_satellite_lock = asyncio.Lock()
_earthquake_lock = asyncio.Lock()


MISSION_PATTERNS = (
    re.compile(r"^SENTINEL-[123](?:[A-Z])?"),
    re.compile(r"^SENTINEL-5P$"),
    re.compile(r"^LANDSAT [89]$"),
    re.compile(r"^(TERRA|AQUA|SUOMI NPP)$"),
    re.compile(r"^NOAA (?:15|18|19|20|21)(?:\s|$)"),
    re.compile(r"^(?:GOES|EWS-G2 \(GOES) (?:1[456789])"),
    re.compile(r"^METEOSAT-(?:9|10|11|12)"),
)


def mission_profile(name: str) -> MissionProfile:
    upper = name.upper()
    common_status = "Orbital elements current; instrument telemetry is not asserted"
    if upper.startswith("SENTINEL-1"):
        return MissionProfile(
            family="Sentinel-1",
            operator="ESA / EU Copernicus",
            instruments=["C-band SAR"],
            nominal_swath_km=250,
            nominal_revisit="6–12 days by constellation",
            orbit_class="Sun-synchronous LEO",
            color="#38bdf8",
            sensor_status=common_status,
        )
    if upper.startswith("SENTINEL-2"):
        return MissionProfile(
            family="Sentinel-2",
            operator="ESA / EU Copernicus",
            instruments=["MSI"],
            nominal_swath_km=290,
            nominal_revisit="5 days by constellation",
            orbit_class="Sun-synchronous LEO",
            color="#4ade80",
            sensor_status=common_status,
        )
    if upper.startswith("SENTINEL-3"):
        return MissionProfile(
            family="Sentinel-3",
            operator="ESA / EUMETSAT",
            instruments=["OLCI", "SLSTR", "SRAL"],
            nominal_swath_km=1270,
            nominal_revisit="1–2 days by instrument",
            orbit_class="Sun-synchronous LEO",
            color="#22d3ee",
            sensor_status=common_status,
        )
    if upper == "SENTINEL-5P":
        return MissionProfile(
            family="Sentinel-5P",
            operator="ESA / EU Copernicus",
            instruments=["TROPOMI"],
            nominal_swath_km=2600,
            nominal_revisit="Daily",
            orbit_class="Sun-synchronous LEO",
            color="#a78bfa",
            sensor_status=common_status,
        )
    if upper.startswith("LANDSAT"):
        return MissionProfile(
            family="Landsat",
            operator="USGS / NASA",
            instruments=["OLI", "TIRS"],
            nominal_swath_km=185,
            nominal_revisit="8 days combined",
            orbit_class="Sun-synchronous LEO",
            color="#facc15",
            sensor_status=common_status,
        )
    if upper in {"TERRA", "AQUA"}:
        return MissionProfile(
            family=upper.title(),
            operator="NASA",
            instruments=["MODIS", "CERES"],
            nominal_swath_km=2330,
            nominal_revisit="Near-daily global",
            orbit_class="Sun-synchronous LEO",
            color="#fb923c",
            sensor_status=common_status,
        )
    if upper == "SUOMI NPP" or upper.startswith("NOAA "):
        return MissionProfile(
            family="JPSS / NOAA polar",
            operator="NOAA / NASA",
            instruments=["VIIRS", "CrIS", "ATMS", "OMPS"],
            nominal_swath_km=3040,
            nominal_revisit="Twice daily per spacecraft",
            orbit_class="Sun-synchronous LEO",
            color="#60a5fa",
            sensor_status=common_status,
        )
    if "GOES" in upper:
        return MissionProfile(
            family="GOES",
            operator="NOAA / NASA",
            instruments=["ABI", "GLM"],
            nominal_swath_km=17000,
            nominal_revisit="Full disk every 10 minutes",
            orbit_class="Geostationary",
            color="#fb7185",
            sensor_status=common_status,
        )
    if upper.startswith("METEOSAT"):
        instrument = "FCI / LI" if "12" in upper else "SEVIRI"
        return MissionProfile(
            family="Meteosat",
            operator="EUMETSAT",
            instruments=[instrument],
            nominal_swath_km=17000,
            nominal_revisit="Full disk every 10–15 minutes",
            orbit_class="Geostationary",
            color="#f472b6",
            sensor_status=common_status,
        )
    if upper.startswith("SKYSAT"):
        return MissionProfile(
            family="SkySat",
            operator="Planet Labs",
            instruments=["Optical video / panchromatic / multispectral"],
            nominal_swath_km=8,
            nominal_revisit="Tasking dependent",
            orbit_class="LEO",
            color="#c084fc",
            sensor_status=common_status,
        )
    return MissionProfile(
        family="PlanetScope",
        operator="Planet Labs",
        instruments=["Dove multispectral imager"],
        nominal_swath_km=24,
        nominal_revisit="Near-daily by constellation",
        orbit_class="Sun-synchronous LEO",
        color="#d946ef",
        sensor_status=common_status,
    )


class PlanetaryOperationsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def satellite_catalog(self) -> SatelliteCatalog:
        global _satellite_cache
        now_monotonic = time.monotonic()
        if _satellite_cache is not None and _satellite_cache.expires_monotonic > now_monotonic:
            return _satellite_cache.value  # type: ignore[return-value]
        async with _satellite_lock:
            now_monotonic = time.monotonic()
            if _satellite_cache is not None and _satellite_cache.expires_monotonic > now_monotonic:
                return _satellite_cache.value  # type: ignore[return-value]
            groups = await asyncio.gather(
                *(
                    self._fetch_json(self._celestrak_url(group))
                    for group in self.settings.orbital_groups
                )
            )
            records = self._select_satellites(groups)
            retrieved_at = datetime.now(UTC)
            expires_at = retrieved_at + timedelta(seconds=self.settings.orbital_cache_seconds)
            catalog = SatelliteCatalog(
                source="CelesTrak GP OMM",
                source_updated_at=retrieved_at,
                cache_expires_at=expires_at,
                count=len(records),
                satellites=records,
            )
            _satellite_cache = CacheEntry(
                catalog, now_monotonic + self.settings.orbital_cache_seconds
            )
            return catalog

    async def earthquake_feed(self) -> EarthquakeFeed:
        global _earthquake_cache
        now_monotonic = time.monotonic()
        if _earthquake_cache is not None and _earthquake_cache.expires_monotonic > now_monotonic:
            return _earthquake_cache.value  # type: ignore[return-value]
        async with _earthquake_lock:
            now_monotonic = time.monotonic()
            if (
                _earthquake_cache is not None
                and _earthquake_cache.expires_monotonic > now_monotonic
            ):
                return _earthquake_cache.value  # type: ignore[return-value]
            payload = await self._fetch_json(self.settings.usgs_earthquake_feed_url)
            generated_ms = (
                payload.get("metadata", {}).get("generated") if isinstance(payload, dict) else None
            )
            generated_at = (
                datetime.fromtimestamp(generated_ms / 1000, tz=UTC)
                if isinstance(generated_ms, (int, float))
                else datetime.now(UTC)
            )
            features = self._normalize_earthquakes(payload)
            expires_at = datetime.now(UTC) + timedelta(seconds=self.settings.hazard_cache_seconds)
            feed = EarthquakeFeed(
                source="USGS Earthquake Hazards Program",
                generated_at=generated_at,
                cache_expires_at=expires_at,
                count=len(features),
                earthquakes=features,
            )
            _earthquake_cache = CacheEntry(feed, now_monotonic + self.settings.hazard_cache_seconds)
            return feed

    def _celestrak_url(self, group: str) -> str:
        return f"{self.settings.celestrak_gp_url}?GROUP={group}&FORMAT=JSON"

    async def _fetch_json(self, url: str) -> Any:
        for attempt in range(1, self.settings.provider_max_attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.settings.request_timeout_seconds,
                    headers={"User-Agent": "TerraLens/0.1 source-backed planetary operations"},
                ) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    return response.json()
            except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
                if attempt == self.settings.provider_max_attempts:
                    raise PlanetaryFeedError(f"Upstream planetary feed failed: {url}") from exc
                await asyncio.sleep(self.settings.provider_backoff_seconds * (2 ** (attempt - 1)))
        raise PlanetaryFeedError(f"Upstream planetary feed failed: {url}")

    def _select_satellites(self, groups: list[Any]) -> list[TrackedSatellite]:
        selected: dict[int, TrackedSatellite] = {}
        planet_counts = {"skysat": 0, "planetscope": 0}
        for raw_group in groups:
            if not isinstance(raw_group, list):
                continue
            for raw in raw_group:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("OBJECT_NAME", "")).upper().strip()
                public_mission = any(pattern.search(name) for pattern in MISSION_PATTERNS)
                planet_mission = name.startswith(("FLOCK", "SKYSAT", "PELICAN", "TANAGER"))
                planet_family = "skysat" if name.startswith("SKYSAT") else "planetscope"
                family_limit = (
                    min(8, self.settings.planet_satellite_limit)
                    if planet_family == "skysat"
                    else max(0, self.settings.planet_satellite_limit - 8)
                )
                if planet_mission and planet_counts[planet_family] >= family_limit:
                    continue
                if not public_mission and not planet_mission:
                    continue
                try:
                    omm = OrbitalElementSet.model_validate(raw)
                    epoch = datetime.fromisoformat(omm.epoch.replace("Z", "+00:00"))
                    if epoch.tzinfo is None:
                        epoch = epoch.replace(tzinfo=UTC)
                    satellite = TrackedSatellite(
                        id=f"norad-{omm.norad_catalog_id}",
                        name=omm.object_name,
                        international_designator=omm.object_id,
                        norad_catalog_id=omm.norad_catalog_id,
                        element_epoch=epoch,
                        profile=mission_profile(omm.object_name),
                        omm=omm,
                    )
                except (ValidationError, ValueError) as exc:
                    logger.warning("Discarding invalid orbital element record: %s", exc)
                    continue
                if satellite.norad_catalog_id not in selected:
                    selected[satellite.norad_catalog_id] = satellite
                    if planet_mission:
                        planet_counts[planet_family] += 1
        return sorted(selected.values(), key=lambda item: (item.profile.family, item.name))

    def _normalize_earthquakes(self, payload: Any) -> list[EarthquakeFeature]:
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise PlanetaryFeedError("USGS feed is not valid GeoJSON")
        earthquakes: list[EarthquakeFeature] = []
        for raw in payload["features"]:
            try:
                properties = raw["properties"]
                coordinates = raw["geometry"]["coordinates"]
                occurred_at = datetime.fromtimestamp(properties["time"] / 1000, tz=UTC)
                earthquakes.append(
                    EarthquakeFeature(
                        id=str(raw["id"]),
                        title=str(properties.get("title") or "Earthquake"),
                        magnitude=properties.get("mag"),
                        occurred_at=occurred_at,
                        longitude=float(coordinates[0]),
                        latitude=float(coordinates[1]),
                        depth_km=float(coordinates[2]),
                        detail_url=properties.get("url"),
                        tsunami=bool(properties.get("tsunami")),
                        place=properties.get("place"),
                        properties={
                            "alert": properties.get("alert"),
                            "felt": properties.get("felt"),
                            "significance": properties.get("sig"),
                        },
                    )
                )
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                logger.warning("Discarding invalid earthquake feature: %s", exc)
        return earthquakes
