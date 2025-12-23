"""
Output format converters for geometry data.

This module provides functions to convert geometries to various formats:
- WKT (Well-Known Text)
- WKB (Well-Known Binary)
- GeoJSON
- GeoPackage (using fiona/GDAL)
"""

import json
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import fiona
from pyproj import CRS, Transformer
from shapely.geometry import (
    LineString as ShapelyLineString,
)
from shapely.geometry import (
    MultiLineString as ShapelyMultiLineString,
)
from shapely.geometry import (
    MultiPoint as ShapelyMultiPoint,
)
from shapely.geometry import (
    MultiPolygon as ShapelyMultiPolygon,
)
from shapely.geometry import (
    Point as ShapelyPoint,
)
from shapely.geometry import (
    Polygon as ShapelyPolygon,
)
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from .database import Feature, GeoDatabase
from .geometry import (
    Geometry,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

# WKB constants
WKB_POINT = 1
WKB_LINESTRING = 2
WKB_POLYGON = 3
WKB_MULTIPOINT = 4
WKB_MULTILINESTRING = 5
WKB_MULTIPOLYGON = 6
WKB_Z_FLAG = 0x80000000

# Pre-built transformer for Web Mercator to WGS84 conversion (thread-safe, reusable)
_transformer_3857_to_4326 = Transformer.from_crs(
    "EPSG:3857", "EPSG:4326", always_xy=True
)


def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """
    Convert Web Mercator (EPSG:3857) coordinates to WGS84 (EPSG:4326).

    Uses pyproj for accurate coordinate transformation that handles edge cases
    such as poles and antimeridian crossings.

    Args:
        x: X coordinate in Web Mercator meters
        y: Y coordinate in Web Mercator meters

    Returns:
        Tuple of (longitude, latitude) in WGS84 degrees

    Example:
        >>> lon, lat = web_mercator_to_wgs84(-13410713.258, 5894992.591)
        >>> round(lon, 4), round(lat, 4)
        (-120.4705, 46.7108)
    """
    lon, lat = _transformer_3857_to_4326.transform(x, y)
    return (lon, lat)


def _transform_coord(coord: list[float], to_wgs84: bool) -> list[float]:
    """Transform a single coordinate, preserving Z if present."""
    if to_wgs84:
        lon, lat = web_mercator_to_wgs84(coord[0], coord[1])
        if len(coord) > 2:
            return [lon, lat, coord[2]]
        return [lon, lat]
    return coord


def _transform_ring(ring: list[list[float]], to_wgs84: bool) -> list[list[float]]:
    """Transform a ring of coordinates."""
    return [_transform_coord(coord, to_wgs84) for coord in ring]


def get_transformer(
    source_crs: str | int | CRS,
    target_crs: str | int | CRS,
) -> Transformer:
    """
    Create a pyproj Transformer for coordinate reprojection.

    Args:
        source_crs: Source coordinate reference system (EPSG code, WKT, or CRS object)
        target_crs: Target coordinate reference system (EPSG code, WKT, or CRS object)

    Returns:
        A pyproj Transformer instance configured for the specified transformation.

    Example:
        >>> transformer = get_transformer("EPSG:3857", "EPSG:4326")
        >>> lon, lat = transformer.transform(-13410713.258, 5894992.591)
    """
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)


