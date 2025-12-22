"""
Output format converters for geometry data.

This module provides functions to convert geometries to various formats:
- WKT (Well-Known Text)
- WKB (Well-Known Binary)
- GeoJSON
"""

import json
import struct
from collections.abc import Iterator
from pathlib import Path
from typing import Any

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


def to_geojson_geometry(geom: Geometry) -> dict[str, Any]:
    """
    Convert geometry to GeoJSON geometry object.

    Args:
        geom: Geometry object

    Returns:
        GeoJSON geometry dictionary

    Example:
        >>> pt = Point(x=-122.0, y=47.0)
        >>> to_geojson_geometry(pt)
        {'type': 'Point', 'coordinates': [-122.0, 47.0]}
    """
    if isinstance(geom, Point):
        coords: list[float] = [geom.x, geom.y]
        if geom.z is not None:
            coords.append(geom.z)
        return {"type": "Point", "coordinates": coords}

    elif isinstance(geom, LineString):
        line_coords: list[list[float]] = []
        for i, pt in enumerate(geom.points):
            coord: list[float] = [pt[0], pt[1]]
            if geom.z_values is not None and i < len(geom.z_values):
                coord.append(geom.z_values[i])
            line_coords.append(coord)
        return {"type": "LineString", "coordinates": line_coords}

    elif isinstance(geom, Polygon):
        rings: list[list[list[float]]] = []
        for i, ring in enumerate(geom.rings):
            ring_coords: list[list[float]] = []
            for j, pt in enumerate(ring):
                coord: list[float] = [pt[0], pt[1]]
                if geom.has_z and geom.z_values and i < len(geom.z_values):
                    coord.append(geom.z_values[i][j])
                ring_coords.append(coord)
            rings.append(ring_coords)
        return {"type": "Polygon", "coordinates": rings}

    elif isinstance(geom, MultiPoint):
        mp_coords: list[list[float]] = []
        for pt in geom.points:
            coord: list[float] = [pt.x, pt.y]
            if pt.z is not None:
                coord.append(pt.z)
            mp_coords.append(coord)
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
            lines.append(mls_line_coords)
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
            mpoly_rings.append(mpoly_ring_coords)
        polys.append(mpoly_rings)
    return {"type": "MultiPolygon", "coordinates": polys}


def feature_to_geojson(feature: Feature) -> dict[str, Any]:
    """
    Convert a Feature to a GeoJSON Feature object.

    Args:
        feature: Feature object

    Returns:
        GeoJSON Feature dictionary
    """
    geojson: dict[str, Any] = {
        "type": "Feature",
        "properties": feature.attributes,
        "geometry": None,
    }

    if feature.geometry:
        geojson["geometry"] = to_geojson_geometry(feature.geometry)

    if feature.fid is not None:
        geojson["id"] = feature.fid

    return geojson


def features_to_geojson(
    features: Iterator[Feature], crs: str | None = None
) -> dict[str, Any]:
    """
    Convert an iterable of Features to a GeoJSON FeatureCollection.

    Args:
        features: Iterable of Feature objects
        crs: Optional CRS identifier (e.g., "EPSG:3857")

    Returns:
        GeoJSON FeatureCollection dictionary
    """
    feature_list = [feature_to_geojson(f) for f in features]

    geojson: dict[str, Any] = {"type": "FeatureCollection", "features": feature_list}

    if crs:
        geojson["crs"] = {"type": "name", "properties": {"name": crs}}

    return geojson


def write_geojson(
    gdb: GeoDatabase,
    table_name: str,
    output_path: str,
    indent: int | None = 2,
    columns: list[str] | None = None,
    where: str | None = None,
    limit: int | None = None,
) -> int:
    """
    Export a geodatabase table to a GeoJSON file.

    Args:
        gdb: GeoDatabase instance
        table_name: Name of table to export
        output_path: Path to output GeoJSON file
        indent: JSON indentation (None for compact)
        columns: List of attribute columns to include (None for all)
        where: Optional SQL WHERE clause (without 'WHERE' keyword)
        limit: Maximum number of features to return

    Returns:
        Number of features written

    Example:
        >>> gdb = GeoDatabase("file.geodatabase")
        >>> write_geojson(gdb, "Rivers", "rivers.geojson")
    """
    table = gdb.get_table(table_name)
    crs = None
    if table and table.coord_system and table.coord_system.srid:
        crs = f"EPSG:{table.coord_system.srid}"

    features = list(
        gdb.read_table(table_name, columns=columns, where=where, limit=limit)
    )
    geojson = features_to_geojson(iter(features), crs=crs)

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
) -> int:
    """
    Export a geodatabase table to a GeoJSON Lines (newline-delimited) file.

    This format is better for large datasets as it can be processed line by line.

    Args:
        gdb: GeoDatabase instance
        table_name: Name of table to export
        output_path: Path to output .geojsonl file
        columns: List of attribute columns to include (None for all)
        where: Optional SQL WHERE clause (without 'WHERE' keyword)
        limit: Maximum number of features to return

    Returns:
        Number of features written
    """
    count = 0
    with Path(output_path).open("w") as f:
        for feature in gdb.read_table(
            table_name, columns=columns, where=where, limit=limit
        ):
            geojson = feature_to_geojson(feature)
            f.write(json.dumps(geojson) + "\n")
            count += 1
    return count
