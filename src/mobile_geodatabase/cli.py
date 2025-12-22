"""
Command-line interface for mobile-geodatabase.

Usage:
    mobile-geodatabase info <file.geodatabase>
    mobile-geodatabase convert <input.geodatabase> <output.geojson> [--table TABLE]
    mobile-geodatabase dump <file.geodatabase> <table> [--format FORMAT]
"""

import json
import sys
from pathlib import Path

import click

from .converters import to_wkt, write_geojson, write_geojsonl, write_geopackage
from .database import GeoDatabase


@click.group()
@click.version_option()
def main():
    """
    Read Esri Mobile Geodatabase (.geodatabase) files.

    This tool reads .geodatabase files without requiring Esri's proprietary
    libstgeometry_sqlite.so library.
    """
    pass


@main.command()
@click.argument("geodatabase", type=click.Path(exists=True))
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def info(geodatabase: str, output_json: bool):
    """
    Display information about a geodatabase file.

    Shows tables, geometry types, row counts, and coordinate system info.
    """
    try:
        gdb = GeoDatabase(geodatabase)
    except Exception as e:
        click.echo(f"Error opening geodatabase: {e}", err=True)
        sys.exit(1)

    if output_json:
        tables_list: list[dict[str, str | int | list[str] | None]] = []
        for table in gdb.tables:
            table_info: dict[str, str | int | list[str] | None] = {
                "name": table.name,
                "row_count": table.row_count,
                "columns": table.columns,
            }
            if table.has_geometry:
                table_info["geometry_column"] = table.geometry_column
                table_info["geometry_type"] = table.geometry_type
                if table.coord_system and table.coord_system.srid:
                    table_info["srid"] = table.coord_system.srid
            tables_list.append(table_info)
        data: dict[str, str | list[dict[str, str | int | list[str] | None]]] = {
            "path": str(gdb.path),
            "tables": tables_list,
        }
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"Geodatabase: {gdb.path.name}")
        click.echo(f"Path: {gdb.path}")
        click.echo()

        if not gdb.tables:
            click.echo("No tables found.")
            return

        # Find tables with geometry
        geom_tables = [t for t in gdb.tables if t.has_geometry]
        other_tables = [t for t in gdb.tables if not t.has_geometry]

        if geom_tables:
            click.echo("Geometry Tables:")
            click.echo("-" * 60)
            for table in geom_tables:
                click.echo(f"  {table.name}")
                click.echo(f"    Type: {table.geometry_type or 'Unknown'}")
                click.echo(f"    Rows: {table.row_count:,}")
                if table.coord_system and table.coord_system.srid:
                    click.echo(f"    SRID: {table.coord_system.srid}")
                click.echo()

        if other_tables:
            click.echo("Other Tables:")
            click.echo("-" * 60)
            for table in other_tables:
                click.echo(f"  {table.name}: {table.row_count:,} rows")

    gdb.close()