def reproject_geometry(
    geom: Geometry,
    source_crs: str | int | CRS,
    target_crs: str | int | CRS,
) -> Geometry:
    """
    Reproject a geometry from one coordinate reference system to another.

    Uses pyproj for accurate coordinate transformation, supporting 8000+
    coordinate systems and proper datum transformations.

    Args:
        geom: Geometry object to reproject
        source_crs: Source CRS (EPSG code like "EPSG:3857", integer SRID, or CRS object)
        target_crs: Target CRS (EPSG code like "EPSG:4326", integer SRID, or CRS object)

    Returns:
        A new Geometry object with transformed coordinates

    Example:
        >>> from mobile_geodatabase.geometry import Point
        >>> pt = Point(x=-13410713.258, y=5894992.591)
        >>> reprojected = reproject_geometry(pt, "EPSG:3857", "EPSG:4326")
        >>> round(reprojected.x, 4), round(reprojected.y, 4)
        (-120.4705, 46.7108)
    """
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

    if isinstance(geom, Point):
        x, y = transformer.transform(geom.x, geom.y)
        return Point(x=x, y=y, z=geom.z)

    elif isinstance(geom, LineString):
        new_points: list[tuple[float, float]] = []
        for pt in geom.points:
            x, y = transformer.transform(pt[0], pt[1])
            new_points.append((x, y))
        return LineString(points=new_points, z_values=geom.z_values)

    elif isinstance(geom, Polygon):
        new_rings: list[list[tuple[float, float]]] = []
        for ring in geom.rings:
            new_ring: list[tuple[float, float]] = []
            for pt in ring:
                x, y = transformer.transform(pt[0], pt[1])
                new_ring.append((x, y))
            new_rings.append(new_ring)
        return Polygon(rings=new_rings, z_values=geom.z_values)

    elif isinstance(geom, MultiPoint):
        new_points_mp: list[Point] = []
        for pt in geom.points:
            x, y = transformer.transform(pt.x, pt.y)
            new_points_mp.append(Point(x=x, y=y, z=pt.z))
        return MultiPoint(points=new_points_mp)

    elif isinstance(geom, MultiLineString):
        new_lines: list[LineString] = []
        for line in geom.lines:
            new_line_points: list[tuple[float, float]] = []
            for pt in line.points:
                x, y = transformer.transform(pt[0], pt[1])
                new_line_points.append((x, y))
            new_lines.append(LineString(points=new_line_points, z_values=line.z_values))
        return MultiLineString(lines=new_lines)

    # MultiPolygon is the only remaining case
    assert isinstance(geom, MultiPolygon)
    new_polygons: list[Polygon] = []
    for poly in geom.polygons:
        new_poly_rings: list[list[tuple[float, float]]] = []
        for ring in poly.rings:
            new_poly_ring: list[tuple[float, float]] = []
            for pt in ring:
                x, y = transformer.transform(pt[0], pt[1])
                new_poly_ring.append((x, y))
            new_poly_rings.append(new_poly_ring)
        new_polygons.append(Polygon(rings=new_poly_rings, z_values=poly.z_values))
    return MultiPolygon(polygons=new_polygons)


def to_wkt(geom: Geometry) -> str:
    """
    Convert geometry to Well-Known Text (WKT) format.

    Args:
        geom: Geometry object

    Returns:
        WKT string representation

    Example:
        >>> pt = Point(x=-122.0, y=47.0)
        >>> to_wkt(pt)
        'POINT (-122.0 47.0)'
    """
    return geom.wkt


def to_wkb(geom: Geometry, big_endian: bool = False) -> bytes:
    """
    Convert geometry to Well-Known Binary (WKB) format.

    Args:
        geom: Geometry object
        big_endian: Use big-endian byte order (default: little-endian)

    Returns:
        WKB bytes

    Example:
        >>> pt = Point(x=-122.0, y=47.0)
        >>> wkb = to_wkb(pt)
    """
    byte_order = ">" if big_endian else "<"
    bo_flag = 0 if big_endian else 1

    def write_point_coords(p: Point) -> bytes:
        if p.has_z:
            return struct.pack(f"{byte_order}ddd", p.x, p.y, p.z)
        return struct.pack(f"{byte_order}dd", p.x, p.y)

    if isinstance(geom, Point):
        wkb_type = WKB_POINT | (WKB_Z_FLAG if geom.has_z else 0)
        return struct.pack(f"{byte_order}bI", bo_flag, wkb_type) + write_point_coords(
            geom
        )

    elif isinstance(geom, LineString):
        wkb_type = WKB_LINESTRING | (WKB_Z_FLAG if geom.has_z else 0)
        data = struct.pack(f"{byte_order}bII", bo_flag, wkb_type, len(geom.points))
        for i, pt in enumerate(geom.points):
            if geom.has_z and geom.z_values:
                data += struct.pack(f"{byte_order}ddd", pt[0], pt[1], geom.z_values[i])
            else:
                data += struct.pack(f"{byte_order}dd", pt[0], pt[1])
        return data

    elif isinstance(geom, Polygon):
        wkb_type = WKB_POLYGON | (WKB_Z_FLAG if geom.has_z else 0)
        data = struct.pack(f"{byte_order}bII", bo_flag, wkb_type, len(geom.rings))
        for i, ring in enumerate(geom.rings):
            data += struct.pack(f"{byte_order}I", len(ring))
            for j, pt in enumerate(ring):
                if geom.has_z and geom.z_values and i < len(geom.z_values):
                    data += struct.pack(
                        f"{byte_order}ddd", pt[0], pt[1], geom.z_values[i][j]
                    )
                else:
                    data += struct.pack(f"{byte_order}dd", pt[0], pt[1])
        return data

    elif isinstance(geom, MultiPoint):
        wkb_type = WKB_MULTIPOINT | (WKB_Z_FLAG if geom.has_z else 0)
        data = struct.pack(f"{byte_order}bII", bo_flag, wkb_type, len(geom.points))
        for pt in geom.points:
            data += to_wkb(pt, big_endian)
        return data

    elif isinstance(geom, MultiLineString):
        wkb_type = WKB_MULTILINESTRING | (WKB_Z_FLAG if geom.has_z else 0)
        data = struct.pack(f"{byte_order}bII", bo_flag, wkb_type, len(geom.lines))
        for line in geom.lines:
            data += to_wkb(line, big_endian)
        return data

    # MultiPolygon is the only remaining case
    assert isinstance(geom, MultiPolygon)
    wkb_type = WKB_MULTIPOLYGON | (WKB_Z_FLAG if geom.has_z else 0)
    data = struct.pack(f"{byte_order}bII", bo_flag, wkb_type, len(geom.polygons))
    for poly in geom.polygons:
        data += to_wkb(poly, big_endian)
    return data


