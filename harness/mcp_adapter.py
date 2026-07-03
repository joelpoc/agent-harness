"""
mcp_adapter — bridges MCP tool discovery to the harness contract registry.

Guarantee: MCP tools discovered via stdio transport are wrapped in the same
ToolDefinition contract and registered in the same registry as native tools.
They pass through the same hook pipeline and policy engine. The agent loop
cannot distinguish native from MCP tools — that uniformity is the point.
"""

from __future__ import annotations

from typing import Any

from pydantic import create_model

from harness.contracts import ToolDefinition, ToolInput, ToolOutput, ToolRegistry


class MCPToolAdapter:
    """
    Discovers tools from a running MCP server (stdio) and registers them
    in the harness registry with a 'mcp/' prefix.
    """

    def __init__(self, server_command: list[str], registry: ToolRegistry) -> None:
        self._command = server_command
        self._registry = registry

    async def discover_and_register(self) -> list[str]:
        """
        Connect to the MCP server, list tools, wrap each in a ToolDefinition,
        register in the registry. Returns list of registered tool names.
        """
        from mcp import ClientSession, StdioServerParameters  # type: ignore[import-untyped]
        from mcp.client.stdio import stdio_client  # type: ignore[import-untyped]

        registered: list[str] = []
        server_params = StdioServerParameters(command=self._command[0], args=self._command[1:])

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()

                for mcp_tool in tools_result.tools:
                    prefixed_name = f"mcp/{mcp_tool.name}"
                    input_model = self._make_input_model(prefixed_name, mcp_tool.inputSchema or {})
                    handler = self._make_handler(session, mcp_tool.name)

                    definition = ToolDefinition(
                        name=prefixed_name,
                        description=mcp_tool.description or "",
                        input_schema=input_model,
                        output_schema=self._make_output_model(prefixed_name),
                        handler=handler,
                        source="mcp",
                        tags=["mcp"],
                    )
                    self._registry.register(definition)
                    registered.append(prefixed_name)

        return registered

    def _make_input_model(self, tool_name: str, schema: dict[str, Any]) -> type[ToolInput]:
        """Dynamically create a ToolInput subclass from MCP JSON schema."""
        fields: dict[str, Any] = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            fields[prop_name] = (str, ...)
        return create_model(  # type: ignore[call-overload]
            f"{tool_name}_Input", __base__=ToolInput, **fields
        )

    def _make_output_model(self, tool_name: str) -> type[ToolOutput]:
        return create_model(  # type: ignore[call-overload]
            f"{tool_name}_Output",
            __base__=ToolOutput,
            content=(str, ""),
        )

    def _make_handler(self, session: Any, tool_name: str) -> Any:
        async def handler(**kwargs: Any) -> Any:
            result = await session.call_tool(tool_name, arguments=kwargs)
            content = result.content[0].text if result.content else ""
            return {"success": True, "content": content}

        return handler
