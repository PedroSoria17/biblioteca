import time

import jwt
import pytest

from library_shared.errors import AuthError
from library_shared.jwt_tokens import (
    ALGORITHM,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from library_shared.roles import ROLE_ADMIN, ROLE_USER


OTHER_SECRET = "another-unit-test-secret-key-long-enough-9876543210"


def _payload(**overrides):
    now = int(time.time())
    payload = {
        "user_id": 7,
        "role_id": ROLE_USER,
        "jti": "abc123",
        "iat": now,
        "exp": now + 600,
        "type": TOKEN_TYPE_ACCESS,
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


def _assert_401(exc_info, code="INVALID_TOKEN"):
    assert exc_info.value.http_status == 401
    assert exc_info.value.code == code


def test_valid_access_token_roundtrip(jwt_settings):
    issued = create_access_token(jwt_settings, user_id=7, role_id=ROLE_ADMIN, session_id="s1")

    claims = decode_token(issued.token, jwt_settings, TOKEN_TYPE_ACCESS)

    assert claims.user_id == 7
    assert claims.role_id == ROLE_ADMIN
    assert claims.session_id == "s1"
    assert claims.token_type == TOKEN_TYPE_ACCESS
    assert claims.jti == issued.claims.jti and len(claims.jti) == 32


def test_access_token_contains_required_claims_and_expires_in_20_minutes(jwt_settings):
    issued = create_access_token(jwt_settings, user_id=1, role_id=ROLE_USER)

    header = jwt.get_unverified_header(issued.token)
    payload = jwt.decode(issued.token, jwt_settings.secret_key, algorithms=[ALGORITHM])

    assert header["alg"] == "HS256"
    assert {"user_id", "role_id", "jti", "iat", "exp", "type"} <= payload.keys()
    assert payload["exp"] - payload["iat"] == 20 * 60
    assert payload["type"] == "access"


def test_refresh_token_lives_longer_and_has_its_own_jti(jwt_settings):
    access = create_access_token(jwt_settings, user_id=1, role_id=ROLE_USER)
    refresh = create_refresh_token(jwt_settings, user_id=1, role_id=ROLE_USER)

    assert refresh.claims.expires_at - refresh.claims.issued_at > access.claims.expires_at - access.claims.issued_at
    assert refresh.claims.jti != access.claims.jti
    assert decode_token(refresh.token, jwt_settings, TOKEN_TYPE_REFRESH).token_type == TOKEN_TYPE_REFRESH


def test_issued_token_repr_does_not_leak_token(jwt_settings):
    issued = create_access_token(jwt_settings, user_id=1, role_id=ROLE_USER)
    assert issued.token not in repr(issued)


def test_expired_token_is_rejected(jwt_settings):
    issued = create_access_token(jwt_settings, user_id=1, role_id=ROLE_USER, now=int(time.time()) - 3600)

    with pytest.raises(AuthError) as exc_info:
        decode_token(issued.token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info, "TOKEN_EXPIRED")


def test_wrong_signature_is_rejected(jwt_settings):
    token = jwt.encode(_payload(), OTHER_SECRET, algorithm="HS256")

    with pytest.raises(AuthError) as exc_info:
        decode_token(token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


def test_tampered_payload_is_rejected(jwt_settings):
    issued = create_access_token(jwt_settings, user_id=1, role_id=ROLE_USER)
    forged = jwt.encode(_payload(user_id=1, role_id=ROLE_ADMIN), "x" * 40, algorithm="HS256")
    header, _payload_part, signature = issued.token.split(".")
    tampered = ".".join([header, forged.split(".")[1], signature])

    with pytest.raises(AuthError) as exc_info:
        decode_token(tampered, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
@pytest.mark.parametrize("algorithm", ["HS512", "HS384"])
def test_other_hmac_algorithm_is_rejected_even_with_right_key(jwt_settings, algorithm):
    token = jwt.encode(_payload(), jwt_settings.secret_key, algorithm=algorithm)

    with pytest.raises(AuthError) as exc_info:
        decode_token(token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


def test_alg_none_is_rejected(jwt_settings):
    token = jwt.encode(_payload(), None, algorithm="none")

    with pytest.raises(AuthError) as exc_info:
        decode_token(token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


@pytest.mark.parametrize("missing", ["user_id", "role_id", "jti", "iat", "exp", "type"])
def test_missing_required_claim_is_rejected(jwt_settings, missing):
    payload = _payload()
    del payload[missing]
    token = jwt.encode(payload, jwt_settings.secret_key, algorithm="HS256")

    with pytest.raises(AuthError) as exc_info:
        decode_token(token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


@pytest.mark.parametrize(
    "overrides",
    [
        {"user_id": "7"},
        {"user_id": 0},
        {"user_id": True},
        {"role_id": -1},
        {"role_id": "2"},
        {"jti": ""},
        {"jti": 123},
        {"sid": 5},
    ],
)
def test_invalid_claim_values_are_rejected(jwt_settings, overrides):
    token = jwt.encode(_payload(**overrides), jwt_settings.secret_key, algorithm="HS256")

    with pytest.raises(AuthError) as exc_info:
        decode_token(token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


def test_refresh_token_cannot_be_used_as_access_token(jwt_settings):
    refresh = create_refresh_token(jwt_settings, user_id=1, role_id=ROLE_USER)

    with pytest.raises(AuthError) as exc_info:
        decode_token(refresh.token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


def test_access_token_cannot_be_used_as_refresh_token(jwt_settings):
    access = create_access_token(jwt_settings, user_id=1, role_id=ROLE_USER)

    with pytest.raises(AuthError) as exc_info:
        decode_token(access.token, jwt_settings, TOKEN_TYPE_REFRESH)

    _assert_401(exc_info)


@pytest.mark.parametrize("token", ["", "   ", "not-a-jwt", "a.b.c", None])
def test_malformed_token_is_rejected(jwt_settings, token):
    with pytest.raises(AuthError) as exc_info:
        decode_token(token, jwt_settings, TOKEN_TYPE_ACCESS)

    _assert_401(exc_info)


@pytest.mark.parametrize("user_id,role_id", [(0, 1), (1, 0), (True, 1), ("1", 1)])
def test_cannot_issue_token_with_invalid_ids(jwt_settings, user_id, role_id):
    with pytest.raises(ValueError):
        create_access_token(jwt_settings, user_id=user_id, role_id=role_id)