def to_geojson_geometry(geom: Geometry, to_wgs84: bool = True) -> dict[str, Any]:
    """
    Convert geometry to GeoJSON geometry object.

    By default, coordinates are transformed from Web Mercator (EPSG:3857) to
    WGS84 (EPSG:4326) as required by GeoJSON RFC 7946.

    Args:
        geom: Geometry object
        to_wgs84: If True (default), transform coordinates from Web Mercator
            to WGS84. Set to False to keep original coordinates.

    Returns:
        GeoJSON geometry dictionary

    Example:
        >>> pt = Point(x=-122.0, y=47.0)
        >>> to_geojson_geometry(pt, to_wgs84=False)
        {'type': 'Point', 'coordinates': [-122.0, 47.0]}

        >>> pt = Point(x=-13410713.258, y=5894992.591)
        >>> geojson = to_geojson_geometry(pt, to_wgs84=True)
        >>> round(geojson['coordinates'][0], 4)
        -120.4705
    """
    if isinstance(geom, Point):
        coords: list[float] = [geom.x, geom.y]
        if geom.z is not None:
            coords.append(geom.z)
        return {"type": "Point", "coordinates": _transform_coord(coords, to_wgs84)}

    elif isinstance(geom, LineString):
        line_coords: list[list[float]] = []
        for i, pt in enumerate(geom.points):
            coord: list[float] = [pt[0], pt[1]]
            if geom.z_values is not None and i < len(geom.z_values):
                coord.append(geom.z_values[i])
            line_coords.append(coord)
        return {
            "type": "LineString",
            "coordinates": [_transform_coord(c, to_wgs84) for c in line_coords],
        }

    elif isinstance(geom, Polygon):
        rings: list[list[list[float]]] = []
        for i, ring in enumerate(geom.rings):
            ring_coords: list[list[float]] = []
            for j, pt in enumerate(ring):
                coord: list[float] = [pt[0], pt[1]]
                if geom.has_z and geom.z_values and i < len(geom.z_values):
                    coord.append(geom.z_values[i][j])
                ring_coords.append(coord)
            rings.append(_transform_ring(ring_coords, to_wgs84))
        return {"type": "Polygon", "coordinates": rings}

    elif isinstance(geom, MultiPoint):
        mp_coords: list[list[float]] = []
        for pt in geom.points:
            coord: list[float] = [pt.x, pt.y]
            if pt.z is not None:
                coord.append(pt.z)
            mp_coords.append(_transform_coord(coord, to_wgs84))
        return {"type": "MultiPoint", "coordinates": mp_coords}

    elif isinstance(geom, MultiLineString):
        lines: list[list[list[float]]] = []
        for line in geom.lines:
            mls_line_coords: list[list[float]] = []
            for i, pt in enumerate(line.points):
                coord: list[float] = [pt[0], pt[1]]
                if line.has_z and line.z_values:
                    coord.append(line.z_values[i])
                mls_line_coords.append(coord)
            lines.append([_transform_coord(c, to_wgs84) for c in mls_line_coords])
        return {"type": "MultiLineString", "coordinates": lines}

    # MultiPolygon is the only remaining case
    polys: list[list[list[list[float]]]] = []
    for poly in geom.polygons:
        mpoly_rings: list[list[list[float]]] = []
        for i, ring in enumerate(poly.rings):
            mpoly_ring_coords: list[list[float]] = []
            for j, pt in enumerate(ring):
                coord: list[float] = [pt[0], pt[1]]
                if poly.has_z and poly.z_values and i < len(poly.z_values):
                    coord.append(poly.z_values[i][j])
                mpoly_ring_coords.append(coord)
            mpoly_rings.append(_transform_ring(mpoly_ring_coords, to_wgs84))
        polys.append(mpoly_rings)
    return {"type": "MultiPolygon", "coordinates": polys}


