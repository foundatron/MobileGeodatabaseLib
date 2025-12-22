# Mobile Geodatabase Library

!!!! THIS IS SUPER EXPERIMENTAL / Laughably Bad !!!!

A pure Python library for reading Esri Mobile Geodatabase (.geodatabase) files.

## Features

- Read .geodatabase files (SQLite-based Esri Mobile Geodatabases)
- Decode ST_Geometry blobs to standard geometry objects
- Export to GeoJSON, WKT, and WKB formats
- Command-line interface for quick data inspection and conversion
- No proprietary dependencies

## Installation

```bash
pip install mobile-geodatabase
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install mobile-geodatabase
```

Or install from source:

```bash
git clone https://github.com/foundatron/MobileGeodatabaseLib.git
cd MobileGeodatabaseLib
pip install -e .  # or: uv pip install -e .
```

## Quick Start

### Python API

```python
from mobile_geodatabase import GeoDatabase

# Open a geodatabase
gdb = GeoDatabase("file.geodatabase")

# List tables
for table in gdb.tables:
    print(f"{table.name}: {table.geometry_type} ({table.row_count} rows)")

# Read features
for feature in gdb.read_table("Rivers"):
    print(feature.geometry.wkt)
    print(feature.attributes)

# Export to GeoJSON
from mobile_geodatabase import write_geojson
write_geojson(gdb, "Rivers", "rivers.geojson")

# Close when done
gdb.close()

# Or use context manager
with GeoDatabase("file.geodatabase") as gdb:
    features = gdb.read_all("Cities", limit=100)
```

### Command Line

```bash
# Show geodatabase info
mobile-geodatabase info file.geodatabase

# Convert to GeoJSON
mobile-geodatabase convert file.geodatabase output.geojson

# Convert specific table
mobile-geodatabase convert file.geodatabase rivers.geojson --table Rivers

# Dump features for inspection
mobile-geodatabase dump file.geodatabase Rivers --limit 5

# List tables (script-friendly)
mobile-geodatabase list-tables file.geodatabase
```

## Supported Geometry Types

- Point / PointZ
- LineString / LineStringZ
- Polygon / PolygonZ
- MultiPoint / MultiPointZ
- MultiLineString / MultiLineStringZ
- MultiPolygon / MultiPolygonZ

## API Reference

### GeoDatabase

The main class for reading geodatabase files.

```python
from mobile_geodatabase import GeoDatabase

gdb = GeoDatabase("path/to/file.geodatabase")

# Properties
gdb.path          # Path to the geodatabase file
gdb.tables        # List of TableInfo objects
gdb.table_names   # List of table names

# Methods
gdb.get_table(name)                    # Get TableInfo by name
gdb.read_table(name, limit=None, where=None)  # Iterator of Features
gdb.read_all(name, **kwargs)           # List of Features
gdb.execute(sql)                       # Execute raw SQL
gdb.close()                            # Close connection
```

### Feature

Represents a row from a geodatabase table.

```python
feature.geometry    # Geometry object (Point, LineString, etc.)
feature.attributes  # Dict of attribute values
feature.fid         # Feature ID (OBJECTID)

# Dict-like access
feature["column_name"]
feature.get("column_name", default)
```

### Geometry Objects

All geometry objects have these common properties:

```python
geom.wkt          # Well-Known Text representation
geom.bounds       # BoundingBox (xmin, ymin, xmax, ymax)
geom.has_z        # Whether geometry has Z values
geom.coordinates  # Coordinate tuples
```

### Converters

```python
from mobile_geodatabase import (
    to_wkt,              # Convert to WKT string
    to_wkb,              # Convert to WKB bytes
    to_geojson_geometry, # Convert to GeoJSON geometry dict
    feature_to_geojson,  # Convert Feature to GeoJSON feature dict
    write_geojson,       # Write table to GeoJSON file
    write_geojsonl,      # Write table to GeoJSON Lines file
)
```

## Technical Details

This library reverse-engineers the ST_Geometry blob format used in Esri Mobile Geodatabases. Key findings:

- **Magic Header**: `0x64 0x11 0x0F 0x00`
- **Scale Factor**: Coordinates use 2x the metadata scale value
- **Coordinate Encoding**: Varint encoding with zigzag for deltas
- **Multi-part Detection**: Parts are identified by absolute coordinates (>100 billion)

See [docs/format.md](docs/format.md) for complete format documentation.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for package management, [ruff](https://docs.astral.sh/ruff/) for linting/formatting, and [pyright](https://github.com/microsoft/pyright) for type checking.

### Setup

```bash
# Create virtual environment and install dependencies
uv venv
uv pip install -e ".[dev]"

# Install pre-commit hooks
uv run pre-commit install
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v

# Run tests with coverage
uv run pytest --cov=mobile_geodatabase

# Run specific test file
uv run pytest tests/test_geometry.py
```

### Linting & Formatting

```bash
# Check for linting errors
uv run ruff check src tests

# Auto-fix linting errors
uv run ruff check --fix src tests

# Check formatting
uv run ruff format --check src tests

# Apply formatting
uv run ruff format src tests
```

### Type Checking

```bash
# Run type checker (strict mode)
uv run pyright src tests
```

### Pre-commit Hooks

Pre-commit hooks run automatically on `git commit`. To run manually:

```bash
# Run all hooks on staged files
uv run pre-commit run

# Run all hooks on all files
uv run pre-commit run --all-files

# Update hook versions
uv run pre-commit autoupdate
```

### All Checks

```bash
# Run all checks (lint, format, typecheck, tests)
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src tests && uv run pytest
```

## License

MIT License - see LICENSE file.

## Acknowledgments

The ST_Geometry format was reverse-engineered by analyzing real geodatabase files. This library is not affiliated with or endorsed by Esri. Also doesn't really work...yet.
