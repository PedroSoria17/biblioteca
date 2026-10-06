"""Last-ADMIN protection and DELETE behavior (order history is preserved)."""

from __future__ import annotations

import pytest

from conftest import ADMIN_ID, INACTIVE_ID, USER_ID, FakeForeignKeyViolation


# ---------------------------------------------------------------------------
# Last ADMIN
# ---------------------------------------------------------------------------

def test_cannot_delete_last_admin(client, admin_headers, user_db):
    response = client.delete(f"/users/{ADMIN_ID}", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "LAST_ADMIN_REQUIRED"
    assert ADMIN_ID in user_db.users


def test_cannot_deactivate_last_admin(client, admin_headers, user_db):
    response = client.patch(f"/users/{ADMIN_ID}", json={"activo": False}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "LAST_ADMIN_REQUIRED"
    assert user_db.users[ADMIN_ID]["activo"] is True


def test_cannot_demote_last_admin_with_patch(client, admin_headers, user_db):
    response = client.patch(f"/users/{ADMIN_ID}", json={"role_id": 1}, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "LAST_ADMIN_REQUIRED"
    assert user_db.users[ADMIN_ID]["role_id"] == 2
    assert user_db.users[ADMIN_ID]["es_administrador"] is True


@pytest.mark.parametrize("role_id,activo", [(1, True), (2, False), (1, False)])
def test_cannot_demote_or_deactivate_last_admin_with_put(client, admin_headers, user_db, role_id, activo):
    body = {"nombre_completo": "Admin", "email": "admin@example.com", "role_id": role_id, "activo": activo}

    response = client.put(f"/users/{ADMIN_ID}", json=body, headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "LAST_ADMIN_REQUIRED"
    assert user_db.users[ADMIN_ID]["nombre_completo"] == "User 1"  # nothing applied


def test_admin_can_still_edit_own_profile_and_password(client, admin_headers, user_db):
    response = client.patch(
        f"/users/{ADMIN_ID}",
        json={"nombre_completo": "Administrador", "password": "AdminNueva123", "role_id": 2, "activo": True},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert user_db.users[ADMIN_ID]["nombre_completo"] == "Administrador"
    assert user_db.users[ADMIN_ID]["role_id"] == 2


def test_put_on_admin_keeping_role_and_active_is_allowed(client, admin_headers):
    body = {"nombre_completo": "Admin", "email": "admin@example.com", "role_id": 2, "activo": True}

    assert client.put(f"/users/{ADMIN_ID}", json=body, headers=admin_headers).status_code == 200


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

def test_delete_user_without_history(client, admin_headers, user_db):
    response = client.delete(f"/users/{INACTIVE_ID}", headers=admin_headers)

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": {"usuario_id": INACTIVE_ID, "deleted": True}}
    assert INACTIVE_ID not in user_db.users


def test_delete_unknown_user_returns_404(client, admin_headers):
    response = client.delete("/users/999", headers=admin_headers)

    assert response.status_code == 404
    assert response.get_json()["code"] == "USER_NOT_FOUND"


def test_delete_user_with_orders_returns_409_and_preserves_history(client, admin_headers, user_db):
    user_db.orders[USER_ID] = 2

    response = client.delete(f"/users/{USER_ID}", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "USER_HAS_ORDER_HISTORY"
    assert USER_ID in user_db.users
    assert user_db.orders[USER_ID] == 2


def test_user_with_orders_can_be_deactivated_instead(client, admin_headers, user_db):
    user_db.orders[USER_ID] = 1

    response = client.patch(f"/users/{USER_ID}", json={"activo": False}, headers=admin_headers)

    assert response.status_code == 200
    assert user_db.users[USER_ID]["activo"] is False
    assert user_db.orders[USER_ID] == 1


def test_delete_fk_violation_race_is_409_not_500(client, admin_headers, user_db, monkeypatch):
    from repositories import user_repository

    # An order is created between the explicit check and the DELETE:
    # fk_pedidos_usuario (ON DELETE RESTRICT) rejects it.
    monkeypatch.setattr(user_repository, "has_orders", lambda *_a, **_k: False)
    user_db.orders[USER_ID] = 1

    response = client.delete(f"/users/{USER_ID}", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "USER_HAS_ORDER_HISTORY"
    assert USER_ID in user_db.users


def test_delete_unknown_foreign_key_is_409_dependencies(client, admin_headers, monkeypatch):
    from repositories import user_repository

    def blocked(_conn, _usuario_id):
        raise FakeForeignKeyViolation("fk violation", "fk_some_future_table")

    monkeypatch.setattr(user_repository, "delete_user", blocked)

    response = client.delete(f"/users/{USER_ID}", headers=admin_headers)

    assert response.status_code == 409
    assert response.get_json()["code"] == "USER_HAS_DEPENDENCIES"
