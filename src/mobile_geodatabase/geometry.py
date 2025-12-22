"""
Geometry classes for representing spatial data.

These classes provide simple containers for geometry data with WKT output.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Union
from enum import IntEnum


class GeometryType(IntEnum):
    """Esri geometry type codes from st_geometry_columns.geometry_type"""
    POINT = 1
    LINESTRING = 2
    POLYGON = 3
    MULTIPOINT = 4
    MULTILINESTRING = 5
    MULTIPOLYGON = 6
    # Z variants add 1000
    POINTZ = 1001
    LINESTRINGZ = 1002
    POLYGONZ = 1003
    MULTIPOINTZ = 1004
    MULTILINESTRINGZ = 1005
    MULTIPOLYGONZ = 1006


@dataclass
class CoordinateSystem:
    """
    Coordinate system parameters from geodatabase XML definition.

    Attributes:
        x_origin: X origin for coordinate transformation
        y_origin: Y origin for coordinate transformation
        xy_scale: XY scale from metadata (actual encoding uses 2x this value)
        z_origin: Z origin for Z coordinate transformation
        z_scale: Z scale factor
        srid: Spatial reference ID (e.g., 3857 for Web Mercator)
        wkt: Well-known text representation of the coordinate system
    """
    x_origin: float = -20037700
    y_origin: float = -30241100
    xy_scale: float = 10000
    z_origin: float = -100000
    z_scale: float = 10000
    srid: Optional[int] = None
    wkt: Optional[str] = None

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

    def __iter__(self):
        return iter((self.xmin, self.ymin, self.xmax, self.ymax))


@dataclass
class Point:
    """A 2D or 3D point"""
    x: float
    y: float
    z: Optional[float] = None

    @property
    def has_z(self) -> bool:
        return self.z is not None

    @property
    def wkt(self) -> str:
        if self.z is not None:
            return f"POINT Z ({self.x} {self.y} {self.z})"
        return f"POINT ({self.x} {self.y})"

    @property
    def coordinates(self) -> Tuple:
        if self.z is not None:
            return (self.x, self.y, self.z)
        return (self.x, self.y)

    @property
    def bounds(self) -> BoundingBox:
        return BoundingBox(self.x, self.y, self.x, self.y)


@dataclass
class LineString:
    """A line string (polyline)"""
    points: List[Tuple[float, float]]
    z_values: Optional[List[float]] = None

    @property
    def has_z(self) -> bool:
        return self.z_values is not None and len(self.z_values) > 0

    @property
    def wkt(self) -> str:
        if self.z_values:
            coords = ", ".join(f"{p[0]} {p[1]} {z}"
                              for p, z in zip(self.points, self.z_values))
            return f"LINESTRING Z ({coords})"
        coords = ", ".join(f"{p[0]} {p[1]}" for p in self.points)
        return f"LINESTRING ({coords})"

    @property
    def coordinates(self) -> List[Tuple]:
        if self.z_values:
            return [(p[0], p[1], z) for p, z in zip(self.points, self.z_values)]
        return list(self.points)

    @property
    def bounds(self) -> BoundingBox:
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return BoundingBox(min(xs), min(ys), max(xs), max(ys))

    def __len__(self) -> int:
        return len(self.points)


@dataclass
class Polygon:
    """A polygon with optional holes"""
    rings: List[List[Tuple[float, float]]]
    z_values: Optional[List[List[float]]] = None

    @property
    def exterior(self) -> List[Tuple[float, float]]:
        """The exterior ring (first ring)"""
        return self.rings[0] if self.rings else []

    @property
    def interiors(self) -> List[List[Tuple[float, float]]]:
        """Interior rings (holes)"""
        return self.rings[1:] if len(self.rings) > 1 else []

    @property
    def has_z(self) -> bool:
        return self.z_values is not None and len(self.z_values) > 0

    @property
    def wkt(self) -> str:
        ring_strs = []
        for i, ring in enumerate(self.rings):
            if self.z_values and i < len(self.z_values):
                coords = ", ".join(f"{p[0]} {p[1]} {z}"
                                  for p, z in zip(ring, self.z_values[i]))
            else:
                coords = ", ".join(f"{p[0]} {p[1]}" for p in ring)
            ring_strs.append(f"({coords})")

        if self.has_z:
            return f"POLYGON Z ({', '.join(ring_strs)})"
        return f"POLYGON ({', '.join(ring_strs)})"

    @property
    def coordinates(self) -> List[List[Tuple]]:
        if self.z_values:
            result = []
            for i, ring in enumerate(self.rings):
                if i < len(self.z_values):
                    result.append([(p[0], p[1], z) for p, z in zip(ring, self.z_values[i])])
                else:
                    result.append(list(ring))
            return result
        return [list(ring) for ring in self.rings]

    @property
    def bounds(self) -> BoundingBox:
        all_points = [p for ring in self.rings for p in ring]
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        return BoundingBox(min(xs), min(ys), max(xs), max(ys))


@dataclass
class MultiPoint:
    """Multiple points"""
    points: List[Point]

    @property
    def has_z(self) -> bool:
        return any(p.has_z for p in self.points)

    @property
    def wkt(self) -> str:
        if self.has_z:
            coords = ", ".join(f"({p.x} {p.y} {p.z or 0})" for p in self.points)
            return f"MULTIPOINT Z ({coords})"
        coords = ", ".join(f"({p.x} {p.y})" for p in self.points)
        return f"MULTIPOINT ({coords})"

    @property
    def coordinates(self) -> List[Tuple]:
        return [p.coordinates for p in self.points]

    @property
    def bounds(self) -> BoundingBox:
        xs = [p.x for p in self.points]
        ys = [p.y for p in self.points]
        return BoundingBox(min(xs), min(ys), max(xs), max(ys))

    def __len__(self) -> int:
        return len(self.points)

    def __iter__(self):
        return iter(self.points)


@dataclass
class MultiLineString:
    """Multiple line strings"""
    lines: List[LineString]

    @property
    def has_z(self) -> bool:
        return any(l.has_z for l in self.lines)

    @property
    def wkt(self) -> str:
        has_z = self.has_z
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

    @property
    def coordinates(self) -> List[List[Tuple]]:
        return [line.coordinates for line in self.lines]

    @property
    def bounds(self) -> BoundingBox:
        all_bounds = [line.bounds for line in self.lines]
        return BoundingBox(
            min(b.xmin for b in all_bounds),
            min(b.ymin for b in all_bounds),
            max(b.xmax for b in all_bounds),
            max(b.ymax for b in all_bounds)
        )

    def __len__(self) -> int:
        return len(self.lines)

    def __iter__(self):
        return iter(self.lines)


@dataclass
class MultiPolygon:
    """Multiple polygons"""
    polygons: List[Polygon]

    @property
    def has_z(self) -> bool:
        return any(p.has_z for p in self.polygons)

    @property
    def wkt(self) -> str:
        has_z = self.has_z
        poly_strs = []
        for poly in self.polygons:
            ring_strs = []
            for i, ring in enumerate(poly.rings):
                if has_z and poly.z_values and i < len(poly.z_values):
                    coords = ", ".join(f"{p[0]} {p[1]} {z}"
                                      for p, z in zip(ring, poly.z_values[i]))
                else:
                    coords = ", ".join(f"{p[0]} {p[1]}" for p in ring)
                ring_strs.append(f"({coords})")
            poly_strs.append(f"({', '.join(ring_strs)})")

        if has_z:
            return f"MULTIPOLYGON Z ({', '.join(poly_strs)})"
        return f"MULTIPOLYGON ({', '.join(poly_strs)})"

    @property
    def coordinates(self) -> List[List[List[Tuple]]]:
        return [poly.coordinates for poly in self.polygons]

    @property
    def bounds(self) -> BoundingBox:
        all_bounds = [poly.bounds for poly in self.polygons]
        return BoundingBox(
            min(b.xmin for b in all_bounds),
            min(b.ymin for b in all_bounds),
            max(b.xmax for b in all_bounds),
            max(b.ymax for b in all_bounds)
        )

    def __len__(self) -> int:
        return len(self.polygons)

    def __iter__(self):
        return iter(self.polygons)


# Type alias for any geometry
Geometry = Union[Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon]


def geometry_type_name(geom: Geometry) -> str:
    """Get the geometry type name"""
    return type(geom).__name__
