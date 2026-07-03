import json
import math
from typing import Any, cast

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

from app.core.config import get_settings

_EARTH_RADIUS_KM = 6371.0088


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


def approximate_area_sq_km(geometry: dict[str, Any]) -> float:
    """Equirectangular-projection approximation of polygon area.

    Adequate for watch-area to continent-scale polygons; this is not a geodesic/
    ellipsoidal calculation, so it should be treated as an estimate, not a
    surveyed measurement.
    """
    geom = shape(geometry)
    min_lon, min_lat, max_lon, max_lat = geom.bounds
    mean_lat_rad = math.radians((min_lat + max_lat) / 2)
    km_per_deg_lon = (math.pi / 180) * _EARTH_RADIUS_KM * math.cos(mean_lat_rad)
    km_per_deg_lat = (math.pi / 180) * _EARTH_RADIUS_KM

    def _scale(coords: Any) -> list[tuple[float, float]]:
        return [(x * km_per_deg_lon, y * km_per_deg_lat) for x, y in coords]

    def _project_polygon(polygon: Any) -> Polygon:
        interiors = [_scale(ring.coords) for ring in polygon.interiors]
        return Polygon(_scale(polygon.exterior.coords), interiors)

    if isinstance(geom, Polygon):
        return abs(_project_polygon(geom).area)
    if isinstance(geom, MultiPolygon):
        return abs(MultiPolygon([_project_polygon(part) for part in geom.geoms]).area)
    return 0.0
