"""
describe_schema — returns table schema from the Iceberg warehouse.

This tool is also exposed via the MCP server (mcp_server/server.py) to
demonstrate that the same governance shell covers both native and MCP tools.
"""

from __future__ import annotations

from pydantic import Field

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, registry

SCHEMA_INFO = """
Tables in the cloud billing warehouse:

gcp_billing_export (date DATE, project_id STRING, service STRING,
    sku STRING, usage_amount DOUBLE, cost_usd DOUBLE, currency STRING)

gcp_resource_usage (date DATE, project_id STRING, resource_type STRING,
    resource_name STRING, region STRING, utilization_pct DOUBLE)

gcp_credits (date DATE, project_id STRING, credit_type STRING,
    credit_amount_usd DOUBLE)
"""


class DescribeSchemaInput(ToolInput):
    table_name: str | None = Field(
        default=None, description="Optional: specific table name to describe"
    )


class DescribeSchemaOutput(ToolOutput):
    schema_text: str = ""


async def _describe_handler(table_name: str | None = None) -> DescribeSchemaOutput:
    if table_name:
        # Filter to relevant table
        lines = [line for line in SCHEMA_INFO.splitlines() if table_name.lower() in line.lower()]
        text = "\n".join(lines) or f"Table '{table_name}' not found"
    else:
        text = SCHEMA_INFO.strip()
    return DescribeSchemaOutput(success=True, schema_text=text)


registry.register(
    ToolDefinition(
        name="describe_schema",
        description="Return schema information for Iceberg warehouse tables.",
        input_schema=DescribeSchemaInput,
        output_schema=DescribeSchemaOutput,
        handler=_describe_handler,  # type: ignore[arg-type]
        tags=["data", "schema"],
    )
)
