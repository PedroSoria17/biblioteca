from __future__ import annotations

import bcrypt
import pytest

from conftest import ADMIN_ID, INACTIVE_ID, USER_ID, FakeUniqueViolation


NEW_USER = {
    "nombre_completo": "  Ana Torres  ",
    "email": "  Ana.Torres@Example.COM ",
    "password": "NuevaClave123!",
}


def _stored(user_db, usuario_id):
    return user_db.users[usuario_id]


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------

def test_create_user_defaults_to_active_user(client, admin_headers, user_db):
    response = client.post("/users", json=NEW_USER, headers=admin_headers)

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["nombre_completo"] == "Ana Torres"
    # Same normalization as Login's /register and /login.
    assert data["email"] == "ana.torres@example.com"
    assert data["role_id"] == 1
    assert data["role"] == "USER"
    assert data["activo"] is True
    assert "password" not in str(response.get_json())

    stored = _stored(user_db, data["usuario_id"])
    assert stored["password_hash"] != NEW_USER["password"]
    assert bcrypt.checkpw(NEW_USER["password"].encode(), stored["password_hash"].encode())
    assert stored["es_administrador"] is False


def test_create_inactive_user(client, admin_headers):
    response = client.post("/users", json={**NEW_USER, "activo": False}, headers=admin_headers)

    assert response.status_code == 201
    assert response.get_json()["data"]["activo"] is False


