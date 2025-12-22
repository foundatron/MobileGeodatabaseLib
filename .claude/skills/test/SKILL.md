---
name: test
description: Run pytest tests for the Mobile Geodatabase library. Use when the user wants to run tests, check test coverage, run specific test files, or debug test failures.
allowed-tools: Bash
---

# Test Runner

Run pytest tests for the Mobile Geodatabase library with various options.

## Common Commands

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_geometry.py
uv run pytest tests/test_decoder.py
uv run pytest tests/test_converters.py
uv run pytest tests/test_integration.py

# Run with coverage report
uv run pytest --cov=mobile_geodatabase

# Run with HTML coverage report
uv run pytest --cov=mobile_geodatabase --cov-report=html

# Run specific test by name pattern
uv run pytest -k "test_point"
uv run pytest -k "test_decode"

# Run and stop on first failure
uv run pytest -x

# Run with detailed failure output
uv run pytest -vvs
```

## Test Structure

```
tests/
├── test_geometry.py      # Geometry class unit tests
├── test_decoder.py       # ST_Geometry decoder tests (varint, zigzag, etc.)
├── test_converters.py    # Format converter tests (WKT, WKB, GeoJSON)
└── test_integration.py   # End-to-end tests (requires test database)
```

## Test Database

Integration tests require a test database at:

```
/tmp/geodatabase_test/replica.geodatabase
```

If missing, integration tests will be skipped (not failed).

## Coverage Goals

- Focus on decoder edge cases (multi-part detection, coordinate scaling)
- Ensure all geometry types are covered (Point, LineString, Polygon, Multi\*)
- Test both 2D and 3D (Z) coordinate variants
