# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pure Python library for reading Esri Mobile Geodatabase (.geodatabase) files. The project reverse-engineered the proprietary ST_Geometry blob format with 100% success on 51,895 test geometries. No Esri dependencies required.

## Commands

```bash
# Setup
uv venv && uv pip install -e ".[dev]"
uv run pre-commit install

# Testing
uv run pytest                          # all tests
uv run pytest tests/test_geometry.py   # single file
uv run pytest -v                       # verbose
uv run pytest --cov=mobile_geodatabase # with coverage

# Linting & Formatting
uv run ruff check src tests            # lint
uv run ruff check --fix src tests      # lint + autofix
uv run ruff format src tests           # format

# Type Checking (strict mode)
uv run pyright src tests

# All checks at once
uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src tests && uv run pytest
```

## Architecture

The library has a clean layered architecture:

```
database.py (GeoDatabase) → decoder.py (STGeometryDecoder) → geometry.py (Point, LineString, etc.)
                        ↘ converters.py (GeoJSON, WKT, WKB export)
```

**Key modules:**

- `database.py`: High-level API. `GeoDatabase` opens SQLite files, reads table metadata from `GDB_Items` and `st_geometry_columns`, extracts coordinate system params from embedded XML
- `decoder.py`: ST_Geometry blob decoder. Handles varint parsing, zigzag decoding, multi-part detection via 100B threshold
- `geometry.py`: Dataclasses for all geometry types with WKT output
- `converters.py`: Export functions for GeoJSON, WKT, WKB formats
- `cli.py`: Click-based CLI (`mobile-geodatabase info/convert/dump/list-tables`)

**Critical encoding details (from reverse engineering):**

- Magic header: `0x64 0x11 0x0F 0x00`
- Coordinates use 2x the XML metadata scale (`XYScale=10000` → actual scale = 20000)
- Multi-part geometries detected when varint > 100 billion (absolute coord vs delta)
- Formula: `x = raw_x / (scale * 2) + x_origin`

See `docs/format.md` for complete format documentation.

## Code Quality Rules

- **Never add linting ignore comments** (e.g., `# type: ignore`, `# noqa`, `# pyright: ignore`). Fix the underlying issue instead.
- All code must pass ruff and pyright checks without suppressions.
- Python 3.12+ required; use modern union syntax (`X | Y` not `Union[X, Y]`)
