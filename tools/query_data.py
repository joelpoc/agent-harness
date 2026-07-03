"""
query_data — text-to-SQL tool over Apache Iceberg tables via DuckDB.

Guarantee: ALL numbers in responses come from SQL execution against the
data warehouse. The model provides the SQL query; DuckDB computes the result.
The model never invents or estimates figures.
"""

from __future__ import annotations

from pydantic import Field

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, registry


class QueryDataInput(ToolInput):
    sql: str = Field(description="SQL query to execute against the Iceberg warehouse")


class QueryDataOutput(ToolOutput):
    rows: list[dict[str, object]] = Field(default_factory=list)
    row_count: int = 0
    columns: list[str] = Field(default_factory=list)


async def _query_handler(sql: str) -> QueryDataOutput:
    """Execute SQL against the local DuckDB+Iceberg warehouse."""
    try:
        import duckdb

        con = duckdb.connect(database=":memory:")
        # Load Iceberg extension
        con.execute("INSTALL iceberg; LOAD iceberg;")
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
            "Execute a SQL query against the cloud billing/usage Iceberg warehouse. "
            "Returns rows and column names. ALL numbers must come from this tool — "
            "never invent or estimate figures."
        ),
        input_schema=QueryDataInput,
        output_schema=QueryDataOutput,
        handler=_query_handler,  # type: ignore[arg-type]
        tags=["data", "sql"],
    )
)
