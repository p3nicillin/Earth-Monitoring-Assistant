import json
from typing import Any, cast

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping, shape


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


def polygon_bbox(geometry: dict[str, Any]) -> list[float]:
    return list(shape(geometry).bounds)


def polygon_centroid(geometry: dict[str, Any]) -> tuple[float, float]:
    point = shape(geometry).centroid
    return point.x, point.y
