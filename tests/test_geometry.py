"""Tests for geometry classes."""

import pytest
from mobile_geodatabase import (
    Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon,
    CoordinateSystem, BoundingBox
)


class TestPoint:
    def test_point_2d(self):
        pt = Point(x=-122.0, y=47.0)
        assert pt.x == -122.0
        assert pt.y == 47.0
        assert pt.z is None
        assert not pt.has_z

    def test_point_3d(self):
        pt = Point(x=-122.0, y=47.0, z=100.0)
        assert pt.z == 100.0
        assert pt.has_z

    def test_point_wkt_2d(self):
        pt = Point(x=-122.0, y=47.0)
        assert pt.wkt == "POINT (-122.0 47.0)"

    def test_point_wkt_3d(self):
        pt = Point(x=-122.0, y=47.0, z=100.0)
        assert pt.wkt == "POINT Z (-122.0 47.0 100.0)"

    def test_point_coordinates(self):
        pt = Point(x=-122.0, y=47.0)
        assert pt.coordinates == (-122.0, 47.0)

        pt3d = Point(x=-122.0, y=47.0, z=100.0)
        assert pt3d.coordinates == (-122.0, 47.0, 100.0)

    def test_point_bounds(self):
        pt = Point(x=-122.0, y=47.0)
        bounds = pt.bounds
        assert bounds.xmin == -122.0
        assert bounds.ymin == 47.0
        assert bounds.xmax == -122.0
        assert bounds.ymax == 47.0


class TestLineString:
    def test_linestring_basic(self):
        pts = [(-122.0, 47.0), (-122.1, 47.1), (-122.2, 47.2)]
        line = LineString(points=pts)
        assert len(line) == 3
        assert not line.has_z

    def test_linestring_wkt(self):
        pts = [(-122.0, 47.0), (-122.1, 47.1)]
        line = LineString(points=pts)
        assert line.wkt == "LINESTRING (-122.0 47.0, -122.1 47.1)"

    def test_linestring_with_z(self):
        pts = [(-122.0, 47.0), (-122.1, 47.1)]
        z_vals = [100.0, 200.0]
        line = LineString(points=pts, z_values=z_vals)
        assert line.has_z
        assert "LINESTRING Z" in line.wkt

    def test_linestring_bounds(self):
        pts = [(-122.0, 47.0), (-122.5, 47.5), (-122.2, 47.2)]
        line = LineString(points=pts)
        bounds = line.bounds
        assert bounds.xmin == -122.5
        assert bounds.xmax == -122.0
        assert bounds.ymin == 47.0
        assert bounds.ymax == 47.5


class TestPolygon:
    def test_polygon_single_ring(self):
        ring = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        poly = Polygon(rings=[ring])
        assert len(poly.rings) == 1
        assert poly.exterior == ring
        assert poly.interiors == []

    def test_polygon_with_hole(self):
        exterior = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole = [(2, 2), (8, 2), (8, 8), (2, 8), (2, 2)]
        poly = Polygon(rings=[exterior, hole])
        assert len(poly.rings) == 2
        assert poly.exterior == exterior
        assert poly.interiors == [hole]

    def test_polygon_wkt(self):
        ring = [(0, 0), (10, 0), (10, 10), (0, 0)]
        poly = Polygon(rings=[ring])
        assert poly.wkt == "POLYGON ((0 0, 10 0, 10 10, 0 0))"


class TestMultiLineString:
    def test_multilinestring(self):
        line1 = LineString(points=[(0, 0), (1, 1)])
        line2 = LineString(points=[(2, 2), (3, 3)])
        mls = MultiLineString(lines=[line1, line2])
        assert len(mls) == 2

    def test_multilinestring_wkt(self):
        line1 = LineString(points=[(0, 0), (1, 1)])
        line2 = LineString(points=[(2, 2), (3, 3)])
        mls = MultiLineString(lines=[line1, line2])
        assert mls.wkt == "MULTILINESTRING ((0 0, 1 1), (2 2, 3 3))"

    def test_multilinestring_iteration(self):
        line1 = LineString(points=[(0, 0), (1, 1)])
        line2 = LineString(points=[(2, 2), (3, 3)])
        mls = MultiLineString(lines=[line1, line2])
        lines = list(mls)
        assert len(lines) == 2


class TestCoordinateSystem:
    def test_default_values(self):
        cs = CoordinateSystem()
        assert cs.x_origin == -20037700
        assert cs.y_origin == -30241100
        assert cs.xy_scale == 10000

    def test_effective_scale(self):
        cs = CoordinateSystem(xy_scale=10000)
        assert cs.effective_xy_scale == 20000

    def test_custom_values(self):
        cs = CoordinateSystem(
            x_origin=0,
            y_origin=0,
            xy_scale=5000,
            srid=4326
        )
        assert cs.x_origin == 0
        assert cs.srid == 4326
        assert cs.effective_xy_scale == 10000


class TestBoundingBox:
    def test_bbox_values(self):
        bbox = BoundingBox(xmin=-122.5, ymin=47.0, xmax=-122.0, ymax=47.5)
        assert bbox.xmin == -122.5
        assert bbox.ymax == 47.5

    def test_bbox_iteration(self):
        bbox = BoundingBox(xmin=0, ymin=1, xmax=2, ymax=3)
        values = list(bbox)
        assert values == [0, 1, 2, 3]
