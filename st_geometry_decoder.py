#!/usr/bin/env python3
"""
Esri Mobile Geodatabase ST_Geometry Blob Decoder

This module decodes the proprietary ST_Geometry blob format used in Esri Mobile
Geodatabases (.geodatabase files). It was reverse-engineered from the WDFW
Washington State fishing regulations geodatabase.

Author: Reverse engineered Dec 2025
License: Public Domain / CC0

Usage:
    from st_geometry_decoder import decode_geometry

    # Decode a blob from the database
    geom = decode_geometry(blob, coord_system_info)
    print(geom.wkt)
"""

import struct
from dataclasses import dataclass
from typing import List, Tuple, Optional, Union
from enum import IntEnum


class GeometryType(IntEnum):
    """Esri geometry type codes from st_geometry_columns.geometry_type"""
    POINT = 1
    LINESTRING = 2
    POLYGON = 3
    MULTIPOINT = 4
    MULTILINESTRING = 5  # Line in Esri terms
    MULTIPOLYGON = 6
    # Z variants add 1000
    POINTZ = 1001
    LINESTRINGZ = 1002
    POLYGONZ = 1003
    MULTIPOINTZ = 1004
    MULTILINESTRINGZ = 1005  # Also 2005 seen in practice
    MULTIPOLYGONZ = 1006


@dataclass
class CoordinateSystem:
    """Coordinate system parameters from the geodatabase XML definition"""
    x_origin: float = -20037700
    y_origin: float = -30241100
    xy_scale: float = 10000  # Metadata says 10000, but encoding uses 2x this
    z_origin: float = -100000
    z_scale: float = 10000

    @property
    def effective_xy_scale(self) -> float:
        """The actual scale used in encoding (2x metadata value)"""
        return self.xy_scale * 2


@dataclass
class BoundingBox:
    """Geometry bounding box"""
    xmin: float
    ymin: float
    xmax: float
    ymax: float


@dataclass
class Point:
    """A 2D or 3D point"""
    x: float
    y: float
    z: Optional[float] = None

    @property
    def wkt(self) -> str:
        if self.z is not None:
            return f"POINT Z ({self.x} {self.y} {self.z})"
        return f"POINT ({self.x} {self.y})"


@dataclass
class LineString:
    """A line string (polyline)"""
    points: List[Tuple[float, float]]
    z_values: Optional[List[float]] = None

    @property
    def wkt(self) -> str:
        if self.z_values:
            coords = ", ".join(f"{p[0]} {p[1]} {z}"
                              for p, z in zip(self.points, self.z_values))
            return f"LINESTRING Z ({coords})"
        coords = ", ".join(f"{p[0]} {p[1]}" for p in self.points)
        return f"LINESTRING ({coords})"


@dataclass
class Polygon:
    """A polygon with optional holes"""
    rings: List[List[Tuple[float, float]]]  # First ring is exterior, rest are holes
    z_values: Optional[List[List[float]]] = None

    @property
    def wkt(self) -> str:
        ring_strs = []
        for i, ring in enumerate(self.rings):
            if self.z_values:
                coords = ", ".join(f"{p[0]} {p[1]} {z}"
                                  for p, z in zip(ring, self.z_values[i]))
            else:
                coords = ", ".join(f"{p[0]} {p[1]}" for p in ring)
            ring_strs.append(f"({coords})")

        if self.z_values:
            return f"POLYGON Z ({', '.join(ring_strs)})"
        return f"POLYGON ({', '.join(ring_strs)})"


@dataclass
class MultiLineString:
    """Multiple line strings"""
    lines: List[LineString]

    @property
    def wkt(self) -> str:
        has_z = any(l.z_values for l in self.lines)
        line_strs = []
        for line in self.lines:
            if has_z and line.z_values:
                coords = ", ".join(f"{p[0]} {p[1]} {z}"
                                  for p, z in zip(line.points, line.z_values))
            else:
                coords = ", ".join(f"{p[0]} {p[1]}" for p in line.points)
            line_strs.append(f"({coords})")

        if has_z:
            return f"MULTILINESTRING Z ({', '.join(line_strs)})"
        return f"MULTILINESTRING ({', '.join(line_strs)})"


@dataclass
class MultiPolygon:
    """Multiple polygons"""
    polygons: List[Polygon]

    @property
    def wkt(self) -> str:
        has_z = any(p.z_values for p in self.polygons)
        poly_strs = []
        for poly in self.polygons:
            ring_strs = []
            for i, ring in enumerate(poly.rings):
                if has_z and poly.z_values:
                    coords = ", ".join(f"{p[0]} {p[1]} {z}"
                                      for p, z in zip(ring, poly.z_values[i]))
                else:
                    coords = ", ".join(f"{p[0]} {p[1]}" for p in ring)
                ring_strs.append(f"({coords})")
            poly_strs.append(f"({', '.join(ring_strs)})")

        if has_z:
            return f"MULTIPOLYGON Z ({', '.join(poly_strs)})"
        return f"MULTIPOLYGON ({', '.join(poly_strs)})"


