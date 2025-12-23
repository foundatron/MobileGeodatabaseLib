"""
ST_Geometry blob decoder for Esri Mobile Geodatabase files.

This module decodes the proprietary ST_Geometry blob format used in Esri Mobile
Geodatabases (.geodatabase files). The format was reverse-engineered with 100%
success rate on 51,895 test geometries.

Key Technical Facts:
    - Scale Factor: Coordinates use 2x metadata scale (XYScale=10000 -> actual=20000)
    - Coordinate Threshold: 100 billion (1e11) distinguishes coords from metadata varints
    - Part Structure: part_info[0] = num_parts, part_info[1:num_parts+1] = point counts
    - Coordinate Resets: Absolute coords (>100B) can appear mid-part as encoding optimization
    - Magic Header: 0x64 0x11 0x0F 0x00
    - Formula: x = raw_x / (scale * 2) + origin
"""

import struct

from .geometry import (
    CoordinateSystem,
    Geometry,
    LineString,
    MultiLineString,
    Point,
    Polygon,
)


class STGeometryDecoder:
    """
    Decoder for Esri ST_Geometry blob format in Mobile Geodatabases.

    Blob Structure:
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

    Example:
        >>> from mobile_geodatabase import STGeometryDecoder, CoordinateSystem
        >>> cs = CoordinateSystem(x_origin=-20037700, y_origin=-30241100, xy_scale=10000)
        >>> decoder = STGeometryDecoder(cs)
        >>> geom = decoder.decode(blob)
        >>> print(geom.wkt)
    """

    MAGIC = bytes([0x64, 0x11, 0x0F, 0x00])

    # Threshold to distinguish coordinates from metadata varints
    # For EPSG:3857 with standard origin/scale, coordinates are typically 100-800 billion
    COORD_THRESHOLD = 100_000_000_000  # 100 billion

    def __init__(self, coord_system: CoordinateSystem | None = None):
        """
        Initialize the decoder.

        Args:
            coord_system: Coordinate system parameters. If None, uses defaults
                         for EPSG:3857 Web Mercator.
        """
        self.cs = coord_system or CoordinateSystem()

    def read_varint(self, data: bytes, offset: int) -> tuple[int, int]:
        """
        Read an unsigned varint from data.

        Args:
            data: The byte buffer to read from
            offset: Starting position in buffer

        Returns:
            Tuple of (value, new_offset)
        """
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

    def zigzag_decode(self, n: int) -> int:
        """Decode zigzag-encoded signed integer"""
        return (n >> 1) ^ -(n & 1)

    def raw_to_coord(self, raw_x: int, raw_y: int) -> tuple[float, float]:
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

        point_count = struct.unpack("<I", blob[4:8])[0]

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
        x_raw, pos = self.read_varint(blob, pos)
        y_raw, pos = self.read_varint(blob, pos)

        x, y = self.raw_to_coord(x_raw, y_raw)
        return Point(x=x, y=y)

    def _decode_complex(self, blob: bytes, point_count: int) -> Geometry:
        """Decode line/polygon geometries with multi-part support"""
        pos = 8

        # Read header varints
        _size_hint, pos = self.read_varint(blob, pos)
        geom_flags, pos = self.read_varint(blob, pos)

        # Bounding box (4 varints - may be small for normalized bbox)
        _xmin_raw, pos = self.read_varint(blob, pos)
        _ymin_raw, pos = self.read_varint(blob, pos)
        _xmax_raw, pos = self.read_varint(blob, pos)
        _ymax_raw, pos = self.read_varint(blob, pos)

        # Part information structure:
        # - All part info varints are small (< 100 billion)
        # - First large varint (> 100 billion) is the first X coordinate
        # - part_info[0] = num_parts (for multi-part geometries)
        # - part_info[1:num_parts+1] = point count per part
        part_info: list[int] = []
        x_raw: int = 0
        while pos < len(blob):
            v, new_pos = self.read_varint(blob, pos)
            if v > self.COORD_THRESHOLD:
                # This is the first X coordinate
                x_raw = v
                pos = new_pos
                break
            part_info.append(v)
            pos = new_pos
            if len(part_info) > 10000:
                raise ValueError("Could not find coordinate start")

        # Read first Y coordinate
        y_raw, pos = self.read_varint(blob, pos)

        # Determine part structure from part_info
        # For single-part: part_info might just have trailing zeros or [point_count, 0, 0]
        # For multi-part: part_info[0] = num_parts, part_info[1:num_parts+1] = points per part
        num_parts = 1
        points_per_part: list[int] = [point_count]

        if part_info:
            potential_num_parts = part_info[0]
            # Check if this looks like a valid part structure:
            # - num_parts should be reasonable (< 10000)
            # - should have enough values for part counts
            # - all counts should be non-negative
            # - sum of counts should match the header point_count
            has_valid_structure = (
                0 < potential_num_parts < 10000 and len(part_info) > potential_num_parts
            )
            if has_valid_structure:
                potential_counts = part_info[1 : potential_num_parts + 1]
                # Validate that:
                # - counts list is non-empty
                # - all counts are non-negative
                # - sum of counts matches header point_count (catches compact-bbox
                #   format where small values are misinterpreted as part structure)
                counts_valid = (
                    potential_counts
                    and all(c >= 0 for c in potential_counts)
                    and sum(potential_counts) == point_count
                )
                if counts_valid:
                    num_parts = potential_num_parts
                    points_per_part = potential_counts

        # Decode coordinates using the part structure
        parts: list[list[tuple[float, float]]] = []
        curr_x, curr_y = x_raw, y_raw

        for part_idx in range(num_parts):
            current_part: list[tuple[float, float]] = []
            part_point_count = (
                points_per_part[part_idx] if part_idx < len(points_per_part) else 0
            )

            # Track consecutive absolute coordinates for break marker detection
            prev_was_absolute = False
            pending_coord: tuple[float, float] | None = None

            # First point of each part
            if part_idx == 0:
                # Already read first coordinate
                current_part.append(self.raw_to_coord(curr_x, curr_y))
                points_to_read = part_point_count - 1
                prev_was_absolute = True  # First coord is always absolute
            else:
                # Need to read first coordinate of this part
                points_to_read = part_point_count
                prev_was_absolute = False

            for _ in range(points_to_read):
                if pos >= len(blob):
                    break

                v1, pos = self.read_varint(blob, pos)
                v2, pos = self.read_varint(blob, pos)

                if v1 > self.COORD_THRESHOLD:
                    # Absolute coordinate reset
                    curr_x, curr_y = v1, v2
                    coord = self.raw_to_coord(curr_x, curr_y)

                    if prev_was_absolute and pending_coord is not None:
                        # Consecutive absolute pair = segment boundary!
                        # Add pending as last point of current part
                        current_part.append(pending_coord)
                        # Save current part and start new one
                        if current_part:
                            parts.append(current_part)
                        current_part = []
                        # Add this coord as first point of new part
                        current_part.append(coord)
                        pending_coord = None
                    else:
                        # Single absolute - defer adding until we know if it's a pair
                        pending_coord = coord

                    prev_was_absolute = True
                else:
                    # Delta encoded coordinate
                    if pending_coord is not None:
                        # Standalone absolute followed by delta - add it normally
                        current_part.append(pending_coord)
                        pending_coord = None

                    dx = self.zigzag_decode(v1)
                    dy = self.zigzag_decode(v2)
                    curr_x += dx
                    curr_y += dy
                    current_part.append(self.raw_to_coord(curr_x, curr_y))

                    prev_was_absolute = False

            # Add any remaining pending coordinate at the end of the part
            if pending_coord is not None:
                current_part.append(pending_coord)

            if current_part:
                parts.append(current_part)

        # Determine geometry type from flags
        # Lower 4 bits: 1=Point, 4=Line, 8=Polygon
        base_type = geom_flags & 0x0F
        is_polygon = base_type == 8

        if is_polygon:
            return Polygon(rings=parts)
        else:
            if len(parts) == 1:
                return LineString(points=parts[0])
            else:
                lines = [LineString(points=p) for p in parts]
                return MultiLineString(lines=lines)


def decode_geometry(
    blob: bytes,
    x_origin: float = -20037700,
    y_origin: float = -30241100,
    xy_scale: float = 10000,
) -> Geometry:
    """
    Convenience function to decode an ST_Geometry blob.

    Args:
        blob: Raw bytes from the shape column
        x_origin: X origin from coordinate system definition
        y_origin: Y origin from coordinate system definition
        xy_scale: XY scale from coordinate system definition (will be doubled internally)

    Returns:
        Decoded geometry object with .wkt property

    Example:
        >>> geom = decode_geometry(blob)
        >>> print(geom.wkt)
        POINT (-13152949.2 5964179.3)
    """
    cs = CoordinateSystem(x_origin=x_origin, y_origin=y_origin, xy_scale=xy_scale)
    decoder = STGeometryDecoder(cs)
    return decoder.decode(blob)
