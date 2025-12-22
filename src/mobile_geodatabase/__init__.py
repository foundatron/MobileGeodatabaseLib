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

from .converters import (
    feature_to_geojson,
    features_to_geojson,
    geometry_to_shapely,
    to_geojson_geometry,
    to_wkb,
    to_wkt,
    web_mercator_to_wgs84,
    write_geojson,
    write_geojsonl,
    write_geopackage,
)
from .database import (
    Feature,
    GeoDatabase,
    TableInfo,
)
from .decoder import (
    STGeometryDecoder,
    decode_geometry,
)
from .geometry import (
    BoundingBox,
    CoordinateSystem,
    Geometry,
    GeometryType,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)

__all__ = [
    "BoundingBox",
    "CoordinateSystem",
    "Feature",
    # Database
    "GeoDatabase",
    # Geometry types
    "Geometry",
    "GeometryType",
    "LineString",
    "MultiLineString",
    "MultiPoint",
    "MultiPolygon",
    "Point",
    "Polygon",
    # Decoder
    "STGeometryDecoder",
    "TableInfo",
    # Version
    "__version__",
    "decode_geometry",
    "feature_to_geojson",
    "features_to_geojson",
    "geometry_to_shapely",
    "to_geojson_geometry",
    "to_wkb",
    # Converters
    "to_wkt",
    "web_mercator_to_wgs84",
    "write_geojson",
    "write_geojsonl",
    "write_geopackage",
]
