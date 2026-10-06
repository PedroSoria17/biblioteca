import time

import pytest

from library_shared import keys
from library_shared.errors import AuthError, RedisUnavailableError
from library_shared.jwt_tokens import create_access_token, create_refresh_token
from library_shared.roles import ROLE_USER
from library_shared.token_store import (
    authenticate_access_token,
    consume_refresh_token,
    delete_session,
    get_session,
    is_token_revoked,
    revoke_refresh_token,
    revoke_token,
    store_refresh_token,
    store_session,
)


def test_valid_access_token_is_authenticated(jwt_settings, gateway):
    issued = create_access_token(jwt_settings, user_id=3, role_id=ROLE_USER)

    claims = authenticate_access_token(issued.token, jwt_settings, gateway)

    assert claims.user_id == 3


def test_revoked_token_is_rejected_with_401(jwt_settings, gateway, fake_redis):
    issued = create_access_token(jwt_settings, user_id=3, role_id=ROLE_USER)
    revoke_token(gateway, issued.claims)

    key = f"jwt:revoked:{issued.claims.jti}"
    assert key in fake_redis.store
    # Revocation key lives exactly as long as the token could still be used.
    assert abs(fake_redis.ttls[key] - (issued.claims.expires_at - time.time())) <= 2

    with pytest.raises(AuthError) as exc_info:
        authenticate_access_token(issued.token, jwt_settings, gateway)

    assert exc_info.value.http_status == 401
    assert exc_info.value.code == "TOKEN_REVOKED"


def test_redis_down_fails_closed(jwt_settings, broken_gateway):
    issued = create_access_token(jwt_settings, user_id=3, role_id=ROLE_USER)

    with pytest.raises(AuthError) as exc_info:
        authenticate_access_token(issued.token, jwt_settings, broken_gateway)

    assert exc_info.value.http_status == 503
    assert exc_info.value.code == "AUTH_BACKEND_UNAVAILABLE"


def test_invalid_token_is_rejected_before_touching_redis(jwt_settings, broken_gateway):
    # A bad token is a 401 even when Redis is down: no need to ask Redis.
    with pytest.raises(AuthError) as exc_info:
        authenticate_access_token("garbage", jwt_settings, broken_gateway)

    assert exc_info.value.http_status == 401


def test_is_token_revoked_raises_when_redis_is_down(broken_gateway):
    with pytest.raises(RedisUnavailableError):
        is_token_revoked(broken_gateway, "jti")


def test_refresh_token_can_be_consumed_only_once(jwt_settings, gateway, fake_redis):
    refresh = create_refresh_token(jwt_settings, user_id=4, role_id=ROLE_USER, session_id="s1")
    store_refresh_token(gateway, refresh.claims)

    key = keys.refresh_token_key(refresh.claims.jti)
    assert fake_redis.ttls[key] > jwt_settings.access_ttl_seconds

    data = consume_refresh_token(gateway, refresh.claims)
    assert data == {"user_id": 4, "role_id": ROLE_USER, "sid": "s1"}

    with pytest.raises(AuthError) as exc_info:
        consume_refresh_token(gateway, refresh.claims)
    assert exc_info.value.http_status == 401


def test_revoked_refresh_token_cannot_be_consumed(jwt_settings, gateway):
    refresh = create_refresh_token(jwt_settings, user_id=4, role_id=ROLE_USER)
    store_refresh_token(gateway, refresh.claims)
    revoke_refresh_token(gateway, refresh.claims.jti)

    with pytest.raises(AuthError):
        consume_refresh_token(gateway, refresh.claims)


def test_consume_refresh_token_with_redis_down_is_503(jwt_settings, broken_gateway):
    refresh = create_refresh_token(jwt_settings, user_id=4, role_id=ROLE_USER)

    with pytest.raises(AuthError) as exc_info:
        consume_refresh_token(broken_gateway, refresh.claims)

    assert exc_info.value.http_status == 503


def test_access_token_cannot_be_stored_as_refresh(jwt_settings, gateway):
    access = create_access_token(jwt_settings, user_id=4, role_id=ROLE_USER)

    with pytest.raises(ValueError):
        store_refresh_token(gateway, access.claims)


def test_session_lifecycle(gateway, fake_redis):
    store_session(gateway, "abc", {"user_id": 1}, 3600)

    assert fake_redis.ttls["auth:session:abc"] == 3600
    assert get_session(gateway, "abc") == {"user_id": 1}

    delete_session(gateway, "abc")
    assert get_session(gateway, "abc") is None
