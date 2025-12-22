"""
Mobile Geodatabase Library

Read Esri Mobile Geodatabase (.geodatabase) files without proprietary dependencies.

This library provides a pure Python implementation for reading the ST_Geometry
blob format used in Esri Mobile Geodatabases.

Example:
    >>> from mobile_geodatabase import GeoDatabase
    >>>
    >>> gdb = GeoDatabase("file.geodatabase")
    >>> for table in gdb.tables:
    ...     print(table.name, table.geometry_type)
    ...
    >>> for feature in gdb.read_table("Rivers"):
    ...     print(feature.geometry.wkt)
    ...     print(feature.attributes)

CLI Example:
    $ mobile-geodatabase info file.geodatabase
    $ mobile-geodatabase convert file.geodatabase output.geojson
"""

__version__ = "0.1.0"

from .geometry import (
    Geometry,
    GeometryType,
    Point,
    LineString,
    Polygon,
    MultiPoint,
    MultiLineString,
    MultiPolygon,
    CoordinateSystem,
    BoundingBox,
)

from .decoder import (
    STGeometryDecoder,
    decode_geometry,
)

from .database import (
    GeoDatabase,
    Feature,
    TableInfo,
)

from .converters import (
    to_wkt,
    to_wkb,
    to_geojson_geometry,
    feature_to_geojson,
    features_to_geojson,
    write_geojson,
    write_geojsonl,
)

__all__ = [
    # Version
    "__version__",
    # Geometry types
    "Geometry",
    "GeometryType",
    "Point",
    "LineString",
    "Polygon",
    "MultiPoint",
    "MultiLineString",
    "MultiPolygon",
    "CoordinateSystem",
    "BoundingBox",
    # Decoder
    "STGeometryDecoder",
    "decode_geometry",
    # Database
    "GeoDatabase",
    "Feature",
    "TableInfo",
    # Converters
    "to_wkt",
    "to_wkb",
    "to_geojson_geometry",
    "feature_to_geojson",
    "features_to_geojson",
    "write_geojson",
    "write_geojsonl",
]
