"""
GeoDatabase class for reading Esri Mobile Geodatabase files.

This module provides a high-level API for accessing .geodatabase files,
which are SQLite databases containing spatial data encoded in ST_Geometry format.
"""

import contextlib
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any

from .decoder import STGeometryDecoder
from .geometry import CoordinateSystem, Geometry


@dataclass
class Feature:
    """
    A feature (row) from a geodatabase table.

    Attributes:
        geometry: The feature's geometry (Point, LineString, Polygon, etc.)
        attributes: Dictionary of attribute values keyed by column name
        fid: Feature ID (primary key)
    """

    geometry: Geometry | None
    attributes: dict[str, Any]
    fid: int | None = None

    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access to attributes"""
        return self.attributes[key]

    def get(self, key: str, default: Any = None) -> Any:
        """Get attribute with default"""
        return self.attributes.get(key, default)


@dataclass
class TableInfo:
    """
    Information about a table in the geodatabase.

    Attributes:
        name: Table name
        geometry_column: Name of the geometry column (usually 'shape')
        geometry_type: Type of geometry stored
        geometry_type_code: Numeric type code from st_geometry_columns
        srid: Spatial reference ID
        coord_system: Coordinate system parameters
        columns: List of column names
        row_count: Number of rows in the table
    """

    name: str
    geometry_column: str | None = None
    geometry_type: str | None = None
    geometry_type_code: int | None = None
    srid: int | None = None
    coord_system: CoordinateSystem | None = None
    columns: list[str] = field(default_factory=lambda: [])
    row_count: int = 0

    @property
    def has_geometry(self) -> bool:
        """Check if this table has a geometry column"""
        return self.geometry_column is not None


class GeoDatabase:
    """
    Reader for Esri Mobile Geodatabase files (.geodatabase).

    This class provides a high-level API for reading spatial data from
    Mobile Geodatabase files without requiring Esri's proprietary libraries.

    Example:
        >>> gdb = GeoDatabase("file.geodatabase")
        >>> for table in gdb.tables:
        ...     print(table.name, table.geometry_type)
        ...
        >>> for feature in gdb.read_table("Rivers"):
        ...     print(feature.geometry.wkt)
        ...     print(feature.attributes)

    Attributes:
        path: Path to the geodatabase file
        tables: List of TableInfo objects describing available tables
    """

    def __init__(self, path: str | Path):
        """
        Open a geodatabase file.

        Args:
            path: Path to the .geodatabase file

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file is not a valid geodatabase
        """
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Geodatabase not found: {self.path}")

        self._conn: sqlite3.Connection | None = None
        self._tables: list[TableInfo] | None = None
        self._table_map: dict[str, TableInfo] = {}
        self._decoders: dict[str, STGeometryDecoder] = {}

        # Validate it's a geodatabase
        self._validate()

    def _validate(self):
        """Validate this is a valid geodatabase file"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Check for required system tables
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='GDB_Items'"
                )
                if not cursor.fetchone():
                    raise ValueError("Not a valid geodatabase: missing GDB_Items table")
        except sqlite3.Error as e:
            raise ValueError(f"Invalid geodatabase file: {e}") from e

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        """Close the database connection"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "GeoDatabase":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def tables(self) -> list[TableInfo]:
        """
        List all tables with geometry in the geodatabase.

        Returns:
            List of TableInfo objects
        """
        if self._tables is None:
            self._load_tables()
        assert self._tables is not None  # _load_tables always sets this
        return self._tables

    @property
    def table_names(self) -> list[str]:
        """List of table names with geometry"""
        return [t.name for t in self.tables]

    def get_table(self, name: str) -> TableInfo | None:
        """
        Get table info by name.

        Args:
            name: Table name (case-insensitive)

        Returns:
            TableInfo or None if not found
        """
        if self._tables is None:
            self._load_tables()
        return self._table_map.get(name.lower())

    def _load_tables(self):
        """Load table information from the database"""
        self._tables = []
        self._table_map = {}

        conn = self._get_connection()
        cursor = conn.cursor()

        # Get geometry tables from st_geometry_columns
        try:
            cursor.execute("""
                SELECT table_name, column_name, geometry_type, srid
                FROM st_geometry_columns
            """)
            geom_info = {row["table_name"]: dict(row) for row in cursor.fetchall()}
        except sqlite3.Error:
            geom_info = {}

        # Get all user tables
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            AND name NOT LIKE 'sqlite_%'
            AND name NOT LIKE 'GDB_%'
            AND name NOT LIKE 'st_%'
        """)

        for (table_name,) in cursor.fetchall():
            # Get column info
            cursor.execute(f"PRAGMA table_info('{table_name}')")
            columns = [row["name"] for row in cursor.fetchall()]

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM '{table_name}'")
            row_count = cursor.fetchone()[0]

            # Build TableInfo
            info = TableInfo(name=table_name, columns=columns, row_count=row_count)

            # Add geometry info if available
            if table_name in geom_info:
                gi = geom_info[table_name]
                info.geometry_column = gi.get("column_name", "shape")
                info.geometry_type_code = gi.get("geometry_type")
                info.srid = gi.get("srid")
                info.geometry_type = self._geometry_type_name(info.geometry_type_code)
                info.coord_system = self._get_coordinate_system(table_name)
            elif "shape" in [c.lower() for c in columns]:
                # Infer geometry column
                for col in columns:
                    if col.lower() == "shape":
                        info.geometry_column = col
                        info.coord_system = self._get_coordinate_system(table_name)
                        break

            self._tables.append(info)
            self._table_map[table_name.lower()] = info

    def _geometry_type_name(self, type_code: int | None) -> str | None:
        """Convert geometry type code to name"""
        if type_code is None:
            return None
        type_map = {
            1: "Point",
            2: "LineString",
            3: "Polygon",
            4: "MultiPoint",
            5: "MultiLineString",
            6: "MultiPolygon",
            1001: "PointZ",
            1002: "LineStringZ",
            1003: "PolygonZ",
            1004: "MultiPointZ",
            1005: "MultiLineStringZ",
            1006: "MultiPolygonZ",
            2005: "MultiLineStringZ",  # Alternative code seen in practice
        }
        return type_map.get(type_code, f"Unknown({type_code})")

    def _get_coordinate_system(self, table_name: str) -> CoordinateSystem:
        """
        Extract coordinate system parameters from geodatabase XML definition.

        Args:
            table_name: Name of the geometry table

        Returns:
            CoordinateSystem with extracted parameters
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Try both with and without 'main.' prefix
        row: sqlite3.Row | None = None
        for name in [f"main.{table_name}", table_name]:
            cursor.execute("SELECT Definition FROM GDB_Items WHERE Name = ?", (name,))
            row = cursor.fetchone()
            if row:
                break

        if not row or not row[0]:
            return CoordinateSystem()

        xml: str = row[0]

        def extract(pattern: str) -> float | None:
            match = re.search(pattern, xml)
            return float(match.group(1)) if match else None

        # Extract SRID from WKID
        srid_match = re.search(r"<WKID>(\d+)</WKID>", xml)
        srid = int(srid_match.group(1)) if srid_match else None

        # Extract WKT
        wkt_match = re.search(r"<WKT>([^<]+)</WKT>", xml)
        wkt = wkt_match.group(1) if wkt_match else None

        return CoordinateSystem(
            x_origin=extract(r"<XOrigin>([^<]+)") or -20037700,
            y_origin=extract(r"<YOrigin>([^<]+)") or -30241100,
            xy_scale=extract(r"<XYScale>([^<]+)") or 10000,
            z_origin=extract(r"<ZOrigin>([^<]+)") or -100000,
            z_scale=extract(r"<ZScale>([^<]+)") or 10000,
            srid=srid,
            wkt=wkt,
        )

    def _get_decoder(self, table_name: str) -> STGeometryDecoder:
        """Get or create a decoder for the given table"""
        key = table_name.lower()
        if key not in self._decoders:
            table = self.get_table(table_name)
            if table and table.coord_system:
                self._decoders[key] = STGeometryDecoder(table.coord_system)
            else:
                self._decoders[key] = STGeometryDecoder()
        return self._decoders[key]

    def read_table(
        self,
        table_name: str,
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
    ) -> Iterator[Feature]:
        """
        Read features from a table.

        Args:
            table_name: Name of the table to read
            columns: List of attribute columns to include (None for all)
            where: Optional SQL WHERE clause (without 'WHERE' keyword)
            limit: Maximum number of features to return

        Yields:
            Feature objects with geometry and attributes

        Raises:
            ValueError: If the table doesn't exist

        Example:
            >>> for feature in gdb.read_table("Rivers", limit=10):
            ...     print(feature.geometry.wkt)
        """
        table = self.get_table(table_name)
        if table is None:
            raise ValueError(f"Table not found: {table_name}")

        conn = self._get_connection()
        cursor = conn.cursor()

        # Build column list
        if columns:
            # Always include geometry column and OBJECTID
            cols = list(columns)
            if table.geometry_column and table.geometry_column not in cols:
                cols.append(table.geometry_column)
            if "OBJECTID" not in cols and "OBJECTID" in table.columns:
                cols.insert(0, "OBJECTID")
            col_str = ", ".join(f'"{c}"' for c in cols)
        else:
            col_str = "*"

        # Build query
        sql = f'SELECT {col_str} FROM "{table_name}"'
        if where:
            sql += f" WHERE {where}"
        if limit:
            sql += f" LIMIT {limit}"

        cursor.execute(sql)
        decoder = self._get_decoder(table_name)

        for row in cursor:
            row_dict = dict(row)

            # Extract geometry
            geometry = None
            if table.geometry_column and table.geometry_column in row_dict:
                blob = row_dict.pop(table.geometry_column)
                if blob:
                    with contextlib.suppress(Exception):
                        geometry = decoder.decode(blob)

            # Extract FID (case-insensitive lookup)
            fid = None
            for key in list(row_dict.keys()):
                if key.lower() == "objectid":
                    fid = row_dict.pop(key)
                    break

            yield Feature(geometry=geometry, attributes=row_dict, fid=fid)

    def read_all(
        self,
        table_name: str,
        columns: list[str] | None = None,
        where: str | None = None,
        limit: int | None = None,
    ) -> list[Feature]:
        """
        Read all features from a table into a list.

        Args:
            table_name: Name of the table to read
            columns: List of attribute columns to include (None for all)
            where: Optional SQL WHERE clause (without 'WHERE' keyword)
            limit: Maximum number of features to return

        Returns:
            List of Feature objects
        """
        return list(
            self.read_table(table_name, columns=columns, where=where, limit=limit)
        )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """
        Execute a raw SQL query.

        Args:
            sql: SQL query string
            params: Query parameters

        Returns:
            Cursor with results
        """
        conn = self._get_connection()
        return conn.execute(sql, params)
