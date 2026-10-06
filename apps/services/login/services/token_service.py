"""
Session lifecycle of the login microservice: login -> refresh (rotation)
-> logout (revocation).

Everything JWT/Redis related is delegated to library_shared
(apps/services/shared); this module only decides WHAT is issued, stored
and revoked, and in which order.

Redis keys (see library_shared.keys):
  auth:session:<sid>    user_id, role_id, email, created_at, refreshed_at,
                        refresh_jti (the only refresh token currently valid
                        for that session). TTL = refresh token TTL.
  auth:refresh:<jti>    {"user_id", "role_id", "sid"}. TTL = until refresh exp.
  jwt:revoked:<jti>     revoked access token. TTL = until access exp.

No password, password hash or encoded token is ever stored in Redis.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from library_shared.errors import RedisUnavailableError, invalid_token, token_revoked
from library_shared.jwt_tokens import (
    TOKEN_TYPE_REFRESH,
    IssuedToken,
    TokenClaims,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from library_shared.redaction import mask_secret
from library_shared.redis_client import RedisGateway
from library_shared.settings import JwtSettings
from library_shared.token_store import (
    consume_refresh_token,
    delete_session,
    get_session,
    new_session_id,
    revoke_refresh_token,
    revoke_token,
    store_refresh_token,
    store_session,
)

from services import auth_service


logger = logging.getLogger("login_microservice.tokens")


def _issue_pair(settings: JwtSettings, user: dict, sid: str) -> tuple[IssuedToken, IssuedToken]:
    access = create_access_token(settings, user["id"], user["role_id"], session_id=sid)
    refresh = create_refresh_token(settings, user["id"], user["role_id"], session_id=sid)
    return access, refresh


def _token_payload(access: IssuedToken, refresh: IssuedToken) -> dict[str, Any]:
    return {
        "access_token": access.token,
        "refresh_token": refresh.token,
        "token_type": "Bearer",
        "expires_in": access.claims.expires_at - access.claims.issued_at,
        "refresh_expires_in": refresh.claims.expires_at - refresh.claims.issued_at,
    }


def start_session(user: dict, settings: JwtSettings, gateway: RedisGateway) -> dict[str, Any]:
    """
    Called after the credentials were validated against PostgreSQL. Tokens
    are returned ONLY once both the session and the refresh token are
    stored; if Redis fails, RedisUnavailableError propagates (-> 503) and
    nothing usable is handed to the client.
    """
    sid = new_session_id()
    access, refresh = _issue_pair(settings, user, sid)
    now = int(time.time())

    session_data = {
        "user_id": user["id"],
        "role_id": user["role_id"],
        "email": user["email"],
        "created_at": now,
        "refreshed_at": now,
        "refresh_jti": refresh.claims.jti,
    }

    try:
        store_session(gateway, sid, session_data, settings.refresh_ttl_seconds)
        store_refresh_token(gateway, refresh.claims)
    except RedisUnavailableError:
        _discard_session_quietly(gateway, sid)
        raise

    logger.info("Session started user_id=%s sid=%s", user["id"], mask_secret(sid))
    return _token_payload(access, refresh)


def refresh_session(refresh_token: str, settings: JwtSettings, gateway: RedisGateway) -> dict[str, Any]:
    """
    Rotation: the presented refresh token is consumed atomically
    (RedisGateway.pop via consume_refresh_token), so only ONE request can
    ever succeed with it; a second or concurrent use gets 401. The new pair
    carries the role_id CURRENTLY stored in PostgreSQL, not the old claim.

    The session and the user are checked BEFORE consuming the token, so a
    PostgreSQL outage does not burn the client's refresh token. The pop is
    still the single gate: concurrent requests may all pass the checks,
    but only one of them gets the token out of Redis.
    """
    claims = decode_token(refresh_token, settings, TOKEN_TYPE_REFRESH)  # 401 on any JWT problem
    sid = claims.session_id
    if not sid:
        raise invalid_token()

    session = get_session(gateway, sid)  # RedisUnavailableError -> 503
    if (
        session is None
        or session.get("user_id") != claims.user_id
        or session.get("refresh_jti") != claims.jti
    ):
        raise token_revoked()

    user = auth_service.get_active_user(claims.user_id)
    if user is None:
        # Deleted or deactivated since login: end the session for good.
        revoke_refresh_token(gateway, claims.jti)
        delete_session(gateway, sid)
        logger.info("Refresh denied for inactive user_id=%s sid=%s", claims.user_id, mask_secret(sid))
        raise token_revoked()

    stored = consume_refresh_token(gateway, claims)  # atomic; 401 reused/revoked, 503 Redis down
    if stored.get("sid") != sid:
        raise token_revoked()

    access, refresh = _issue_pair(settings, user, sid)
    store_refresh_token(gateway, refresh.claims)

    session.update(
        role_id=user["role_id"],
        email=user["email"],
        refreshed_at=int(time.time()),
        refresh_jti=refresh.claims.jti,
    )
    store_session(gateway, sid, session, settings.refresh_ttl_seconds)

    logger.info("Session refreshed user_id=%s sid=%s", user["id"], mask_secret(sid))
    return {**_token_payload(access, refresh), "user": user}


def end_session(claims: TokenClaims, gateway: RedisGateway) -> None:
    """
    Logout with an already validated access token: revoke that access token
    (jwt:revoked:<jti>, TTL = its remaining life), then drop the session
    and its current refresh token.
    """
    revoke_token(gateway, claims)

    sid = claims.session_id
    if sid:
        session = get_session(gateway, sid)
        if session and session.get("refresh_jti"):
            revoke_refresh_token(gateway, session["refresh_jti"])
        delete_session(gateway, sid)

    logger.info("Session ended user_id=%s sid=%s", claims.user_id, mask_secret(sid))


def describe_session(claims: TokenClaims, gateway: RedisGateway) -> dict[str, Any]:
    """GET /session for a valid access token whose session must still exist."""
    session = get_session(gateway, claims.session_id) if claims.session_id else None
    if session is None or session.get("user_id") != claims.user_id:
        raise token_revoked()

    return {"id": claims.user_id, "email": session.get("email"), "role_id": claims.role_id}


def _discard_session_quietly(gateway: RedisGateway, sid: str) -> None:
    try:
        delete_session(gateway, sid)
    except RedisUnavailableError:
        # No token was handed out, so a leftover session key is unusable
        # and expires on its own TTL.
        pass
