"""
JWT creation and validation (PyJWT).

Rules enforced here, never configurable by the token itself:
- signature algorithm is always HS256 (the header `alg` is checked
  explicitly and also pinned in jwt.decode(algorithms=[...]));
- user_id, role_id, jti, iat, exp and type are mandatory;
- `type` distinguishes access from refresh tokens, so a refresh token can
  never be used where an access token is expected (and vice versa).

Revocation lives in library_shared.token_store because it needs Redis.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
import uuid

import jwt

from library_shared.errors import invalid_token, token_expired
from library_shared.settings import JwtSettings


ALGORITHM = "HS256"
TOKEN_TYPE_CLAIM = "type"
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
SESSION_ID_CLAIM = "sid"

REQUIRED_CLAIMS = ("user_id", "role_id", "jti", "iat", "exp", TOKEN_TYPE_CLAIM)
MAX_JTI_LENGTH = 128


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    role_id: int
    jti: str
    token_type: str
    issued_at: int
    expires_at: int
    session_id: str | None = None


@dataclass(frozen=True)
class IssuedToken:
    token: str
    claims: TokenClaims

    def __repr__(self) -> str:
        # The encoded token is a credential: keep it out of logs/tracebacks.
        return f"IssuedToken(token='***', claims={self.claims!r})"


def new_jti() -> str:
    return uuid.uuid4().hex


def _is_positive_int(value: object) -> bool:
    # bool is a subclass of int: True must not be accepted as user_id=1.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _issue(
    settings: JwtSettings,
    token_type: str,
    ttl_seconds: int,
    user_id: int,
    role_id: int,
    session_id: str | None,
    now: int | None,
) -> IssuedToken:
    if not _is_positive_int(user_id) or not _is_positive_int(role_id):
        raise ValueError("user_id and role_id must be positive integers.")

    issued_at = int(time.time()) if now is None else int(now)
    claims = TokenClaims(
        user_id=user_id,
        role_id=role_id,
        jti=new_jti(),
        token_type=token_type,
        issued_at=issued_at,
        expires_at=issued_at + ttl_seconds,
        session_id=session_id,
    )

    payload: dict[str, object] = {
        "user_id": claims.user_id,
        "role_id": claims.role_id,
        "jti": claims.jti,
        "iat": claims.issued_at,
        "exp": claims.expires_at,
        TOKEN_TYPE_CLAIM: claims.token_type,
    }
    if session_id:
        payload[SESSION_ID_CLAIM] = session_id

    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return IssuedToken(token=token, claims=claims)


def create_access_token(
    settings: JwtSettings,
    user_id: int,
    role_id: int,
    *,
    session_id: str | None = None,
    now: int | None = None,
) -> IssuedToken:
    return _issue(settings, TOKEN_TYPE_ACCESS, settings.access_ttl_seconds, user_id, role_id, session_id, now)


def create_refresh_token(
    settings: JwtSettings,
    user_id: int,
    role_id: int,
    *,
    session_id: str | None = None,
    now: int | None = None,
) -> IssuedToken:
    return _issue(settings, TOKEN_TYPE_REFRESH, settings.refresh_ttl_seconds, user_id, role_id, session_id, now)


def decode_token(token: str, settings: JwtSettings, expected_type: str) -> TokenClaims:
    """
    Verifies signature, algorithm, expiry, required claims and token type.
    Raises AuthError (401) on any problem. Does NOT check revocation.
    """
    if not isinstance(token, str) or not token.strip():
        raise invalid_token()

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise invalid_token() from exc

    # Explicit check on top of algorithms=[ALGORITHM] below: the algorithm
    # is decided by this service, never by what the token claims to use.
    if header.get("alg") != ALGORITHM:
        raise invalid_token()

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": list(REQUIRED_CLAIMS), "verify_signature": True, "verify_exp": True},
        )
    except jwt.ExpiredSignatureError as exc:
        raise token_expired() from exc
    except jwt.InvalidTokenError as exc:
        raise invalid_token() from exc

    return _claims_from_payload(payload, expected_type)


def _claims_from_payload(payload: dict, expected_type: str) -> TokenClaims:
    user_id = payload.get("user_id")
    role_id = payload.get("role_id")
    jti = payload.get("jti")
    token_type = payload.get(TOKEN_TYPE_CLAIM)
    session_id = payload.get(SESSION_ID_CLAIM)

    if not _is_positive_int(user_id) or not _is_positive_int(role_id):
        raise invalid_token()
    if not isinstance(jti, str) or not jti.strip() or len(jti) > MAX_JTI_LENGTH:
        raise invalid_token()
    if token_type != expected_type:
        raise invalid_token()
    if session_id is not None and not isinstance(session_id, str):
        raise invalid_token()

    return TokenClaims(
        user_id=user_id,
        role_id=role_id,
        jti=jti,
        token_type=token_type,
        issued_at=int(payload["iat"]),
        expires_at=int(payload["exp"]),
        session_id=session_id,
    )
