"""
sql_guard — AST-based read-only SQL enforcement.

Guarantee: is_read_only() returns False for any SQL that contains a mutating
statement (DROP, DELETE, INSERT, UPDATE, CREATE, TRUNCATE, ALTER), regardless
of whitespace, comments, casing, or multi-statement batches.

Uses sqlglot to parse SQL into an AST and walks every node — a structural
check that cannot be bypassed by spacing or comment injection unlike substring
matching.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

_MUTATING_NODES = (
    exp.Drop,
    exp.Delete,
    exp.Insert,
    exp.Update,
    exp.Create,
    exp.TruncateTable,
    exp.Alter,
    exp.Command,  # catches EXEC, CALL, and other raw command statements
)


def is_read_only(sql: str) -> bool:
    """
    Return True only if sql contains exclusively read operations.

    Returns False if:
    - sql contains any mutating statement
    - sql cannot be parsed (unparseable SQL is denied by default)
    - sql is empty
    """
    if not sql or not sql.strip():
        return False

    try:
        statements = sqlglot.parse(sql)
    except sqlglot.errors.ParseError:
        return False  # unparseable → deny

    if not statements:
        return False

    for statement in statements:
        if statement is None:
            continue
        for node in statement.walk():
            if isinstance(node, _MUTATING_NODES):
                return False

    return True
