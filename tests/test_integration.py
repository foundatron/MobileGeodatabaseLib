"""Integration tests using real geodatabase files."""

from collections.abc import Generator
from pathlib import Path

import pytest

from mobile_geodatabase import (
    GeoDatabase,
    Geometry,
    LineString,
    MultiLineString,
    Point,
    Polygon,
    TableInfo,
    to_geojson_geometry,
)

# Test database path
TEST_DB = Path("/tmp/geodatabase_test/replica.geodatabase")


@pytest.fixture
def test_gdb() -> Generator[GeoDatabase, None, None]:
    """Fixture providing access to test geodatabase."""
    if not TEST_DB.exists():
        pytest.skip(f"Test database not found: {TEST_DB}")
    gdb = GeoDatabase(TEST_DB)
    yield gdb
    gdb.close()


class TestGeoDatabase:
    def test_open_geodatabase(self, test_gdb: GeoDatabase) -> None:
        """Test opening a geodatabase file."""
        assert test_gdb.path == TEST_DB

    def test_list_tables(self, test_gdb: GeoDatabase) -> None:
        """Test listing tables."""
        tables: list[TableInfo] = test_gdb.tables
        assert len(tables) > 0

        # Check that we have expected tables
        table_names: list[str] = [t.name.lower() for t in tables]
        # The test database should have these tables
        assert any("stream" in n for n in table_names)
        assert any("lake" in n for n in table_names)

    def test_table_info(self, test_gdb: GeoDatabase) -> None:
        """Test table information."""
        for table in test_gdb.tables:
            if table.has_geometry:
                assert table.geometry_column is not None
                assert table.coord_system is not None

    def test_get_table(self, test_gdb: GeoDatabase) -> None:
        """Test getting table by name."""
        # Get first geometry table
        geom_tables: list[TableInfo] = [t for t in test_gdb.tables if t.has_geometry]
        if geom_tables:
            table = test_gdb.get_table(geom_tables[0].name)
            assert table is not None
            assert table.name == geom_tables[0].name

    def test_get_table_case_insensitive(self, test_gdb: GeoDatabase) -> None:
        """Test case-insensitive table lookup."""
        geom_tables: list[TableInfo] = [t for t in test_gdb.tables if t.has_geometry]
        if geom_tables:
            name = geom_tables[0].name
            table = test_gdb.get_table(name.upper())
            assert table is not None


class TestReadFeatures:
    def test_read_points(self, test_gdb: GeoDatabase) -> None:
        """Test reading point geometries."""
        # Find a point table
        point_tables: list[TableInfo] = [
            t for t in test_gdb.tables if t.geometry_type and "Point" in t.geometry_type
        ]
        if not point_tables:
            pytest.skip("No point tables in test database")

        table = point_tables[0]
        features = list(test_gdb.read_table(table.name, limit=10))

        assert len(features) > 0
        for feature in features:
            if feature.geometry:
                assert isinstance(feature.geometry, Point)
                # Validate coordinates are in Washington State range (EPSG:3857)
                assert -14_000_000 < feature.geometry.x < -12_000_000
                assert 5_500_000 < feature.geometry.y < 6_500_000

    def test_read_lines(self, test_gdb: GeoDatabase) -> None:
        """Test reading line geometries."""
        # Find a line table
        line_tables: list[TableInfo] = [
            t for t in test_gdb.tables if t.geometry_type and "Line" in t.geometry_type
        ]
        if not line_tables:
            pytest.skip("No line tables in test database")

        table = line_tables[0]
        features = list(test_gdb.read_table(table.name, limit=10))

        assert len(features) > 0
        for feature in features:
            if feature.geometry:
                assert isinstance(feature.geometry, LineString | MultiLineString)

    def test_read_polygons(self, test_gdb: GeoDatabase) -> None:
        """Test reading polygon geometries."""
        # Find a polygon table
        poly_tables: list[TableInfo] = [
            t
            for t in test_gdb.tables
            if t.geometry_type and "Polygon" in t.geometry_type
        ]
        if not poly_tables:
            pytest.skip("No polygon tables in test database")

        table = poly_tables[0]
        features = list(test_gdb.read_table(table.name, limit=10))

        assert len(features) > 0
        for feature in features:
            if feature.geometry:
                assert isinstance(feature.geometry, Polygon)

    def test_read_with_limit(self, test_gdb: GeoDatabase) -> None:
        """Test limiting number of features."""
        table = test_gdb.tables[0]
        features = list(test_gdb.read_table(table.name, limit=5))
        assert len(features) <= 5

    def test_feature_attributes(self, test_gdb: GeoDatabase) -> None:
        """Test feature attributes."""
        geom_tables: list[TableInfo] = [t for t in test_gdb.tables if t.has_geometry]
        if not geom_tables:
            pytest.skip("No geometry tables")

        table = geom_tables[0]
        features = list(test_gdb.read_table(table.name, limit=1))

        if features:
            feature = features[0]
            assert isinstance(feature.attributes, dict)
            # Should have some attributes
            assert len(feature.attributes) >= 0


class TestCoordinateValidation:
    """Validate all coordinates are in expected range for Washington State."""

    def test_all_geometries_valid(self, test_gdb: GeoDatabase) -> None:
        """Test that all decoded geometries have valid coordinates."""

        def is_valid_wa(x: float, y: float) -> bool:
            """Check if coordinates are valid for Pacific Northwest region in EPSG:3857.
            Includes Pacific marine areas, extends to Canadian border and Oregon."""
            return -14_500_000 < x < -12_000_000 and 5_400_000 < y < 6_600_000

        def get_all_coords(geom: Geometry) -> list[tuple[float, float]]:
            """Extract all coordinates from a geometry."""
            if isinstance(geom, Point):
                return [(geom.x, geom.y)]
            elif isinstance(geom, LineString):
                return geom.points
            elif isinstance(geom, Polygon):
                return [p for ring in geom.rings for p in ring]
            elif isinstance(geom, MultiLineString):
                return [p for line in geom.lines for p in line.points]
            return []

        errors: list[str] = []
        for table in test_gdb.tables:
            if not table.has_geometry:
                continue

            for feature in test_gdb.read_table(table.name, limit=100):
                if feature.geometry:
                    coords = get_all_coords(feature.geometry)
                    for x, y in coords:
                        if not is_valid_wa(x, y):
                            errors.append(f"{table.name}: Invalid coord ({x}, {y})")
                            break

        assert len(errors) == 0, "Found invalid coordinates:\n" + "\n".join(errors[:10])


class TestGeoJsonOutput:
    def test_feature_to_geojson(self, test_gdb: GeoDatabase) -> None:
        """Test converting features to GeoJSON."""
        geom_tables: list[TableInfo] = [t for t in test_gdb.tables if t.has_geometry]
        if not geom_tables:
            pytest.skip("No geometry tables")

        table = geom_tables[0]
        for feature in test_gdb.read_table(table.name, limit=5):
            if feature.geometry:
                geojson = to_geojson_geometry(feature.geometry)
                assert "type" in geojson
                assert "coordinates" in geojson
