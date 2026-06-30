from app.utils.geo import geojson_to_wkt, polygon_bbox, polygon_centroid, spatial_to_geojson

POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0.0, 50.0], [2.0, 50.0], [2.0, 52.0], [0.0, 52.0], [0.0, 50.0]]],
}


def test_polygon_helpers() -> None:
    assert polygon_bbox(POLYGON) == [0.0, 50.0, 2.0, 52.0]
    assert polygon_centroid(POLYGON) == (1.0, 51.0)
    assert geojson_to_wkt(POLYGON).startswith("POLYGON")


def test_spatial_to_geojson_accepts_json_and_dictionary() -> None:
    assert spatial_to_geojson(POLYGON) is POLYGON
    assert spatial_to_geojson('{"type":"Point","coordinates":[1,2]}') == {
        "type": "Point",
        "coordinates": [1, 2],
    }
    assert spatial_to_geojson(None) == {}