def feature_to_geojson(feature: Feature, to_wgs84: bool = True) -> dict[str, Any]:
    """
    Convert a Feature to a GeoJSON Feature object.

    By default, coordinates are transformed from Web Mercator (EPSG:3857) to
    WGS84 (EPSG:4326) as required by GeoJSON RFC 7946.

    Args:
        feature: Feature object
        to_wgs84: If True (default), transform coordinates from Web Mercator
            to WGS84. Set to False to keep original coordinates.

    Returns:
        GeoJSON Feature dictionary
    """
    geojson: dict[str, Any] = {
        "type": "Feature",
        "properties": feature.attributes,
        "geometry": None,
    }

    if feature.geometry:
        geojson["geometry"] = to_geojson_geometry(feature.geometry, to_wgs84=to_wgs84)

    if feature.fid is not None:
        geojson["id"] = feature.fid

    return geojson


def features_to_geojson(
    features: Iterator[Feature], to_wgs84: bool = True
) -> dict[str, Any]:
    """
    Convert an iterable of Features to a GeoJSON FeatureCollection.

    By default, coordinates are transformed from Web Mercator (EPSG:3857) to
    WGS84 (EPSG:4326) as required by GeoJSON RFC 7946. When coordinates are
    in WGS84, no CRS member is included (per RFC 7946 recommendation).

    Args:
        features: Iterable of Feature objects
        to_wgs84: If True (default), transform coordinates from Web Mercator
            to WGS84. Set to False to keep original coordinates.

    Returns:
        GeoJSON FeatureCollection dictionary
    """
    feature_list = [feature_to_geojson(f, to_wgs84=to_wgs84) for f in features]

    return {"type": "FeatureCollection", "features": feature_list}


def write_geojson(
    gdb: GeoDatabase,
    table_name: str,
    output_path: str,
    indent: int | None = 2,
    columns: list[str] | None = None,
    where: str | None = None,
    limit: int | None = None,
    to_wgs84: bool = True,
) -> int:
    """
    Export a geodatabase table to a GeoJSON file.

    By default, coordinates are transformed from Web Mercator (EPSG:3857) to
    WGS84 (EPSG:4326) as required by GeoJSON RFC 7946.

    Args:
        gdb: GeoDatabase instance
        table_name: Name of table to export
        output_path: Path to output GeoJSON file
        indent: JSON indentation (None for compact)
        columns: List of attribute columns to include (None for all)
        where: Optional SQL WHERE clause (without 'WHERE' keyword)
        limit: Maximum number of features to return
        to_wgs84: If True (default), transform coordinates from Web Mercator
            to WGS84. Set to False to keep original coordinates.

    Returns:
        Number of features written

    Example:
        >>> gdb = GeoDatabase("file.geodatabase")
        >>> write_geojson(gdb, "Rivers", "rivers.geojson")
    """
    features = list(
        gdb.read_table(table_name, columns=columns, where=where, limit=limit)
    )
    geojson = features_to_geojson(iter(features), to_wgs84=to_wgs84)

    with Path(output_path).open("w") as f:
        json.dump(geojson, f, indent=indent)

    return len(features)


