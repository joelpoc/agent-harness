# ADR 009 — sqlglot AST Guard for SQL Read-Only Enforcement

## Context

`query_data` must only execute read-only SQL. The initial enforcement used
`deny_if` substring matching in the policy YAML:

```yaml
deny_if:
  sql:
    - "DROP "
    - "DELETE "
    - "TRUNCATE "
```

This has a structural weakness: it matches on the serialised string, not on
the parsed statement. Several bypass patterns work against substring checks:

```sql
DROP\nTABLE foo          -- newline removes the trailing space from "DROP "
SELECT 1; DROP TABLE foo -- second statement missed if batch not split
DROP/*comment*/TABLE foo -- comment injection
```

The LLM is unlikely to attempt these bypasses deliberately, but a substring
check is a weak guarantee for a system whose thesis is deterministic shell
enforcement.

## Decision

Replace `deny_if` for SQL enforcement with an AST-based guard using
**sqlglot** (`harness/sql_guard.py`):

1. `sqlglot.parse(sql)` — parses all dialects, returns a list of statements
2. Walk every AST node in every statement
3. Deny if any node is an instance of a mutating expression type:
   `Drop`, `Delete`, `Insert`, `Update`, `Create`, `TruncateTable`, `Alter`, `Command`
4. Deny if the SQL cannot be parsed (unparseable → deny by default)

The YAML policy rule changes from:
```yaml
deny_if:
  sql: ["DROP ", "DELETE ", ...]
```
to:
```yaml
require_read_only_sql: true
```

`deny_if` remains in `ToolPolicy` for non-SQL arg checks (e.g. blocking
specific table names or field values in other tools).

## Why sqlglot

- Pure Python, no native extensions — works in all environments including
  offline/air-gapped
- Supports all major SQL dialects (DuckDB, BigQuery, Postgres, etc.)
- AST walk is structural: `DROP\nTABLE` parses to the same `exp.Drop` node as
  `DROP TABLE` — whitespace and comments are irrelevant at the AST level
- Multi-statement batches (`SELECT 1; DROP TABLE foo`) are caught because
  `sqlglot.parse()` returns all statements and we walk each one

## Consequences

- **Stronger guarantee**: bypass patterns that defeat substring matching are
  caught at the AST level. The policy is enforceable, not advisory.
- **Cleaner YAML**: `require_read_only_sql: true` is self-documenting.
  `deny_if` keyword lists were fragile and required manual maintenance.
- **New dependency**: `sqlglot>=25.0` — pure Python, MIT licensed, no
  native extensions. Acceptable per the "boring dependencies" principle;
  no ADR would be needed for a utility this contained, but the SQL guard is
  a security control so the reasoning is worth documenting.
- **Known limitation**: sqlglot parses standard SQL dialects. Highly
  dialect-specific obfuscation (e.g. database-specific `EXEC` variants) may
  not parse, but unparseable SQL is DENY by default — the failure mode is safe.
- **Test coverage**: `tests/test_sql_guard.py` explicitly tests the bypass
  patterns that substring matching would miss (newline injection, multi-
  statement batches, comment injection, identifier named DROP).
