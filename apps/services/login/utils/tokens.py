from __future__ import annotations

import hashlib
import secrets

# 32 random bytes (~256 bits) url-safe encoded: enough entropy that
# guessing a valid verification token is infeasible.
TOKEN_BYTES = 32


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """
    Only this hash is ever stored in PostgreSQL; the plain token travels
    solely inside the verification email URL.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
