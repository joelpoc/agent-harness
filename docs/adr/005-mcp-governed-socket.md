# ADR 005 — MCP via Governed Stdio Socket

## Context
The Cloudera JD references MCP (Model Context Protocol). We need to demonstrate MCP integration while maintaining the thesis: the shell governs all tool calls regardless of transport.

## Decision
Expose `describe_schema` via a local **stdio MCP server** (`mcp_server/server.py`). The `MCPToolAdapter` in `harness/mcp_adapter.py` discovers this server's tools and registers them in the central `ToolRegistry` with a `mcp/` prefix.

Policy rules for `mcp/*` are stricter than native tools (REQUIRE_APPROVAL for all).

The agent loop cannot distinguish native from MCP tools — both appear in the registry with the same `ToolDefinition` shape and pass through the same hook pipeline.

## Consequences
- The same audit event structure, policy engine, and budget tracker covers MCP tools.
- Adding more MCP servers requires zero changes to `harness/` — the adapter handles discovery.
- Demo: registry listing shows `describe_schema` (native) and `mcp/describe_schema` side by side, both governed.
- Transport: stdio only. No network sockets in the demo — simpler, more reliable.

## Evolution

ADR 008 extends this decision by connecting to the **official GitHub MCP server** as a real third-party trust boundary — same governed stdio transport, same hook pipeline, but with whitelist-only tool registration to prevent context flooding and a fine-grained PAT for defense in depth.
