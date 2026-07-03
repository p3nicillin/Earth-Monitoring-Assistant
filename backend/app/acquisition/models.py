import hashlib
import json
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely.geometry import shape


class SearchRequest(BaseModel):
    """Provider-neutral spatial and temporal catalogue search."""

    model_config = ConfigDict(frozen=True)

    geometry: dict[str, Any]
    start: AwareDatetime
    end: AwareDatetime
    max_cloud_cover: float = Field(ge=0, le=100)
    limit: int = Field(ge=1, le=200)

    @field_validator("geometry")
    @classmethod
    def valid_search_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        geometry = shape(value)
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Search geometry must be non-empty and valid")
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Search geometry must be a Polygon or MultiPolygon")
        min_x, min_y, max_x, max_y = geometry.bounds
        if min_x < -180 or max_x > 180 or min_y < -90 or max_y > 90:
            raise ValueError("Search geometry must use WGS84 longitude/latitude bounds")
        return value

    @model_validator(mode="after")
    def chronological_window(self) -> "SearchRequest":
        if self.end <= self.start:
            raise ValueError("Search end must be later than search start")
        return self


class ImageryItem(BaseModel):
    """Normalized immutable catalogue record with deterministic provenance."""

    model_config = ConfigDict(frozen=True)

    item_id: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=80)
    captured_at: AwareDatetime
    footprint: dict[str, Any]
    cloud_cover: float | None = Field(default=None, ge=0, le=100)
    assets: dict[str, dict[str, Any]]
    metadata: dict[str, Any]

    @field_validator("footprint")
    @classmethod
    def valid_footprint(cls, value: dict[str, Any]) -> dict[str, Any]:
        geometry = shape(value)
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Source footprint must be non-empty and valid")
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Source footprint must be a Polygon or MultiPolygon")
        return value

    @field_validator("assets")
    @classmethod
    def safe_assets(cls, value: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        safe: dict[str, dict[str, Any]] = {}
        for key, asset in value.items():
            href = asset.get("href")
            if not isinstance(href, str) or urlparse(href).scheme not in {"https", "s3"}:
                continue
            safe[key] = {
                "href": href,
                "type": asset.get("type") if isinstance(asset.get("type"), str) else None,
            }
        return safe

    @property
    def provenance_checksum(self) -> str:
        payload = {
            "assets": self.assets,
            "captured_at": self.captured_at.isoformat(),
            "footprint": self.footprint,
            "item_id": self.item_id,
            "metadata": self.metadata,
            "source": self.source,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_stac_datetime(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("STAC item datetime is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("STAC item datetime must include a timezone")
    return parsed
