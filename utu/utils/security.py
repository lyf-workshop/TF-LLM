"""Helpers for removing credentials from logs and persisted diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "***"

_SENSITIVE_EXACT_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "authorization",
    "base_url",
    "client_secret",
    "cookie",
    "credentials",
    "database_url",
    "db_url",
    "password",
    "passwd",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}
_SENSITIVE_SUFFIXES = (
    "_api_key",
    "_access_key",
    "_access_token",
    "_auth_token",
    "_base_url",
    "_client_secret",
    "_credential",
    "_credentials",
    "_database_url",
    "_db_url",
    "_password",
    "_private_key",
    "_refresh_token",
    "_secret",
)
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"(?:[A-Z0-9_]*API[_-]?KEY)|"
    r"(?:[A-Z0-9_]*(?:ACCESS|AUTH|REFRESH)[_-]?TOKEN)|"
    r"(?:AUTHORIZATION)|(?:PASSWORD)|(?:PASSWD)|(?:CLIENT[_-]?SECRET)|"
    r"(?:DB[_-]?URL)|(?:BASE[_-]?URL)"
    r")(\s*[:=]\s*)(?:Bearer\s+)?([^\s,;&\"']+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_URL_USERINFO_RE = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@"
)
_QUOTED_MAPPING_RE = re.compile(
    r"(?i)([\"'])("
    r"(?:[A-Z0-9_-]*(?:API[_-]?KEY|ACCESS[_-]?KEY|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|"
    r"BASE[_-]?URL|CLIENT[_-]?SECRET|CREDENTIALS?|DATABASE[_-]?URL|DB[_-]?URL|PASSWORD|"
    r"PASSWD|PRIVATE[_-]?KEY|REFRESH[_-]?TOKEN|SECRET))|"
    r"(?:AUTHORIZATION|COOKIE|TOKEN)"
    r")\1(\s*:\s*)([\"'])(.*?)\4"
)


def is_sensitive_key(key: Any) -> bool:
    """Return whether a mapping key conventionally contains a credential."""

    normalized = str(key).strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_EXACT_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def redact_sensitive_text(value: str) -> str:
    """Redact credentials embedded in command-like or header-like text."""

    value = _QUOTED_MAPPING_RE.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}{match.group(1)}"
            f"{match.group(3)}{match.group(4)}{REDACTED}{match.group(4)}"
        ),
        value,
    )
    value = _ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value)
    value = _BEARER_RE.sub(f"Bearer {REDACTED}", value)
    return _URL_USERINFO_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}:{REDACTED}@", value)


def redact_sensitive_data(value: Any, *, _parent_key: Any = None) -> Any:
    """Return a recursively redacted copy suitable for logs and diagnostics.

    The original object is never mutated. Keys such as ``api_key``, ``db_url``
    and ``*_token`` redact their entire value; credentials embedded in strings
    are also removed. Operational fields such as ``max_tokens`` remain visible.
    """

    if is_sensitive_key(_parent_key):
        return REDACTED if value is not None else None
    if isinstance(value, Mapping):
        return {
            key: redact_sensitive_data(item, _parent_key=key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, set):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if hasattr(value, "model_dump"):
        return redact_sensitive_data(value.model_dump())
    return value
