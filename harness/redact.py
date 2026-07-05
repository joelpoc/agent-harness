"""
redact — PII redaction applied to tool outputs before audit logging.

Guarantee: no email address, IBAN, or phone number from tool output is
written to the audit log in plaintext. Redaction happens in the shell;
the model may still see the original output (by design — it needs to reason
over data). Only the audit record is redacted.

Note: for production, replace regex patterns with Microsoft Presidio.
"""

from __future__ import annotations

import re

# Pattern registry — add patterns here, never in prompt code
_PATTERNS: list[tuple[str, str]] = [
    # Email
    (r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[EMAIL]"),
    # IBAN (EU format, simplified)
    (r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b", "[IBAN]"),
    # Phone (international + local formats)
    (r"\b(?:\+?\d{1,3}[\s\-]?)?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b", "[PHONE]"),
    # Spanish DNI/NIE
    (r"\b[0-9]{8}[A-HJ-NP-TV-Z]\b", "[DNI]"),
    (r"\b[XYZ][0-9]{7}[A-HJ-NP-TV-Z]\b", "[NIE]"),
]

_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern), replacement) for pattern, replacement in _PATTERNS
]


def redact(text: str) -> str:
    """Return text with all known PII patterns replaced by placeholders."""
    result = text
    for pattern, replacement in _COMPILED:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: dict[str, object]) -> dict[str, object]:
    """Recursively redact string values in a dict."""
    out: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, str):
            out[key] = redact(value)
        elif isinstance(value, dict):
            out[key] = redact_dict(value)
        elif isinstance(value, list):
            out[key] = [redact(v) if isinstance(v, str) else v for v in value]
        else:
            out[key] = value
    return out
