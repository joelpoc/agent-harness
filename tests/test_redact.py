"""Unit tests for PII redaction."""

from __future__ import annotations

from harness.redact import redact, redact_dict


def test_email_redacted() -> None:
    assert redact("Contact joel@example.com for help") == "Contact [EMAIL] for help"


def test_multiple_emails_redacted() -> None:
    text = "From: alice@corp.com, To: bob@corp.com"
    result = redact(text)
    assert "[EMAIL]" in result
    assert "@" not in result.replace("[EMAIL]", "")


def test_no_pii_unchanged() -> None:
    text = "SELECT cost_usd FROM gcp_billing WHERE project = 'analytics'"
    assert redact(text) == text


def test_phone_redacted() -> None:
    result = redact("Call +34 612 345 678 now")
    assert "[PHONE]" in result


def test_redact_dict_strings() -> None:
    data: dict[str, object] = {
        "email": "test@example.com",
        "count": 42,
        "name": "safe",
    }
    result = redact_dict(data)
    assert result["email"] == "[EMAIL]"
    assert result["count"] == 42
    assert result["name"] == "safe"


def test_redact_dict_nested() -> None:
    data: dict[str, object] = {"user": {"email": "a@b.com", "role": "admin"}}
    result = redact_dict(data)
    user = result["user"]
    assert isinstance(user, dict)
    assert user["email"] == "[EMAIL]"


def test_redact_dict_list_values() -> None:
    data: dict[str, object] = {"contacts": ["alice@x.com", "bob@y.com"]}
    result = redact_dict(data)
    contacts = result["contacts"]
    assert isinstance(contacts, list)
    for item in contacts:
        assert isinstance(item, str)
        assert "[EMAIL]" in item
