"""
MCP stdio server — exposes describe_schema as an MCP tool.

Purpose: demonstrate that the harness shell governs MCP tools identically
to native tools. The MCPToolAdapter in harness/ wraps this server's tools
in the same ToolDefinition contracts and registers them in the same registry.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root to path when running as standalone server
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp import types  # type: ignore[import-untyped]
from mcp.server import Server  # type: ignore[import-untyped]
from mcp.server.stdio import stdio_server  # type: ignore[import-untyped]

app = Server("agent-harness-mcp")

SCHEMA_INFO = """
Tables in the cloud billing warehouse:

gcp_billing_export (date DATE, project_id STRING, service STRING,
    sku STRING, usage_amount DOUBLE, cost_usd DOUBLE, currency STRING)

gcp_resource_usage (date DATE, project_id STRING, resource_type STRING,
    resource_name STRING, region STRING, utilization_pct DOUBLE)

gcp_credits (date DATE, project_id STRING, credit_type STRING,
    credit_amount_usd DOUBLE)
"""


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="describe_schema",
            description="Return schema information for Iceberg warehouse tables.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Optional table name to filter",
                    }
                },
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, object]) -> list[types.TextContent]:
    if name == "describe_schema":
        table_name = arguments.get("table_name")
        if table_name:
            lines = [
                line for line in SCHEMA_INFO.splitlines() if str(table_name).lower() in line.lower()
            ]
            text = "\n".join(lines) or f"Table '{table_name}' not found"
        else:
            text = SCHEMA_INFO.strip()
        return [types.TextContent(type="text", text=text)]
    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