Geometry = Union[Point, LineString, Polygon, MultiLineString, MultiPolygon]


class STGeometryDecoder:
    """
    Decoder for Esri ST_Geometry blob format in Mobile Geodatabases.

    Blob Structure:
    ===============
    - Bytes 0-3: Magic header (0x64 0x11 0x0F 0x00)
    - Bytes 4-7: Point count (uint32 little-endian)
    - Bytes 8+: Variable structure depending on geometry type

    For Points:
    - Bytes 8-17: Fixed header (type flags, size info, padding)
    - Bytes 18+: Varint-encoded X, Y coordinates

    For Lines/Polygons:
    - Byte 8+: Varint for size hint
    - Next varint: Geometry flags
    - 4 varints: Bounding box (xmin, ymin, xmax, ymax)
    - Variable varints: Part information
    - First coordinate: Absolute X, Y as varints
    - Remaining coordinates: Zigzag-encoded deltas
    - Trailing bytes: Z values (if applicable)

    Coordinate Encoding:
    ====================
    - Coordinates are stored as scaled integers
    - Formula: real_coord = (encoded_value / effective_scale) + origin
    - IMPORTANT: effective_scale = 2 * metadata_xy_scale
    - Delta encoding uses zigzag for signed values

    Multi-Part Geometries:
    ======================
    - Each part starts with an ABSOLUTE coordinate (large raw value)
    - Subsequent points within a part use DELTA encoding
    - To detect new parts: check if raw value > COORD_THRESHOLD
    """

    MAGIC = bytes([0x64, 0x11, 0x0F, 0x00])

    # Threshold to distinguish coordinates from metadata varints
    # For EPSG:3857 with standard origin/scale, coordinates are typically 100-800 billion
    # Part info varints are typically < 10 million
    COORD_THRESHOLD = 100_000_000_000  # 100 billion

    def __init__(self, coord_system: CoordinateSystem = None):
        self.cs = coord_system or CoordinateSystem()

    def _read_varint(self, data: bytes, offset: int) -> Tuple[int, int]:
        """Read an unsigned varint, return (value, new_offset)"""
        result = 0
        shift = 0
        while offset < len(data):
            byte = data[offset]
            result |= (byte & 0x7F) << shift
            offset += 1
            if (byte & 0x80) == 0:
                break
            shift += 7
        return result, offset

    def _zigzag_decode(self, n: int) -> int:
        """Decode zigzag-encoded signed integer"""
        return (n >> 1) ^ -(n & 1)

    def _raw_to_coord(self, raw_x: int, raw_y: int) -> Tuple[float, float]:
        """Convert raw encoded values to real coordinates"""
        scale = self.cs.effective_xy_scale
        x = raw_x / scale + self.cs.x_origin
        y = raw_y / scale + self.cs.y_origin
        return (x, y)

    def decode(self, blob: bytes) -> Geometry:
        """
        Decode an ST_Geometry blob to a geometry object.

        Args:
            blob: The raw blob bytes from the shape column

        Returns:
            A Point, LineString, Polygon, MultiLineString, or MultiPolygon

        Raises:
            ValueError: If the blob format is invalid
        """
        if len(blob) < 8:
            raise ValueError(f"Blob too short: {len(blob)} bytes")

        if blob[:4] != self.MAGIC:
            raise ValueError(f"Invalid magic header: {blob[:4].hex()}")

        point_count = struct.unpack('<I', blob[4:8])[0]

        if point_count == 0:
            raise ValueError("Empty geometry (point count = 0)")

        # Determine geometry type from structure
        if point_count == 1 and len(blob) == 30:
            return self._decode_point(blob)
        else:
            return self._decode_complex(blob, point_count)

    def _decode_point(self, blob: bytes) -> Point:
        """Decode a point geometry (fixed 30-byte structure)"""
        # Coordinates start at byte 18 for points
        pos = 18
        x_raw, pos = self._read_varint(blob, pos)
        y_raw, pos = self._read_varint(blob, pos)

        x, y = self._raw_to_coord(x_raw, y_raw)
        return Point(x=x, y=y)

    def _decode_complex(self, blob: bytes, point_count: int) -> Geometry:
        """Decode line/polygon geometries with multi-part support"""
        pos = 8

        # Read header varints
        size_hint, pos = self._read_varint(blob, pos)
        geom_flags, pos = self._read_varint(blob, pos)

        # Bounding box (4 large varints)
        xmin_raw, pos = self._read_varint(blob, pos)
        ymin_raw, pos = self._read_varint(blob, pos)
        xmax_raw, pos = self._read_varint(blob, pos)
        ymax_raw, pos = self._read_varint(blob, pos)

        bbox = BoundingBox(
            *self._raw_to_coord(xmin_raw, ymin_raw),
            *self._raw_to_coord(xmax_raw, ymax_raw)
        )

        # Part information - variable length structure after bbox
        # All part info varints are small (< 100 billion), coordinates are large (> 100 billion)
        part_info = []
        while pos < len(blob):
            v, new_pos = self._read_varint(blob, pos)
            if v > self.COORD_THRESHOLD:
                # This is the first X coordinate
                x_raw = v
                pos = new_pos
                break
            part_info.append(v)
            pos = new_pos
            # Safety limit - part info can be large for complex multi-part geometries
            if len(part_info) > 10000:
                raise ValueError("Could not find coordinate start")

        # Read first Y coordinate
        y_raw, pos = self._read_varint(blob, pos)

        # Decode coordinates with multi-part detection
        # Key insight: Each part starts with an ABSOLUTE coordinate (large raw values)
        # Within a part, coordinates are DELTA encoded (small zigzag values)
        # When we read a "delta" that's > 100M, it's actually a new part's absolute coord

        parts = []  # List of point lists
        current_part = []
        curr_x, curr_y = x_raw, y_raw
        current_part.append(self._raw_to_coord(curr_x, curr_y))

        points_read = 1
        while points_read < point_count and pos < len(blob):
            v1, pos = self._read_varint(blob, pos)
            v2, pos = self._read_varint(blob, pos)

            if v1 > self.COORD_THRESHOLD:
                # This is an absolute coordinate - new part!
                if current_part:
                    parts.append(current_part)
                current_part = []
                curr_x, curr_y = v1, v2
                current_part.append(self._raw_to_coord(curr_x, curr_y))
            else:
                # Delta encoded coordinate
                dx = self._zigzag_decode(v1)
                dy = self._zigzag_decode(v2)
                curr_x += dx
                curr_y += dy
                current_part.append(self._raw_to_coord(curr_x, curr_y))

            points_read += 1

        # Don't forget the last part
        if current_part:
            parts.append(current_part)

        # Determine geometry type from flags
        # Lower 4 bits: 1=Point, 4=Line, 8=Polygon
        # Higher bits: flags (e.g., has Z values)
        base_type = geom_flags & 0x0F
        is_polygon = base_type == 8

        if is_polygon:
            if len(parts) == 1:
                return Polygon(rings=parts)
            else:
                # Multi-part polygon - could be MultiPolygon or Polygon with holes
                # For simplicity, treat as multiple rings (first is exterior, rest are holes)
                return Polygon(rings=parts)
        else:
            # Line geometry
            if len(parts) == 1:
                return LineString(points=parts[0])
            else:
                # MultiLineString
                lines = [LineString(points=p) for p in parts]
                return MultiLineString(lines=lines)