@main.command()
@click.argument("geodatabase", type=click.Path(exists=True))
@click.argument("output", type=click.Path())
@click.option(
    "--table", "-t", help="Table name to convert (required if multiple tables)"
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["geojson", "geojsonl", "gpkg"]),
    help="Output format (default: auto-detect from extension)",
)
@click.option("--limit", "-n", type=int, help="Limit number of features")
@click.option("--where", "-w", help="SQL WHERE clause to filter features")
@click.option("--compact", is_flag=True, help="Compact JSON output (no indentation)")
def convert(
    geodatabase: str,
    output: str,
    table: str | None,
    output_format: str | None,
    limit: int | None,
    where: str | None,
    compact: bool,
):
    """
    Convert geodatabase table to GeoJSON or GeoPackage.

    Examples:
        mobile-geodatabase convert input.geodatabase output.geojson
        mobile-geodatabase convert input.geodatabase rivers.geojson -t Rivers
        mobile-geodatabase convert input.geodatabase data.geojsonl -n 1000
        mobile-geodatabase convert input.geodatabase output.gpkg -f gpkg
    """
    try:
        gdb = GeoDatabase(geodatabase)
    except Exception as e:
        click.echo(f"Error opening geodatabase: {e}", err=True)
        sys.exit(1)

    # Get tables with geometry
    geom_tables = [t for t in gdb.tables if t.has_geometry]

    if not geom_tables:
        click.echo("No geometry tables found in geodatabase.", err=True)
        sys.exit(1)

    # Determine which table to convert
    if table:
        table_info = gdb.get_table(table)
        if not table_info:
            click.echo(f"Table not found: {table}", err=True)
            click.echo(f"Available tables: {', '.join(t.name for t in geom_tables)}")
            sys.exit(1)
        table_name = table_info.name
    elif len(geom_tables) == 1:
        table_name = geom_tables[0].name
    else:
        click.echo(
            "Multiple geometry tables found. Please specify one with --table:", err=True
        )
        for t in geom_tables:
            click.echo(f"  {t.name} ({t.geometry_type}, {t.row_count:,} rows)")
        sys.exit(1)

    # Determine output format
    output_path = Path(output)
    if output_format:
        fmt = output_format
    elif output_path.suffix.lower() == ".geojsonl":
        fmt = "geojsonl"
    elif output_path.suffix.lower() == ".gpkg":
        fmt = "gpkg"
    else:
        fmt = "geojson"

    # Do the conversion
    click.echo(f"Converting {table_name} to {fmt}...")

    try:
        if fmt == "geojsonl":
            count = write_geojsonl(gdb, table_name, output, where=where, limit=limit)
        elif fmt == "gpkg":
            count = write_geopackage(gdb, table_name, output, where=where, limit=limit)
        else:
            indent = None if compact else 2
            count = write_geojson(
                gdb, table_name, output, indent=indent, where=where, limit=limit
            )

        click.echo(f"Wrote {count:,} features to {output}")

    except Exception as e:
        click.echo(f"Error during conversion: {e}", err=True)
        sys.exit(1)

    gdb.close()


@main.command()
@click.argument("geodatabase", type=click.Path(exists=True))
@click.argument("table")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["wkt", "geojson"]),
    default="wkt",
    help="Output format for geometries",
)
@click.option(
    "--limit",
    "-n",
    type=int,
    default=10,
    help="Number of features to show (default: 10)",
)
@click.option("--where", "-w", help="SQL WHERE clause")
def dump(
    geodatabase: str, table: str, output_format: str, limit: int, where: str | None
):
    """
    Dump features from a table.

    Shows geometry and attributes for quick inspection.

    Example:
        mobile-geodatabase dump file.geodatabase Rivers -n 5
    """
    try:
        gdb = GeoDatabase(geodatabase)
    except Exception as e:
        click.echo(f"Error opening geodatabase: {e}", err=True)
        sys.exit(1)

    table_info = gdb.get_table(table)
    if not table_info:
        click.echo(f"Table not found: {table}", err=True)
        sys.exit(1)

    for i, feature in enumerate(gdb.read_table(table, where=where, limit=limit)):
        click.echo(f"--- Feature {i + 1} (FID: {feature.fid}) ---")

        if feature.geometry:
            if output_format == "wkt":
                click.echo(f"Geometry: {to_wkt(feature.geometry)}")
            else:
                from .converters import to_geojson_geometry

                click.echo(
                    f"Geometry: {json.dumps(to_geojson_geometry(feature.geometry))}"
                )
        else:
            click.echo("Geometry: None")

        if feature.attributes:
            click.echo("Attributes:")
            for key, value in feature.attributes.items():
                if value is not None:
                    click.echo(f"  {key}: {value}")
        click.echo()

    gdb.close()


@main.command("list-tables")
@click.argument("geodatabase", type=click.Path(exists=True))
def list_tables(geodatabase: str):
    """
    List all tables in the geodatabase.

    Simple output suitable for scripting.
    """
    try:
        gdb = GeoDatabase(geodatabase)
    except Exception as e:
        click.echo(f"Error opening geodatabase: {e}", err=True)
        sys.exit(1)

    for table in gdb.tables:
        if table.has_geometry:
            click.echo(f"{table.name}\t{table.geometry_type}\t{table.row_count}")
        else:
            click.echo(f"{table.name}\t-\t{table.row_count}")

    gdb.close()


if __name__ == "__main__":
    main()
