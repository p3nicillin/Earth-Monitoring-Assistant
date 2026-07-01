import json
from typing import Any, cast

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from app.core.config import get_settings


def geojson_to_wkt(geometry: dict[str, Any]) -> str:
    return str(shape(geometry).wkt)


def spatial_to_geojson(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return cast(dict[str, Any], json.loads(value))
    mapped: dict[str, Any] = dict(mapping(to_shape(value)))
    return mapped


def shape_to_spatial(value: BaseGeometry) -> Any:
    if get_settings().database_url.startswith("sqlite"):
        return json.dumps(mapping(value), separators=(",", ":"))
    return from_shape(value, srid=4326)


def polygon_bbox(geometry: dict[str, Any]) -> list[float]:
    return list(shape(geometry).bounds)


def polygon_centroid(geometry: dict[str, Any]) -> tuple[float, float]:
    point = shape(geometry).centroid
    return point.x, point.y