def decode_geometry(blob: bytes,
                    x_origin: float = -20037700,
                    y_origin: float = -30241100,
                    xy_scale: float = 10000) -> Geometry:
    """
    Convenience function to decode an ST_Geometry blob.

    Args:
        blob: Raw bytes from the shape column
        x_origin: X origin from coordinate system definition
        y_origin: Y origin from coordinate system definition
        xy_scale: XY scale from coordinate system definition (will be doubled internally)

    Returns:
        Decoded geometry object with .wkt property
    """
    cs = CoordinateSystem(
        x_origin=x_origin,
        y_origin=y_origin,
        xy_scale=xy_scale
    )
    decoder = STGeometryDecoder(cs)
    return decoder.decode(blob)


def get_coordinate_system_from_db(db_path: str, table_name: str) -> CoordinateSystem:
    """
    Extract coordinate system parameters from geodatabase XML definition.

    Args:
        db_path: Path to the .geodatabase file
        table_name: Name of the geometry table

    Returns:
        CoordinateSystem with extracted parameters
    """
    import sqlite3
    import re

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT Definition FROM GDB_Items WHERE Name = ?",
        (f"main.{table_name}",)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return CoordinateSystem()  # Return defaults

    xml = row[0]

    def extract(pattern):
        match = re.search(pattern, xml)
        return float(match.group(1)) if match else None

    return CoordinateSystem(
        x_origin=extract(r'<XOrigin>([^<]+)') or -20037700,
        y_origin=extract(r'<YOrigin>([^<]+)') or -30241100,
        xy_scale=extract(r'<XYScale>([^<]+)') or 10000,
        z_origin=extract(r'<ZOrigin>([^<]+)') or -100000,
        z_scale=extract(r'<ZScale>([^<]+)') or 10000,
    )


