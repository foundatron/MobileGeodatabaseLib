"""Tests for output converters."""

import tempfile
from pathlib import Path

import fiona
from shapely.geometry import LineString as ShapelyLineString
from shapely.geometry import MultiPoint as ShapelyMultiPoint
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon as ShapelyPolygon

from mobile_geodatabase import (
    LineString,
    MultiLineString,
    MultiPoint,
    Point,
    Polygon,
    feature_to_geojson,
    geometry_to_shapely,
    to_geojson_geometry,
    to_wkb,
    to_wkt,
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
        geojson = to_geojson_geometry(pt, to_wgs84=False)
        assert geojson["type"] == "Point"
        assert geojson["coordinates"] == [-122.0, 47.0]

    def test_point_z_geojson(self):
        pt = Point(x=-122.0, y=47.0, z=100.0)
        geojson = to_geojson_geometry(pt, to_wgs84=False)
        assert geojson["coordinates"] == [-122.0, 47.0, 100.0]

    def test_linestring_geojson(self):
        line = LineString(points=[(0, 0), (1, 1), (2, 2)])
        geojson = to_geojson_geometry(line, to_wgs84=False)
        assert geojson["type"] == "LineString"
        assert geojson["coordinates"] == [[0, 0], [1, 1], [2, 2]]

    def test_polygon_geojson(self):
        poly = Polygon(rings=[[(0, 0), (10, 0), (10, 10), (0, 0)]])
        geojson = to_geojson_geometry(poly, to_wgs84=False)
        assert geojson["type"] == "Polygon"
        assert len(geojson["coordinates"]) == 1
        assert geojson["coordinates"][0] == [[0, 0], [10, 0], [10, 10], [0, 0]]

    def test_multilinestring_geojson(self):
        line1 = LineString(points=[(0, 0), (1, 1)])
        line2 = LineString(points=[(2, 2), (3, 3)])
        mls = MultiLineString(lines=[line1, line2])
        geojson = to_geojson_geometry(mls, to_wgs84=False)
        assert geojson["type"] == "MultiLineString"
        assert len(geojson["coordinates"]) == 2


class TestFeatureToGeoJson:
    def test_feature_with_geometry(self):
        pt = Point(x=-122.0, y=47.0)
        feature = Feature(geometry=pt, attributes={"name": "Test", "value": 42}, fid=1)
        geojson = feature_to_geojson(feature)

        assert geojson["type"] == "Feature"
        assert geojson["id"] == 1
        assert geojson["properties"]["name"] == "Test"
        assert geojson["properties"]["value"] == 42
        assert geojson["geometry"]["type"] == "Point"

    def test_feature_without_geometry(self):
        feature = Feature(geometry=None, attributes={"name": "NoGeom"})
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
        assert wkb[1:5] == b"\x01\x00\x00\x00"
        # Remaining bytes are coordinates
        assert len(wkb) == 21  # 1 + 4 + 8 + 8

    def test_linestring_wkb(self):
        line = LineString(points=[(0, 0), (1, 1)])
        wkb = to_wkb(line)

        assert wkb[0] == 1  # Little endian
        # Type 2 = LineString
        assert wkb[1:5] == b"\x02\x00\x00\x00"

    def test_wkb_big_endian(self):
        pt = Point(x=1.0, y=2.0)
        wkb = to_wkb(pt, big_endian=True)

        assert wkb[0] == 0  # Big endian


class TestGeometryToShapely:
    """Tests for converting library geometries to Shapely geometries."""

    def test_point_to_shapely(self):
        """Test Point conversion to Shapely."""
        pt = Point(x=-122.0, y=47.0)
        shapely_pt = geometry_to_shapely(pt)

        assert isinstance(shapely_pt, ShapelyPoint)
        assert shapely_pt.x == -122.0
        assert shapely_pt.y == 47.0

    def test_point_z_to_shapely(self):
        """Test Point with Z conversion to Shapely."""
        pt = Point(x=-122.0, y=47.0, z=100.0)
        shapely_pt = geometry_to_shapely(pt)

        assert isinstance(shapely_pt, ShapelyPoint)
        assert shapely_pt.has_z
        assert shapely_pt.z == 100.0

    def test_linestring_to_shapely(self):
        """Test LineString conversion to Shapely."""
        line = LineString(points=[(0, 0), (1, 1), (2, 2)])
        shapely_line = geometry_to_shapely(line)

        assert isinstance(shapely_line, ShapelyLineString)
        coords = list(shapely_line.coords)
        assert coords == [(0, 0), (1, 1), (2, 2)]

    def test_polygon_to_shapely(self):
        """Test Polygon conversion to Shapely."""
        poly = Polygon(rings=[[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]])
        shapely_poly = geometry_to_shapely(poly)

        assert isinstance(shapely_poly, ShapelyPolygon)
        assert shapely_poly.exterior is not None
        exterior_coords = list(shapely_poly.exterior.coords)
        assert exterior_coords == [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]

    def test_polygon_with_holes_to_shapely(self):
        """Test Polygon with interior rings conversion to Shapely."""
        poly = Polygon(
            rings=[
                [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],  # exterior
                [(2, 2), (8, 2), (8, 8), (2, 8), (2, 2)],  # hole
            ]
        )
        shapely_poly = geometry_to_shapely(poly)

        assert isinstance(shapely_poly, ShapelyPolygon)
        assert len(list(shapely_poly.interiors)) == 1

    def test_multipoint_to_shapely(self):
        """Test MultiPoint conversion to Shapely."""
        mp = MultiPoint(points=[Point(x=0, y=0), Point(x=1, y=1), Point(x=2, y=2)])
        shapely_mp = geometry_to_shapely(mp)

        assert isinstance(shapely_mp, ShapelyMultiPoint)
        assert len(shapely_mp.geoms) == 3


class TestGeoPackageWithFiona:
    """Tests for GeoPackage file creation using fiona."""

    def test_fiona_geopackage_can_be_read(self):
        """Test that a GeoPackage created with fiona can be read back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gpkg_path = Path(tmpdir) / "test.gpkg"

            # Create a simple GeoPackage with fiona
            schema = {"geometry": "Point", "properties": {"name": "str"}}
            with fiona.open(
                str(gpkg_path),
                "w",
                driver="GPKG",
                crs="EPSG:4326",
                schema=schema,
                layer="test_layer",
            ) as dst:
                dst.write(
                    {
                        "geometry": {"type": "Point", "coordinates": [-122.0, 47.0]},
                        "properties": {"name": "Test Point"},
                    }
                )

            # Read it back
            with fiona.open(str(gpkg_path), layer="test_layer") as src:
                features = list(src)
                assert len(features) == 1
                assert features[0]["properties"]["name"] == "Test Point"

    def test_geopackage_has_correct_crs(self):
        """Test that GeoPackage created with fiona has correct CRS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gpkg_path = Path(tmpdir) / "test.gpkg"

            schema = {"geometry": "Point", "properties": {}}
            with fiona.open(
                str(gpkg_path),
                "w",
                driver="GPKG",
                crs="EPSG:3857",
                schema=schema,
                layer="test_layer",
            ) as dst:
                dst.write(
                    {
                        "geometry": {"type": "Point", "coordinates": [0, 0]},
                        "properties": {},
                    }
                )

            # Verify CRS
            with fiona.open(str(gpkg_path), layer="test_layer") as src:
                crs = src.crs
                # Fiona returns CRS as a dict or pyproj CRS
                assert crs is not None
                # Check that it's EPSG:3857
                crs_str = str(crs)
                assert "3857" in crs_str or "Mercator" in crs_str

    def test_geopackage_linestring_geometry(self):
        """Test GeoPackage with LineString geometries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gpkg_path = Path(tmpdir) / "test.gpkg"

            schema = {"geometry": "LineString", "properties": {"id": "int"}}
            with fiona.open(
                str(gpkg_path),
                "w",
                driver="GPKG",
                crs="EPSG:4326",
                schema=schema,
                layer="lines",
            ) as dst:
                dst.write(
                    {
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[0, 0], [1, 1], [2, 2]],
                        },
                        "properties": {"id": 1},
                    }
                )

            with fiona.open(str(gpkg_path), layer="lines") as src:
                features = list(src)
                assert len(features) == 1
                geom = features[0]["geometry"]
                assert geom["type"] == "LineString"
                assert len(geom["coordinates"]) == 3

    def test_geopackage_polygon_geometry(self):
        """Test GeoPackage with Polygon geometries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gpkg_path = Path(tmpdir) / "test.gpkg"

            schema = {"geometry": "Polygon", "properties": {"area": "float"}}
            with fiona.open(
                str(gpkg_path),
                "w",
                driver="GPKG",
                crs="EPSG:4326",
                schema=schema,
                layer="polygons",
            ) as dst:
                dst.write(
                    {
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
                            ],
                        },
                        "properties": {"area": 100.0},
                    }
                )

            with fiona.open(str(gpkg_path), layer="polygons") as src:
                features = list(src)
                assert len(features) == 1
                geom = features[0]["geometry"]
                assert geom["type"] == "Polygon"
                assert features[0]["properties"]["area"] == 100.0
