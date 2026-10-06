"""
Redis-backed security state: JWT revocation, refresh tokens and sessions.

All of it goes through the CRITICAL RedisGateway operations: if Redis is
unavailable the operation fails (RedisUnavailableError / 503), it never
silently succeeds.
"""

from __future__ import annotations

import json
import logging
from typing import Any
import uuid

from library_shared import keys
from library_shared.errors import RedisUnavailableError, auth_backend_unavailable, token_revoked
from library_shared.jwt_tokens import TOKEN_TYPE_ACCESS, TOKEN_TYPE_REFRESH, TokenClaims, decode_token
from library_shared.redaction import mask_secret
from library_shared.redis_client import RedisGateway, require_ttl, ttl_until
from library_shared.settings import JwtSettings


logger = logging.getLogger("library_shared.token_store")


# ----------------------------------------------------------------------
# Access token revocation: jwt:revoked:<jti>
# ----------------------------------------------------------------------

def revoke_token(gateway: RedisGateway, claims: TokenClaims) -> None:
    """The key expires together with the token: no need to keep it longer."""
    gateway.set(keys.revoked_jwt_key(claims.jti), "1", ttl_until(claims.expires_at))
    logger.info("Revoked %s token jti=%s", claims.token_type, mask_secret(claims.jti))


def is_token_revoked(gateway: RedisGateway, jti: str) -> bool:
    return gateway.exists(keys.revoked_jwt_key(jti))


def authenticate_access_token(token: str, settings: JwtSettings, gateway: RedisGateway) -> TokenClaims:
    """
    Full validation used by every protected endpoint: signature, HS256,
    expiry, claims, type == access, and revocation in Redis.

    Redis down -> 503 (fail closed); revoked -> 401.
    """
    claims = decode_token(token, settings, TOKEN_TYPE_ACCESS)

    try:
        revoked = is_token_revoked(gateway, claims.jti)
    except RedisUnavailableError as exc:
        logger.error("Cannot verify token revocation: Redis unavailable")
        raise auth_backend_unavailable() from exc

    if revoked:
        raise token_revoked()

    return claims


# ----------------------------------------------------------------------
# Refresh tokens: auth:refresh:<jti>
# ----------------------------------------------------------------------

def store_refresh_token(gateway: RedisGateway, claims: TokenClaims) -> None:
    if claims.token_type != TOKEN_TYPE_REFRESH:
        raise ValueError("Only refresh tokens can be stored as refresh tokens.")
    value = json.dumps({"user_id": claims.user_id, "role_id": claims.role_id, "sid": claims.session_id})
    gateway.set(keys.refresh_token_key(claims.jti), value, ttl_until(claims.expires_at))


def consume_refresh_token(gateway: RedisGateway, claims: TokenClaims) -> dict[str, Any]:
    """
    Atomically removes the stored refresh token and returns its data. A
    second use of the same token (replay, or already rotated/revoked)
    finds nothing and raises 401. Callers then issue a NEW pair and store
    the new refresh token (rotation).
    """
    try:
        raw = gateway.pop(keys.refresh_token_key(claims.jti))
    except RedisUnavailableError as exc:
        raise auth_backend_unavailable() from exc

    if raw is None:
        raise token_revoked()

    data = json.loads(raw)
    if data.get("user_id") != claims.user_id:
        raise token_revoked()
    return data


def revoke_refresh_token(gateway: RedisGateway, jti: str) -> None:
    gateway.delete(keys.refresh_token_key(jti))


# ----------------------------------------------------------------------
# Sessions: auth:session:<session_id>
# ----------------------------------------------------------------------

def new_session_id() -> str:
    return uuid.uuid4().hex


def store_session(gateway: RedisGateway, session_id: str, data: dict[str, Any], ttl_seconds: int) -> None:
    gateway.set(keys.session_key(session_id), json.dumps(data), require_ttl(ttl_seconds))


def get_session(gateway: RedisGateway, session_id: str) -> dict[str, Any] | None:
    raw = gateway.get(keys.session_key(session_id))
    return json.loads(raw) if raw is not None else None


def delete_session(gateway: RedisGateway, session_id: str) -> None:
    gateway.delete(keys.session_key(session_id))