def write_geojsonl(
    gdb: GeoDatabase,
    table_name: str,
    output_path: str,
    columns: list[str] | None = None,
    where: str | None = None,
    limit: int | None = None,
    to_wgs84: bool = True,
) -> int:
    """
    Export a geodatabase table to a GeoJSON Lines (newline-delimited) file.

    This format is better for large datasets as it can be processed line by line.
    By default, coordinates are transformed from Web Mercator (EPSG:3857) to
    WGS84 (EPSG:4326) as required by GeoJSON RFC 7946.

    Args:
        gdb: GeoDatabase instance
        table_name: Name of table to export
        output_path: Path to output .geojsonl file
        columns: List of attribute columns to include (None for all)
        where: Optional SQL WHERE clause (without 'WHERE' keyword)
        limit: Maximum number of features to return
        to_wgs84: If True (default), transform coordinates from Web Mercator
            to WGS84. Set to False to keep original coordinates.

    Returns:
        Number of features written
    """
    count = 0
    with Path(output_path).open("w") as f:
        for feature in gdb.read_table(
            table_name, columns=columns, where=where, limit=limit
        ):
            geojson = feature_to_geojson(feature, to_wgs84=to_wgs84)
            f.write(json.dumps(geojson) + "\n")
            count += 1
    return count


def _point_to_shapely(pt: Point) -> ShapelyPoint:
    """Convert a Point to a Shapely Point."""
    if pt.has_z and pt.z is not None:
        return ShapelyPoint(pt.x, pt.y, pt.z)
    return ShapelyPoint(pt.x, pt.y)


def _linestring_to_shapely(line: LineString) -> ShapelyLineString:
    """Convert a LineString to a Shapely LineString."""
    if line.has_z and line.z_values:
        coords: list[tuple[float, float] | tuple[float, float, float]] = [
            (pt[0], pt[1], z) for pt, z in zip(line.points, line.z_values, strict=False)
        ]
    else:
        coords = list(line.points)
    return ShapelyLineString(coords)


def _polygon_to_shapely(poly: Polygon) -> ShapelyPolygon:
    """Convert a Polygon to a Shapely Polygon."""
    if poly.has_z and poly.z_values:
        shell: list[tuple[float, float] | tuple[float, float, float]] = [
            (pt[0], pt[1], z)
            for pt, z in zip(poly.rings[0], poly.z_values[0], strict=False)
        ]
        holes: list[list[tuple[float, float] | tuple[float, float, float]]] = [
            [
                (pt[0], pt[1], z)
                for pt, z in zip(ring, poly.z_values[i + 1], strict=False)
            ]
            for i, ring in enumerate(poly.rings[1:])
            if i + 1 < len(poly.z_values)
        ]
    else:
        shell = list(poly.rings[0])
        holes = [list(ring) for ring in poly.rings[1:]]
    return ShapelyPolygon(shell, holes if holes else None)


def geometry_to_shapely(geom: Geometry) -> BaseGeometry:
    """
    Convert a library geometry to a Shapely geometry.

    Args:
        geom: Geometry object from this library

    Returns:
        Corresponding Shapely geometry object
    """
    if isinstance(geom, Point):
        return _point_to_shapely(geom)

    if isinstance(geom, LineString):
        return _linestring_to_shapely(geom)

    if isinstance(geom, Polygon):
        return _polygon_to_shapely(geom)

    if isinstance(geom, MultiPoint):
        shapely_points = [_point_to_shapely(pt) for pt in geom.points]
        return ShapelyMultiPoint(shapely_points)

    if isinstance(geom, MultiLineString):
        shapely_lines = [_linestring_to_shapely(line) for line in geom.lines]
        return ShapelyMultiLineString(shapely_lines)

    # MultiPolygon is the only remaining case
    assert isinstance(geom, MultiPolygon)
    shapely_polys = [_polygon_to_shapely(poly) for poly in geom.polygons]
    return ShapelyMultiPolygon(shapely_polys)


def _geometry_type_to_fiona(geom: Geometry) -> str:
    """Map geometry type to fiona schema geometry type name."""
    type_map: dict[type[Geometry], str] = {
        Point: "Point",
        LineString: "LineString",
        Polygon: "Polygon",
        MultiPoint: "MultiPoint",
        MultiLineString: "MultiLineString",
        MultiPolygon: "MultiPolygon",
    }
    geom_type = type_map.get(type(geom), "Unknown")
    if geom.has_z:
        return f"3D {geom_type}"
    return geom_type


