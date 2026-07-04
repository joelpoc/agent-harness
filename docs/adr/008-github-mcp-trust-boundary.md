# ADR 008 — GitHub MCP as a Real Trust Boundary

## Context

The harness demo uses MCP to show that external tool servers get identical
governance (policy gate, audit, hook pipeline) as native tools. The first MCP
server was our own mock (`mcp_server/`) — offline, safe for demos, no
credentials.

Adding the official GitHub MCP server (`github-mcp-server`) introduces a
**real third-party trust boundary**:

- Real network calls (GitHub REST API)
- Real credentials (Personal Access Token stored in `.env`)
- A large tool surface: the server exposes ~30+ tools covering repos, files,
  branches, PRs, issues, releases, and more

Without additional controls, connecting to this server would flood the agent's
context with tools it must never call, and a credential leak would expose
far more than issue creation.

## Decision

### 1. Whitelist-only registration

`MCPToolAdapter.discover_and_register(whitelist=["create_issue"])` connects to
the server, lists all tools, and registers **only** those in the whitelist.
The agent's context window never contains GitHub's repo/file/branch tools.

### 2. Token scoping = defense in depth

The PAT documented in `.env.example` must be a **fine-grained token**:
- Permission: Issues → Read & Write only
- Repository access: single repo (`GITHUB_REPO_NAME`)
- No code, no secrets, no branch operations

Even if the agent escapes policy, the token physically cannot push code,
delete branches, or read repository contents.

### 3. Explicit deny for all non-whitelisted GitHub tools

`policies/default.yaml` adds:
```yaml
- pattern: mcp/github/create_issues
  decision: REQUIRE_APPROVAL     # human approval, always
- pattern: mcp/github/*
  decision: DENY                 # everything else blocked at policy layer
```

This is belt-and-suspenders on top of the whitelist: if a non-whitelisted tool
somehow reached the policy engine, it is DENY before it can execute.

### 4. Invariant audit shape

`create_ticket` is always the tool the agent calls. The backend (mock vs
github) is an implementation detail inside the handler. Audit events always
record `tool_name=create_ticket`, `args_hash=<sha256>`, `decision=REQUIRE_APPROVAL`.
The audit log consumer never sees "github" vs "mock" — only the contract.

### 5. TICKETS_BACKEND env var

`TICKETS_BACKEND=mock` (default) → offline, no credentials needed.
`TICKETS_BACKEND=github` → real GitHub issue via `github-mcp-server stdio`.
The agent loop, policy engine, and audit logger are unaware of this setting.

## Consequences

**Demo value**: live proof that the harness governs a real external server at
an actual trust boundary — not a toy mock. A real GitHub issue is created with
human approval; the audit log shows the identical event shape.

**Air-gapped path preserved**: `TICKETS_BACKEND=mock` + `ollama/qwen2.5:14b` =
fully offline demo. The github path is opt-in.

**CI never hits GitHub**: the github dispatch function (`_call_github_mcp_create_issue`)
is monkeypatched in unit tests. No binary, no PAT, no network required in CI.

**No tool surface creep**: GitHub's full tool list never appears in the agent
context. The registry stays focused on the four declared tools plus
`mcp/github/create_issues` when the github backend is active.

**Rejected alternatives**:
- *Register all GitHub tools, deny via policy only*: flooding context is itself
  a risk — a confused model might attempt a denied tool and waste tokens.
- *Embed GitHub API calls directly (no MCP)*: loses the governance demo point.
  The whole value is showing the same hook pipeline governs external servers.
