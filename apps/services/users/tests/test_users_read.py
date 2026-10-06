from __future__ import annotations

import pytest

from conftest import ADMIN_ID, USER_ID, bearer


def _assert_no_secrets(payload) -> None:
    text = str(payload)
    assert "password_hash" not in text
    assert "password" not in text
    assert "$2b$" not in text


def test_list_users_returns_all_without_password_hash(client, admin_headers, user_db):
    response = client.get("/users", headers=admin_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert [u["usuario_id"] for u in body["data"]] == [1, 2, 3]
    assert body["pagination"] == {"limit": 50, "offset": 0, "total": 3}
    assert body["data"][0] == {
        "usuario_id": 1,
        "nombre_completo": "User 1",
        "email": "admin@example.com",
        "role_id": 2,
        "role": "ADMIN",
        "activo": True,
        "fecha_registro": "2026-01-01T00:00:00+00:00",
    }
    _assert_no_secrets(body)


def test_list_users_pagination(client, admin_headers):
    response = client.get("/users?limit=1&offset=1", headers=admin_headers)

    body = response.get_json()
    assert [u["usuario_id"] for u in body["data"]] == [2]
    assert body["pagination"] == {"limit": 1, "offset": 1, "total": 3}


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=abc", "offset=-1"])
def test_list_users_invalid_pagination_returns_400(client, admin_headers, query):
    response = client.get(f"/users?{query}", headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"


def test_get_existing_user(client, admin_headers):
    response = client.get(f"/users/{USER_ID}", headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["usuario_id"] == USER_ID
    assert data["email"] == "user@example.com"
    assert data["role"] == "USER"
    _assert_no_secrets(data)


def test_get_unknown_user_returns_404(client, admin_headers):
    response = client.get("/users/999", headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json() == {"success": False, "code": "USER_NOT_FOUND", "message": "User not found."}


def test_non_numeric_user_id_is_404_json(client, admin_headers):
    response = client.get("/users/abc", headers=admin_headers)

    assert response.status_code == 404
    assert response.is_json


def test_users_me_returns_the_token_user(client, user_headers):
    response = client.get("/users/me", headers=user_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["usuario_id"] == USER_ID
    assert data["email"] == "user@example.com"
    _assert_no_secrets(response.get_json())


def test_users_me_for_admin(client, admin_headers):
    data = client.get("/users/me", headers=admin_headers).get_json()["data"]

    assert data["usuario_id"] == ADMIN_ID
    assert data["role_id"] == 2


def test_users_me_ignores_any_identity_in_the_request(client, user_headers):
    response = client.get(f"/users/me?usuario_id={ADMIN_ID}&user_id={ADMIN_ID}", headers=user_headers)

    assert response.get_json()["data"]["usuario_id"] == USER_ID


def test_users_me_for_deleted_user_returns_404(client, make_token):
    response = client.get("/users/me", headers=bearer(make_token(999, 1)))

    assert response.status_code == 404
    assert response.get_json()["code"] == "USER_NOT_FOUND"


def test_unknown_route_and_wrong_method_are_json(client, admin_headers):
    assert client.get("/nope").is_json
    response = client.post("/users/me", headers=admin_headers)
    assert response.status_code == 405
    assert response.is_json


def test_database_down_returns_503_without_leaking_details(client, admin_headers, user_db):
    user_db.down = True

    response = client.get("/users", headers=admin_headers)

    assert response.status_code == 503
    assert response.get_json()["code"] == "DATABASE_UNAVAILABLE"
    assert "db-test-password" not in response.get_data(as_text=True)
