import pytest
from flask import Flask, Response

from library_shared.errors import AuthError
from library_shared.flask_auth import current_claims, extract_bearer_token, init_auth, require_auth, require_roles
from library_shared.jwt_tokens import create_access_token, create_refresh_token
from library_shared.roles import ROLE_ADMIN, ROLE_USER
from library_shared.token_store import revoke_token


def _make_app(jwt_settings, gateway, error_renderer=None) -> Flask:
    app = Flask(__name__)
    init_auth(app, jwt_settings, gateway, error_renderer)

    @app.get("/me")
    @require_auth
    def me():
        return {"user_id": current_claims().user_id}

    @app.post("/admin")
    @require_roles(ROLE_ADMIN)
    def admin_only():
        return {"ok": True}

    return app


@pytest.fixture
def client(jwt_settings, gateway):
    return _make_app(jwt_settings, gateway).test_client()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_missing_authorization_header_is_401(client):
    resp = client.get("/me")

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "MISSING_TOKEN"
    assert resp.headers["WWW-Authenticate"].startswith("Bearer")


@pytest.mark.parametrize(
    "header",
    ["Basic dXNlcjpwYXNz", "Bearer", "Bearer   ", "Token abc", "Bearer a b", "abc"],
)
def test_malformed_authorization_header_is_401(client, header):
    resp = client.get("/me", headers={"Authorization": header})

    assert resp.status_code == 401


def test_valid_token_reaches_the_view(client, jwt_settings):
    token = create_access_token(jwt_settings, user_id=9, role_id=ROLE_USER).token

    resp = client.get("/me", headers=_bearer(token))

    assert resp.status_code == 200
    assert resp.get_json() == {"user_id": 9}


def test_bearer_scheme_is_case_insensitive(client, jwt_settings):
    token = create_access_token(jwt_settings, user_id=9, role_id=ROLE_USER).token

    assert client.get("/me", headers={"Authorization": f"bearer {token}"}).status_code == 200


def test_refresh_token_is_rejected_as_access_token(client, jwt_settings):
    token = create_refresh_token(jwt_settings, user_id=9, role_id=ROLE_ADMIN).token

    assert client.get("/me", headers=_bearer(token)).status_code == 401


def test_revoked_token_is_401(client, jwt_settings, gateway):
    issued = create_access_token(jwt_settings, user_id=9, role_id=ROLE_USER)
    revoke_token(gateway, issued.claims)

    resp = client.get("/me", headers=_bearer(issued.token))

    assert resp.status_code == 401
    assert resp.get_json()["code"] == "TOKEN_REVOKED"


def test_redis_down_never_grants_access(jwt_settings, broken_gateway):
    client = _make_app(jwt_settings, broken_gateway).test_client()
    token = create_access_token(jwt_settings, user_id=9, role_id=ROLE_ADMIN).token

    resp = client.post("/admin", headers=_bearer(token))

    assert resp.status_code == 503


def test_admin_role_is_authorized(client, jwt_settings):
    token = create_access_token(jwt_settings, user_id=1, role_id=ROLE_ADMIN).token

    assert client.post("/admin", headers=_bearer(token)).status_code == 200


def test_insufficient_role_is_403(client, jwt_settings):
    token = create_access_token(jwt_settings, user_id=2, role_id=ROLE_USER).token

    resp = client.post("/admin", headers=_bearer(token))

    assert resp.status_code == 403
    assert resp.get_json()["code"] == "FORBIDDEN"
    assert "WWW-Authenticate" not in resp.headers


def test_unauthenticated_request_to_role_protected_route_is_401_not_403(client):
    assert client.post("/admin").status_code == 401


def test_custom_error_renderer_keeps_service_format(jwt_settings, gateway):
    def xml_renderer(error: AuthError) -> Response:
        return Response(f"<error><code>{error.code}</code></error>", mimetype="application/xml")

    client = _make_app(jwt_settings, gateway, xml_renderer).test_client()
    resp = client.get("/me")

    assert resp.status_code == 401
    assert resp.mimetype == "application/xml"
    assert b"<code>MISSING_TOKEN</code>" in resp.data


def test_extract_bearer_token():
    assert extract_bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"
    with pytest.raises(AuthError) as exc_info:
        extract_bearer_token(None)
    assert exc_info.value.http_status == 401


def test_require_roles_needs_at_least_one_role():
    with pytest.raises(ValueError):
        require_roles()