# Example usage and testing
if __name__ == "__main__":
    import sqlite3

    DB_PATH = "/tmp/geodatabase_test/replica.geodatabase"

    print("=" * 60)
    print("Esri Mobile Geodatabase ST_Geometry Decoder Test")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Coordinate validation for Washington State (EPSG:3857)
    def is_valid_wa(x, y):
        return -14_000_000 < x < -12_000_000 and 5_500_000 < y < 6_500_000

    # Test Point
    print("\n--- Testing Point Decode ---")
    cursor.execute("SELECT shape FROM sportPamphletWaterAccessSites WHERE shape IS NOT NULL LIMIT 1")
    blob = cursor.fetchone()[0]
    cs = get_coordinate_system_from_db(DB_PATH, "sportPamphletWaterAccessSites")
    decoder = STGeometryDecoder(cs)
    geom = decoder.decode(blob)
    print(f"Geometry type: {type(geom).__name__}")
    print(f"Coordinates: ({geom.x:.2f}, {geom.y:.2f})")
    print(f"Valid for WA: {is_valid_wa(geom.x, geom.y)}")

    # Test LineString (multi-part)
    print("\n--- Testing MultiLineString Decode ---")
    cursor.execute("SELECT shape FROM SportPamphletStream WHERE shape IS NOT NULL LIMIT 1")
    blob = cursor.fetchone()[0]
    cs = get_coordinate_system_from_db(DB_PATH, "SportPamphletStream")
    decoder = STGeometryDecoder(cs)
    geom = decoder.decode(blob)
    print(f"Geometry type: {type(geom).__name__}")

    if isinstance(geom, MultiLineString):
        print(f"Part count: {len(geom.lines)}")
        total_pts = sum(len(line.points) for line in geom.lines)
        print(f"Total points: {total_pts}")
        all_valid = all(is_valid_wa(*p) for line in geom.lines for p in line.points)
        print(f"All coords valid: {all_valid}")
        print(f"First part first pt: ({geom.lines[0].points[0][0]:.2f}, {geom.lines[0].points[0][1]:.2f})")
        print(f"Last part last pt: ({geom.lines[-1].points[-1][0]:.2f}, {geom.lines[-1].points[-1][1]:.2f})")
    else:
        print(f"Point count: {len(geom.points)}")
        print(f"First point: ({geom.points[0][0]:.2f}, {geom.points[0][1]:.2f})")
        print(f"Last point: ({geom.points[-1][0]:.2f}, {geom.points[-1][1]:.2f})")

    # Test Polygon
    print("\n--- Testing Polygon Decode ---")
    cursor.execute("SELECT shape FROM sportPamphletCities WHERE shape IS NOT NULL LIMIT 1")
    blob = cursor.fetchone()[0]
    cs = get_coordinate_system_from_db(DB_PATH, "sportPamphletCities")
    decoder = STGeometryDecoder(cs)
    geom = decoder.decode(blob)
    print(f"Geometry type: {type(geom).__name__}")
    print(f"Ring count: {len(geom.rings)}")
    total_pts = sum(len(ring) for ring in geom.rings)
    print(f"Total points: {total_pts}")
    all_valid = all(is_valid_wa(*p) for ring in geom.rings for p in ring)
    print(f"All coords valid: {all_valid}")

    # Test multiple geometries for validation
    print("\n--- Batch Validation ---")
    tables = [
        ("sportPamphletWaterAccessSites", "Point"),
        ("SportPamphletStream", "MultiLineStringZ"),
        ("sportPamphletCities", "Polygon"),
        ("SportPamphletLake", "PolygonZ"),
    ]

    for table, geom_type in tables:
        cursor.execute(f"SELECT shape FROM {table} WHERE shape IS NOT NULL LIMIT 50")
        rows = cursor.fetchall()
        cs = get_coordinate_system_from_db(DB_PATH, table)
        decoder = STGeometryDecoder(cs)

        valid_count = 0
        total_count = len(rows)

        for (blob,) in rows:
            try:
                geom = decoder.decode(blob)
                # Check all coordinates are valid
                if isinstance(geom, Point):
                    coords = [(geom.x, geom.y)]
                elif isinstance(geom, LineString):
                    coords = geom.points
                elif isinstance(geom, Polygon):
                    coords = [p for ring in geom.rings for p in ring]
                elif isinstance(geom, MultiLineString):
                    coords = [p for line in geom.lines for p in line.points]
                else:
                    coords = []

                if all(is_valid_wa(*c) for c in coords):
                    valid_count += 1
            except Exception as e:
                pass  # Count as invalid

        print(f"{table}: {valid_count}/{total_count} valid")

    conn.close()

    print("\n" + "=" * 60)
    print("Decoder test complete!")
    print("=" * 60)