def _get_fiona_property_type(value: object) -> str:
    """Determine fiona property type from Python value."""
    if value is None:
        return "str"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def write_geopackage(
    gdb: GeoDatabase,
    table_name: str,
    output_path: str,
    columns: list[str] | None = None,
    where: str | None = None,
    limit: int | None = None,
) -> int:
    """
    Export a geodatabase table to a GeoPackage file.

    Uses fiona/GDAL to create a properly formatted GeoPackage (.gpkg) file
    with correct metadata tables and geometry encoding. GeoPackage is a
    SQLite-based format that preserves projection information and is
    widely supported by GIS software.

    Args:
        gdb: GeoDatabase instance
        table_name: Name of table to export
        output_path: Path to output GeoPackage file
        columns: List of attribute columns to include (None for all)
        where: Optional SQL WHERE clause (without 'WHERE' keyword)
        limit: Maximum number of features to return

    Returns:
        Number of features written

    Example:
        >>> gdb = GeoDatabase("file.geodatabase")
        >>> write_geopackage(gdb, "Rivers", "rivers.gpkg")
    """
    table = gdb.get_table(table_name)
    if table is None:
        raise ValueError(f"Table not found: {table_name}")

    # Get SRID, default to Web Mercator
    # Map Esri's internal codes to standard EPSG codes
    esri_to_epsg = {
        102100: 3857,  # Web Mercator
        102113: 3857,  # Web Mercator (older Esri code)
    }
    srid = 3857
    if table.coord_system and table.coord_system.srid:
        srid = esri_to_epsg.get(table.coord_system.srid, table.coord_system.srid)

    # Remove existing file if present
    output_file = Path(output_path)
    if output_file.exists():
        output_file.unlink()

    # Read features to determine schema
    features = list(
        gdb.read_table(table_name, columns=columns, where=where, limit=limit)
    )

    if not features:
        return 0

    # Determine geometry type from first feature with geometry
    # Use Multi* types to handle mixed single/multi geometries
    geometry_type = "Unknown"
    for feature in features:
        if feature.geometry:
            base_type = _geometry_type_to_fiona(feature.geometry)
            # Promote to Multi* for compatibility (single geoms will be promoted when writing)
            promote_map = {
                "LineString": "MultiLineString",
                "Polygon": "MultiPolygon",
                "Point": "MultiPoint",
                "3D LineString": "3D MultiLineString",
                "3D Polygon": "3D MultiPolygon",
                "3D Point": "3D MultiPoint",
            }
            geometry_type = promote_map.get(base_type, base_type)
            break

    # Determine attribute schema from first feature
    properties_schema: dict[str, str] = {}
    if features[0].attributes:
        for key, value in features[0].attributes.items():
            properties_schema[key] = _get_fiona_property_type(value)

    # Build fiona schema
    schema: dict[str, Any] = {
        "geometry": geometry_type,
        "properties": properties_schema,
    }

    # Use a sanitized layer name
    layer_name = table_name.replace(" ", "_").replace("-", "_")

    # Write features using fiona
    # Use EPSG string format for CRS (fiona accepts this directly)
    crs_string = f"EPSG:{srid}"
    count = 0
    with fiona.open(  # pyright: ignore[reportUnknownMemberType]
        output_path,
        "w",
        driver="GPKG",
        crs=crs_string,
        schema=schema,
        layer=layer_name,
    ) as dst:  # pyright: ignore[reportUnknownVariableType]
        # Import shapely types for geometry promotion
        from shapely.geometry import LineString as ShapelyLineString
        from shapely.geometry import MultiLineString as ShapelyMultiLineString
        from shapely.geometry import MultiPoint as ShapelyMultiPoint
        from shapely.geometry import MultiPolygon as ShapelyMultiPolygon
        from shapely.geometry import Point as ShapelyPoint
        from shapely.geometry import Polygon as ShapelyPolygon

        for feature in features:
            # Build feature record
            geom_dict: dict[str, Any] | None = None
            if feature.geometry:
                shapely_geom = geometry_to_shapely(feature.geometry)
                # Promote single geometries to Multi* for schema compatibility
                if isinstance(shapely_geom, ShapelyLineString):
                    shapely_geom = ShapelyMultiLineString([shapely_geom])
                elif isinstance(shapely_geom, ShapelyPolygon):
                    shapely_geom = ShapelyMultiPolygon([shapely_geom])
                elif isinstance(shapely_geom, ShapelyPoint):
                    shapely_geom = ShapelyMultiPoint([shapely_geom])
                geom_dict = mapping(shapely_geom)

            record: dict[str, Any] = {
                "geometry": geom_dict,
                "properties": feature.attributes,
            }
            dst.write(record)  # pyright: ignore[reportUnknownMemberType]
            count += 1

    return count