def test_create_admin_when_admin_exists_returns_409(client, admin_headers, user_db):
    response = client.post("/users", json={**NEW_USER, "role_id": 2}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ADMIN_ALREADY_EXISTS"
    assert len(user_db.users) == 3


def test_create_inactive_admin_returns_409(client, admin_headers):
    response = client.post("/users", json={**NEW_USER, "role_id": 2, "activo": False}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ADMIN_MUST_BE_ACTIVE"


@pytest.mark.parametrize("email", ["user@example.com", "USER@Example.com", " user@example.com "])
def test_create_with_duplicate_email_returns_409(client, admin_headers, email, user_db):
    response = client.post("/users", json={**NEW_USER, "email": email}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "EMAIL_ALREADY_EXISTS"
    assert len(user_db.users) == 3


def test_unique_violation_race_is_409_not_500(client, admin_headers, user_db, monkeypatch):
    from repositories import user_repository

    # Pre-check passes (another request inserts the same email right after),
    # then the UNIQUE constraint fires.
    monkeypatch.setattr(user_repository, "email_taken", lambda *_a, **_k: False)

    response = client.post("/users", json={**NEW_USER, "email": "user@example.com"}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "EMAIL_ALREADY_EXISTS"


def test_admin_unique_index_race_is_409_not_500(client, admin_headers, monkeypatch):
    from repositories import user_repository

    monkeypatch.setattr(user_repository, "admin_exists", lambda *_a, **_k: False)

    response = client.post("/users", json={**NEW_USER, "role_id": 2}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ADMIN_ALREADY_EXISTS"


@pytest.mark.parametrize("role_id", [99, 3])
def test_create_with_unknown_role_returns_400(client, admin_headers, role_id):
    response = client.post("/users", json={**NEW_USER, "role_id": role_id}, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_ROLE"


@pytest.mark.parametrize("role_id", ["2", True, 0, -1, 1.5, None])
def test_create_with_malformed_role_returns_400(client, admin_headers, role_id):
    response = client.post("/users", json={**NEW_USER, "role_id": role_id}, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("password", ["short", "", "        ", 12345678, None, "ñ" * 37])
def test_create_with_invalid_password_returns_400(client, admin_headers, password, user_db):
    response = client.post("/users", json={**NEW_USER, "password": password}, headers=admin_headers)

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert "password" in body["message"]
    assert len(user_db.users) == 3


def test_password_error_never_echoes_the_password(client, admin_headers):
    secret = "abc"  # too short
    response = client.post("/users", json={**NEW_USER, "password": secret}, headers=admin_headers)

    assert secret not in response.get_json()["message"].replace("characters", "")


@pytest.mark.parametrize("email", ["", "no-at-sign", "a@b", "a b@example.com", 42, "x" * 250 + "@example.com"])
def test_create_with_invalid_email_returns_400(client, admin_headers, email):
    response = client.post("/users", json={**NEW_USER, "email": email}, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"


@pytest.mark.parametrize("nombre", ["", "   ", None, 7, "x" * 151])
def test_create_with_invalid_name_returns_400(client, admin_headers, nombre):
    response = client.post("/users", json={**NEW_USER, "nombre_completo": nombre}, headers=admin_headers)

    assert response.status_code == 400


@pytest.mark.parametrize("missing", ["nombre_completo", "email", "password"])
def test_create_missing_required_field_returns_400(client, admin_headers, missing):
    body = {k: v for k, v in NEW_USER.items() if k != missing}

    response = client.post("/users", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert missing in response.get_json()["message"]


def test_create_with_unknown_fields_returns_400(client, admin_headers):
    response = client.post("/users", json={**NEW_USER, "telefono": "1", "foo": 2}, headers=admin_headers)

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "UNKNOWN_FIELDS"
    assert body["details"] == {"fields": ["foo", "telefono"]}


@pytest.mark.parametrize(
    "field,value",
    [
        ("password_hash", "$2b$12$abcdefghijklmnopqrstuuvwxyzABCDEFGHIJKLMNOPQRSTUVWXY"),
        ("es_administrador", True),
        ("fecha_registro", "2020-01-01"),
        ("usuario_id", 50),
    ],
)
def test_create_with_server_managed_field_returns_400(client, admin_headers, user_db, field, value):
    response = client.post("/users", json={**NEW_USER, field: value}, headers=admin_headers)

    assert response.status_code == 400
    body = response.get_json()
    assert body["code"] == "FIELDS_NOT_ALLOWED"
    assert body["details"] == {"fields": [field]}
    assert len(user_db.users) == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "not json", "content_type": "application/json"},
        {"data": "nombre_completo=x", "content_type": "application/x-www-form-urlencoded"},
        {"json": ["a", "list"]},
        {},
    ],
)
def test_create_with_non_object_body_returns_400(client, admin_headers, kwargs):
    response = client.post("/users", headers=admin_headers, **kwargs)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_INPUT"


# ---------------------------------------------------------------------------
# PUT /users/<id>
# ---------------------------------------------------------------------------

def test_put_replaces_all_administrative_fields(client, admin_headers, user_db):
    old_hash = _stored(user_db, USER_ID)["password_hash"]
    body = {"nombre_completo": "Nuevo Nombre", "email": "Nuevo@Example.com", "role_id": 1, "activo": False}

    response = client.put(f"/users/{USER_ID}", json=body, headers=admin_headers)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["nombre_completo"] == "Nuevo Nombre"
    assert data["email"] == "nuevo@example.com"
    assert data["activo"] is False
    # PUT without password keeps the current hash.
    assert _stored(user_db, USER_ID)["password_hash"] == old_hash


def test_put_with_password_replaces_hash(client, admin_headers, user_db):
    body = {
        "nombre_completo": "User 2",
        "email": "user@example.com",
        "role_id": 1,
        "activo": True,
        "password": "OtraClave456!",
    }

    response = client.put(f"/users/{USER_ID}", json=body, headers=admin_headers)

    assert response.status_code == 200
    stored_hash = _stored(user_db, USER_ID)["password_hash"].encode()
    assert bcrypt.checkpw(b"OtraClave456!", stored_hash)
    assert not bcrypt.checkpw(b"PasswordSeguro123!", stored_hash)


@pytest.mark.parametrize("missing", ["nombre_completo", "email", "role_id", "activo"])
def test_put_requires_every_administrative_field(client, admin_headers, missing):
    body = {"nombre_completo": "N", "email": "n@example.com", "role_id": 1, "activo": True}
    body.pop(missing)

    response = client.put(f"/users/{USER_ID}", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert missing in response.get_json()["message"]


def test_put_unknown_user_returns_404(client, admin_headers):
    body = {"nombre_completo": "N", "email": "n@example.com", "role_id": 1, "activo": True}

    response = client.put("/users/999", json=body, headers=admin_headers)

    assert response.status_code == 404


def test_put_rejects_server_managed_fields(client, admin_headers):
    body = {"nombre_completo": "N", "email": "n@example.com", "role_id": 1, "activo": True, "fecha_registro": "x"}

    response = client.put(f"/users/{USER_ID}", json=body, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "FIELDS_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# PATCH /users/<id>
# ---------------------------------------------------------------------------

def test_patch_name_only_changes_name(client, admin_headers, user_db):
    before = dict(_stored(user_db, USER_ID))

    response = client.patch(f"/users/{USER_ID}", json={"nombre_completo": "Solo Nombre"}, headers=admin_headers)

    assert response.status_code == 200
    after = _stored(user_db, USER_ID)
    assert after["nombre_completo"] == "Solo Nombre"
    for field in ("email", "password_hash", "role_id", "es_administrador", "activo", "fecha_registro"):
        assert after[field] == before[field], field


def test_patch_activo_false_does_not_touch_other_fields(client, admin_headers, user_db):
    before = dict(_stored(user_db, USER_ID))

    response = client.patch(f"/users/{USER_ID}", json={"activo": False}, headers=admin_headers)

    assert response.status_code == 200
    after = _stored(user_db, USER_ID)
    assert after["activo"] is False
    assert {k: v for k, v in after.items() if k != "activo"} == {k: v for k, v in before.items() if k != "activo"}


def test_patch_reactivates_user(client, admin_headers, user_db):
    response = client.patch(f"/users/{INACTIVE_ID}", json={"activo": True}, headers=admin_headers)

    assert response.status_code == 200
    assert _stored(user_db, INACTIVE_ID)["activo"] is True


def test_patch_email(client, admin_headers, user_db):
    response = client.patch(f"/users/{USER_ID}", json={"email": "Cambiado@Example.com"}, headers=admin_headers)

    assert response.status_code == 200
    assert _stored(user_db, USER_ID)["email"] == "cambiado@example.com"


def test_patch_same_email_with_other_case_is_not_a_conflict(client, admin_headers):
    response = client.patch(f"/users/{USER_ID}", json={"email": "USER@example.com"}, headers=admin_headers)

    assert response.status_code == 200


def test_patch_duplicate_email_returns_409(client, admin_headers, user_db):
    response = client.patch(f"/users/{USER_ID}", json={"email": "Admin@Example.com"}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "EMAIL_ALREADY_EXISTS"
    assert _stored(user_db, USER_ID)["email"] == "user@example.com"


def test_patch_password_only_replaces_hash(client, admin_headers, user_db):
    before = dict(_stored(user_db, USER_ID))

    response = client.patch(f"/users/{USER_ID}", json={"password": "CambioDeClave789"}, headers=admin_headers)

    assert response.status_code == 200
    assert "password" not in str(response.get_json())
    after = _stored(user_db, USER_ID)
    assert bcrypt.checkpw(b"CambioDeClave789", after["password_hash"].encode())
    assert {k: v for k, v in after.items() if k != "password_hash"} == {
        k: v for k, v in before.items() if k != "password_hash"
    }


def test_patch_invalid_password_returns_400_and_keeps_hash(client, admin_headers, user_db):
    old_hash = _stored(user_db, USER_ID)["password_hash"]

    response = client.patch(f"/users/{USER_ID}", json={"password": "corta"}, headers=admin_headers)

    assert response.status_code == 400
    assert _stored(user_db, USER_ID)["password_hash"] == old_hash


def test_patch_role_to_admin_when_admin_exists_returns_409(client, admin_headers, user_db):
    response = client.patch(f"/users/{USER_ID}", json={"role_id": 2}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ADMIN_ALREADY_EXISTS"
    assert _stored(user_db, USER_ID)["role_id"] == 1


def test_patch_role_to_admin_when_no_admin_exists(client, make_token, user_db):
    # Simulates a database without an ADMIN row (e.g. after a manual fix).
    # The caller's token still says ADMIN, which is all require_roles checks.
    user_db.users[ADMIN_ID].update(role_id=1, es_administrador=False)
    headers = {"Authorization": f"Bearer {make_token(ADMIN_ID, 2).token}"}

    response = client.patch(f"/users/{USER_ID}", json={"role_id": 2}, headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"]["role"] == "ADMIN"
    stored = _stored(user_db, USER_ID)
    # Only role_id was written; es_administrador came from the trigger.
    assert stored["role_id"] == 2
    assert stored["es_administrador"] is True


def test_patch_inactive_user_to_admin_returns_409(client, make_token, user_db):
    user_db.users[ADMIN_ID].update(role_id=1, es_administrador=False)
    headers = {"Authorization": f"Bearer {make_token(ADMIN_ID, 2).token}"}

    response = client.patch(f"/users/{INACTIVE_ID}", json={"role_id": 2}, headers=headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "ADMIN_MUST_BE_ACTIVE"


def test_patch_role_to_unknown_role_returns_400(client, admin_headers):
    response = client.patch(f"/users/{USER_ID}", json={"role_id": 7}, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_ROLE"


def test_patch_empty_body_returns_400(client, admin_headers):
    response = client.patch(f"/users/{USER_ID}", json={}, headers=admin_headers)

    assert response.status_code == 400


def test_patch_null_value_returns_400(client, admin_headers):
    response = client.patch(f"/users/{USER_ID}", json={"activo": None}, headers=admin_headers)

    assert response.status_code == 400


@pytest.mark.parametrize("field", ["password_hash", "es_administrador", "fecha_registro", "usuario_id"])
def test_patch_server_managed_fields_returns_400(client, admin_headers, user_db, field):
    before = dict(_stored(user_db, USER_ID))

    response = client.patch(f"/users/{USER_ID}", json={field: True}, headers=admin_headers)

    assert response.status_code == 400
    assert response.get_json()["code"] == "FIELDS_NOT_ALLOWED"
    assert _stored(user_db, USER_ID) == before


def test_patch_unknown_user_returns_404(client, admin_headers):
    response = client.patch("/users/999", json={"activo": False}, headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "USER_NOT_FOUND"


def test_failed_update_rolls_back_the_transaction(client, admin_headers, user_db, monkeypatch):
    from repositories import user_repository

    def broken_update(_conn, usuario_id, changes):
        user_db.users[usuario_id].update(changes)  # partial write...
        raise FakeUniqueViolation("duplicate key", "usuarios_email_key")  # ...then failure

    monkeypatch.setattr(user_repository, "update_user", broken_update)

    response = client.patch(f"/users/{USER_ID}", json={"nombre_completo": "X"}, headers=admin_headers)

    assert response.status_code == 409
    assert _stored(user_db, USER_ID)["nombre_completo"] == "User 2"
    assert user_db.rollbacks == 1
