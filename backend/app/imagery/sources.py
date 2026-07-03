"""Live imagery source registry.

A source either has a fixed "latest frame" URL (SDO/SOHO/SUVI style) or is
resolved dynamically against an index API (DSCOVR EPIC). Resolution returns
the concrete frame URL plus any upstream-supplied capture metadata; the
harvester treats capture time as fetch time when upstream provides none,
because latest-frame endpoints carry no timestamp contract.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.services.feeds import FeedError, fetch_json_cached


@dataclass(frozen=True)
class ResolvedFrame:
    url: str
    captured_at: datetime | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImagerySource:
    key: str
    title: str
    source: str
    description: str
    static_url: str | None = None
    resolver: str | None = None  # named dynamic resolver, e.g. "epic"


IMAGERY_SOURCES: tuple[ImagerySource, ...] = (
    ImagerySource(
        key="sdo-aia-193",
        title="Solar corona 19.3 nm",
        source="NASA SDO/AIA",
        description="Extreme-ultraviolet corona; flares and coronal holes.",
        static_url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0193.jpg",
    ),
    ImagerySource(
        key="sdo-aia-304",
        title="Chromosphere 30.4 nm",
        source="NASA SDO/AIA",
        description="Helium-II line; filaments and prominences.",
        static_url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0304.jpg",
    ),
    ImagerySource(
        key="sdo-aia-171",
        title="Quiet corona 17.1 nm",
        source="NASA SDO/AIA",
        description="Coronal loops above active regions.",
        static_url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_0171.jpg",
    ),
    ImagerySource(
        key="sdo-hmi-continuum",
        title="Visible solar surface",
        source="NASA SDO/HMI",
        description="Intensitygram; sunspot groups in white light.",
        static_url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIIC.jpg",
    ),
    ImagerySource(
        key="sdo-hmi-magnetogram",
        title="Solar magnetogram",
        source="NASA SDO/HMI",
        description="Line-of-sight magnetic field polarity.",
        static_url="https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIB.jpg",
    ),
    ImagerySource(
        key="soho-lasco-c2",
        title="Inner corona (LASCO C2)",
        source="ESA/NASA SOHO",
        description="Coronagraph view of CMEs close to the Sun.",
        static_url="https://soho.nascom.nasa.gov/data/realtime/c2/512/latest.jpg",
    ),
    ImagerySource(
        key="soho-lasco-c3",
        title="Outer corona (LASCO C3)",
        source="ESA/NASA SOHO",
        description="Wide-field coronagraph; CMEs leaving the Sun.",
        static_url="https://soho.nascom.nasa.gov/data/realtime/c3/512/latest.jpg",
    ),
    ImagerySource(
        key="goes-suvi-195",
        title="GOES SUVI 19.5 nm",
        source="NOAA GOES-R SUVI",
        description="Operational solar EUV imager frame.",
        static_url=("https://services.swpc.noaa.gov/images/animations/suvi/primary/195/latest.png"),
    ),
    ImagerySource(
        key="epic-natural",
        title="Full Earth (EPIC natural colour)",
        source="NASA DSCOVR EPIC",
        description="Sunlit disc of Earth from the L1 Lagrange point.",
        resolver="epic",
    ),
)

SOURCES_BY_KEY: dict[str, ImagerySource] = {source.key: source for source in IMAGERY_SOURCES}


async def resolve_frame(settings: Settings, source: ImagerySource) -> ResolvedFrame | None:
    if source.static_url is not None:
        return ResolvedFrame(url=source.static_url, captured_at=None)
    if source.resolver == "epic":
        return await _resolve_epic(settings)
    return None


async def _resolve_epic(settings: Settings) -> ResolvedFrame | None:
    base = settings.epic_api_url.rstrip("/")
    try:
        payload = await fetch_json_cached(settings, f"{base}/api/natural", ttl_seconds=900)
    except FeedError:
        return None
    if not isinstance(payload, list) or not payload:
        return None
    latest = payload[-1]
    if not isinstance(latest, dict):
        return None
    name = latest.get("image")
    date_raw = latest.get("date")
    if not isinstance(name, str) or not isinstance(date_raw, str):
        return None
    try:
        captured_at = datetime.fromisoformat(date_raw).replace(tzinfo=UTC)
    except ValueError:
        captured_at = None
    day = captured_at or datetime.now(UTC)
    archive_path = f"{day.year:04d}/{day.month:02d}/{day.day:02d}"
    return ResolvedFrame(
        url=f"{base}/archive/natural/{archive_path}/jpg/{name}.jpg",
        captured_at=captured_at,
        metadata={
            "caption": latest.get("caption"),
            "centroid": latest.get("centroid_coordinates"),
        },
    )
