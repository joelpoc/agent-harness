"""
query_data — text-to-SQL tool over Apache Iceberg tables via DuckDB.

Guarantee: ALL numbers in responses come from SQL execution against the
data warehouse. The model provides the SQL query; DuckDB computes the result.
The model never invents or estimates figures.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import Field

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, registry

if TYPE_CHECKING:
    import duckdb as _duckdb

_WAREHOUSE = Path(os.getenv("WAREHOUSE_PATH", "data/warehouse"))
_TABLES = ["gcp_billing_export", "gcp_resource_usage", "gcp_credits"]


class QueryDataInput(ToolInput):
    sql: str = Field(description="SQL query to execute against the Iceberg warehouse")


class QueryDataOutput(ToolOutput):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)


def _get_connection() -> _duckdb.DuckDBPyConnection:
    import duckdb

    con = duckdb.connect(database=":memory:")
    con.execute("INSTALL iceberg; LOAD iceberg;")
    # Create views over warehouse files so queries use plain table names
    for table in _TABLES:
        iceberg_path = _WAREHOUSE / table
        parquet_path = _WAREHOUSE / f"{table}.parquet"
        if iceberg_path.exists():
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM iceberg_scan('{iceberg_path}')")
        elif parquet_path.exists():
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{parquet_path}')")
    return con


async def _query_handler(sql: str) -> QueryDataOutput:
    """Execute SQL against the local DuckDB+Iceberg warehouse."""
    try:
        con = _get_connection()
        result = con.execute(sql).fetchdf()
        return QueryDataOutput(
            success=True,
            rows=result.to_dict(orient="records"),
            row_count=len(result),
            columns=list(result.columns),
        )
    except Exception as e:
        return QueryDataOutput(success=False, error=str(e))


registry.register(
    ToolDefinition(
        name="query_data",
        description=(
            "Execute a SQL statement against the cloud billing/usage warehouse. "
            "Supports SELECT, INSERT, UPDATE, DELETE, and DDL. "
            "Returns rows and column names. ALL numbers must come from this tool — "
            "never invent or estimate figures."
        ),
        input_schema=QueryDataInput,
        output_schema=QueryDataOutput,
        handler=_query_handler,  # type: ignore[arg-type]
        tags=["data", "sql"],
    )
)
