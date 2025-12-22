"""Tests for output converters."""

import json
import pytest
from mobile_geodatabase import (
    Point, LineString, Polygon, MultiLineString, MultiPolygon,
    to_wkt, to_wkb, to_geojson_geometry, feature_to_geojson
)
from mobile_geodatabase.database import Feature


class TestToWkt:
    def test_point_wkt(self):
        pt = Point(x=-122.0, y=47.0)
        assert to_wkt(pt) == "POINT (-122.0 47.0)"

    def test_linestring_wkt(self):
        line = LineString(points=[(0, 0), (1, 1), (2, 2)])
        wkt = to_wkt(line)
        assert wkt == "LINESTRING (0 0, 1 1, 2 2)"

    def test_polygon_wkt(self):
        poly = Polygon(rings=[[(0, 0), (10, 0), (10, 10), (0, 0)]])
        wkt = to_wkt(poly)
        assert wkt == "POLYGON ((0 0, 10 0, 10 10, 0 0))"


class TestToGeoJsonGeometry:
    def test_point_geojson(self):
        pt = Point(x=-122.0, y=47.0)
        geojson = to_geojson_geometry(pt)
        assert geojson["type"] == "Point"
        assert geojson["coordinates"] == [-122.0, 47.0]

    def test_point_z_geojson(self):
        pt = Point(x=-122.0, y=47.0, z=100.0)
        geojson = to_geojson_geometry(pt)
        assert geojson["coordinates"] == [-122.0, 47.0, 100.0]

    def test_linestring_geojson(self):
        line = LineString(points=[(0, 0), (1, 1), (2, 2)])
        geojson = to_geojson_geometry(line)
        assert geojson["type"] == "LineString"
        assert geojson["coordinates"] == [[0, 0], [1, 1], [2, 2]]

    def test_polygon_geojson(self):
        poly = Polygon(rings=[[(0, 0), (10, 0), (10, 10), (0, 0)]])
        geojson = to_geojson_geometry(poly)
        assert geojson["type"] == "Polygon"
        assert len(geojson["coordinates"]) == 1
        assert geojson["coordinates"][0] == [[0, 0], [10, 0], [10, 10], [0, 0]]

    def test_multilinestring_geojson(self):
        line1 = LineString(points=[(0, 0), (1, 1)])
        line2 = LineString(points=[(2, 2), (3, 3)])
        mls = MultiLineString(lines=[line1, line2])
        geojson = to_geojson_geometry(mls)
        assert geojson["type"] == "MultiLineString"
        assert len(geojson["coordinates"]) == 2


class TestFeatureToGeoJson:
    def test_feature_with_geometry(self):
        pt = Point(x=-122.0, y=47.0)
        feature = Feature(
            geometry=pt,
            attributes={"name": "Test", "value": 42},
            fid=1
        )
        geojson = feature_to_geojson(feature)

        assert geojson["type"] == "Feature"
        assert geojson["id"] == 1
        assert geojson["properties"]["name"] == "Test"
        assert geojson["properties"]["value"] == 42
        assert geojson["geometry"]["type"] == "Point"

    def test_feature_without_geometry(self):
        feature = Feature(
            geometry=None,
            attributes={"name": "NoGeom"}
        )
        geojson = feature_to_geojson(feature)

        assert geojson["type"] == "Feature"
        assert geojson["geometry"] is None
        assert geojson["properties"]["name"] == "NoGeom"

    def test_feature_without_fid(self):
        pt = Point(x=0, y=0)
        feature = Feature(geometry=pt, attributes={})
        geojson = feature_to_geojson(feature)

        assert "id" not in geojson


class TestToWkb:
    def test_point_wkb(self):
        pt = Point(x=-122.0, y=47.0)
        wkb = to_wkb(pt)

        # First byte is byte order (1 = little endian)
        assert wkb[0] == 1
        # Next 4 bytes are type (1 = Point)
        assert wkb[1:5] == b'\x01\x00\x00\x00'
        # Remaining bytes are coordinates
        assert len(wkb) == 21  # 1 + 4 + 8 + 8

    def test_linestring_wkb(self):
        line = LineString(points=[(0, 0), (1, 1)])
        wkb = to_wkb(line)

        assert wkb[0] == 1  # Little endian
        # Type 2 = LineString
        assert wkb[1:5] == b'\x02\x00\x00\x00'

    def test_wkb_big_endian(self):
        pt = Point(x=1.0, y=2.0)
        wkb = to_wkb(pt, big_endian=True)

        assert wkb[0] == 0  # Big endian
