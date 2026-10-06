"""
Single source of truth for Redis key names, so every service builds (and
invalidates) exactly the same keys.
"""

from __future__ import annotations

from typing import Mapping
from urllib.parse import urlencode


REVOKED_JWT_PREFIX = "jwt:revoked:"
REFRESH_TOKEN_PREFIX = "auth:refresh:"
SESSION_PREFIX = "auth:session:"
BOOK_PREFIX = "books:"
BOOKS_LIST_PREFIX = "books:list:"
BOOKS_LIST_PATTERN = f"{BOOKS_LIST_PREFIX}*"


def _require_id(value: str, what: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError(f"{what} cannot be empty.")
    return value


def revoked_jwt_key(jti: str) -> str:
    return REVOKED_JWT_PREFIX + _require_id(jti, "jti")


def refresh_token_key(jti: str) -> str:
    return REFRESH_TOKEN_PREFIX + _require_id(jti, "jti")


def session_key(session_id: str) -> str:
    return SESSION_PREFIX + _require_id(session_id, "session_id")


def book_key(isbn: str) -> str:
    return BOOK_PREFIX + _require_id(isbn, "isbn")


def books_list_key(filters: Mapping[str, object] | None = None) -> str:
    """
    Normalizes filters so equivalent queries share one cache entry:
    keys lowercased and sorted, values stripped, empty values dropped.
    {"Titulo": " Dune ", "page": 1} -> "books:list:page=1&titulo=Dune"
    """
    normalized = sorted(
        (str(k).strip().lower(), str(v).strip())
        for k, v in (filters or {}).items()
        if v is not None and str(v).strip()
    )
    return BOOKS_LIST_PREFIX + (urlencode(normalized) if normalized else "all")
