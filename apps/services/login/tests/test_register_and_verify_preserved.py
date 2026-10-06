"""
Regression tests: /register and /verify-email keep their contract after the
JWT + Redis migration (they never depended on the Flask session).
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import pytest


@pytest.fixture
def register_db(monkeypatch):
    from repositories import user_repository
    from services import auth_service

    created = {}

    def create_user(_conn, nombre_completo, email, password_hash):
        created.update(nombre_completo=nombre_completo, email=email, password_hash=password_hash)
        return 42

    monkeypatch.setattr(auth_service, "transaction", lambda: nullcontext(object()))
    monkeypatch.setattr(user_repository, "create_user", create_user)
    monkeypatch.setattr(user_repository, "create_user_detalle", lambda *a: None)
    monkeypatch.setattr(user_repository, "create_verification_token", lambda *a: None)
    return created


def test_register_still_returns_201_json(client, register_db):
    resp = client.post(
        "/register?format=json",
        json={
            "nombre": "Ana",
            "apellido_paterno": "Lopez",
            "apellido_materno": "Diaz",
            "email": "Ana@Example.com",
            "password": "OtraSegura123!",
        },
    )

    assert resp.status_code == 201
    assert resp.get_json()["user"] == {"id": 42, "email": "ana@example.com"}
    assert register_db["password_hash"].startswith("$2b$")
    # Registering does not log anybody in: no tokens are issued here.
    assert "access_token" not in resp.get_json()


def test_register_validation_error_defaults_to_xml(client, register_db):
    resp = client.post("/register", json={"email": "x"})

    assert resp.status_code == 400
    assert resp.mimetype == "application/xml"
    assert ET.fromstring(resp.data).findtext("success") == "false"


def test_verify_email_still_works(client, monkeypatch):
    from repositories import user_repository
    from services import auth_service

    marked = []
    monkeypatch.setattr(auth_service, "transaction", lambda: nullcontext(object()))
    monkeypatch.setattr(
        user_repository,
        "get_verification_by_token_hash",
        lambda _c, _h: {
            "verificacion_id": 1,
            "usuario_id": 42,
            "fecha_expiracion": datetime.now(timezone.utc) + timedelta(hours=1),
            "fecha_verificacion": None,
        },
    )
    monkeypatch.setattr(user_repository, "mark_email_verified", lambda _c, u, v: marked.append((u, v)))

    resp = client.get("/verify-email?token=abc&format=json")

    assert resp.status_code == 200
    assert resp.get_json() == {"success": True, "message": "Email verified"}
    assert marked == [(42, 1)]


def test_unknown_route_is_still_xml_json_not_html(client):
    resp = client.get("/no-such-route?format=json")

    assert resp.status_code == 404
    assert resp.get_json()["success"] is False
