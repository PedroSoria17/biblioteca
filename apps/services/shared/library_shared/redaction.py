"""Helpers to log identifiers without leaking secrets."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    """redis://:secret@host:6379/0 -> redis://:***@host:6379/0"""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid-url>"

    if parts.password is None and parts.username is None:
        return url

    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    user = parts.username or ""
    return urlunsplit((parts.scheme, f"{user}:***@{host}", parts.path, parts.query, parts.fragment))


def mask_secret(value: str | None, visible: int = 6) -> str:
    """
    Shows only a short prefix of a token/jti so log lines can be correlated
    without ever containing a usable credential.
    """
    if not value:
        return "<empty>"
    if len(value) <= visible:
        return "***"
    return f"{value[:visible]}***"
