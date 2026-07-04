"""
describe_schema — returns table schema read directly from the Iceberg warehouse.

Guarantee: schema information is always in sync with the actual warehouse files.
Falls back to DuckDB DESCRIBE if Iceberg metadata is unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, registry

_WAREHOUSE = Path(os.getenv("WAREHOUSE_PATH", "data/warehouse"))
_TABLES = ["gcp_billing_export", "gcp_resource_usage", "gcp_credits"]


def _read_schema_from_warehouse() -> dict[str, list[dict[str, str]]]:
    """Read column names and types directly from Iceberg/Parquet files."""
    import duckdb

    con = duckdb.connect(":memory:")
    con.execute("INSTALL iceberg; LOAD iceberg;")

    schema: dict[str, list[dict[str, str]]] = {}
    for table in _TABLES:
        iceberg_path = _WAREHOUSE / table
        parquet_path = _WAREHOUSE / f"{table}.parquet"

        if iceberg_path.exists():
            source = f"iceberg_scan('{iceberg_path}')"
        elif parquet_path.exists():
            source = f"read_parquet('{parquet_path}')"
        else:
            continue

        rows = con.execute(f"DESCRIBE SELECT * FROM {source}").fetchall()
        schema[table] = [{"column": row[0], "type": row[1]} for row in rows]

    return schema


def _format_schema(schema: dict[str, list[dict[str, str]]], table_name: str | None) -> str:
    tables = {table_name: schema[table_name]} if table_name and table_name in schema else schema
    if not tables:
        return f"Table '{table_name}' not found in warehouse."

    lines = []
    for tbl, columns in tables.items():
        col_str = ", ".join(f"{c['column']} {c['type']}" for c in columns)
        lines.append(f"{tbl} ({col_str})")
    return "\n\n".join(lines)


class DescribeSchemaInput(ToolInput):
    table_name: str | None = Field(
        default=None, description="Optional: specific table name to describe"
    )


class DescribeSchemaOutput(ToolOutput):
    schema_text: str = ""


async def _describe_handler(table_name: str | None = None) -> DescribeSchemaOutput:
    try:
        schema = _read_schema_from_warehouse()
        text = _format_schema(schema, table_name)
    except Exception as e:
        text = f"Could not read schema from warehouse: {e}"
    return DescribeSchemaOutput(success=True, schema_text=text)


registry.register(
    ToolDefinition(
        name="describe_schema",
        description=(
            "Return schema information for Iceberg warehouse tables — "
            "column names and types read directly from the warehouse files."
        ),
        input_schema=DescribeSchemaInput,
        output_schema=DescribeSchemaOutput,
        handler=_describe_handler,  # type: ignore[arg-type]
        tags=["data", "schema"],
    )
)
