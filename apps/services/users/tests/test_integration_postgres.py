"""
Integration tests against a REAL, DISPOSABLE PostgreSQL database.

Skipped unless USERS_IT_DB_NAME is set. They DELETE every row of usuarios,
pedidos, pedido_detalle and pagos, so the database name MUST end in "_test"
(enforced below): never point them at library_db.

The database must contain the full schema: 01_schema.sql, 06_views.sql,
04_stored_procedures.sql, 05_triggers.sql, login_microservice.sql and
migration 07. See README.md ("Pruebas de integración").

Redis is NOT real here (in-memory fake from conftest.py); what is verified
for real is the SQL: constraints, the role_id -> es_administrador trigger,
ON DELETE RESTRICT/CASCADE and the constraint-name -> HTTP code mapping.

Environment:
  USERS_IT_DB_HOST (127.0.0.1), USERS_IT_DB_PORT (5432), USERS_IT_DB_NAME,
  USERS_IT_DB_USER (library_user), USERS_IT_DB_PASSWORD
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import bcrypt
import pytest

from conftest import FakeRedis, bearer


IT_DB_NAME = os.getenv("USERS_IT_DB_NAME", "")

pytestmark = pytest.mark.skipif(not IT_DB_NAME, reason="USERS_IT_DB_NAME not set (no disposable PostgreSQL)")

LOGIN_DIR = Path(__file__).resolve().parents[2] / "login"
SEED_PASSWORD = "SeedPassword123"


def _db_env() -> dict[str, str]:
    if not IT_DB_NAME.endswith("_test"):
        pytest.fail("USERS_IT_DB_NAME must end with '_test': these tests delete every user.")
    return {
        "DB_HOST": os.getenv("USERS_IT_DB_HOST", "127.0.0.1"),
        "DB_PORT": os.getenv("USERS_IT_DB_PORT", "5432"),
        "DB_NAME": IT_DB_NAME,
        "DB_USER": os.getenv("USERS_IT_DB_USER", "library_user"),
        "DB_PASSWORD": os.getenv("USERS_IT_DB_PASSWORD", ""),
    }


@pytest.fixture
def db_env(env, monkeypatch):
    values = _db_env()
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def sql(db_env):
    import psycopg

    conn = psycopg.connect(
        host=db_env["DB_HOST"],
        port=db_env["DB_PORT"],
        dbname=db_env["DB_NAME"],
        user=db_env["DB_USER"],
        password=db_env["DB_PASSWORD"],
        autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()


def _one(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchone()


@pytest.fixture
def seed(sql):
    """Clean slate: one ADMIN, one USER and one USER with an order."""
    with sql.cursor() as cur:
        cur.execute("DELETE FROM pagos")
        cur.execute("DELETE FROM pedido_detalle")
        cur.execute("DELETE FROM pedidos")
        cur.execute("DELETE FROM usuarios")  # cascades usuario_detalle / verificacion
    hashed = bcrypt.hashpw(SEED_PASSWORD.encode(), bcrypt.gensalt(4)).decode()

    def insert(nombre, email, role_id):
        return _one(
            sql,
            "INSERT INTO usuarios (nombre_completo, email, password_hash, role_id) VALUES (%s, %s, %s, %s) "
            "RETURNING usuario_id",
            (nombre, email, hashed, role_id),
        )[0]

    ids = {
        "admin": insert("Admin IT", "admin.it@example.com", 2),
        "user": insert("User IT", "user.it@example.com", 1),
        "buyer": insert("Buyer IT", "buyer.it@example.com", 1),
    }
    ids["pedido"] = _one(sql, "INSERT INTO pedidos (usuario_id) VALUES (%s) RETURNING pedido_id", (ids["buyer"],))[0]
    return ids


@pytest.fixture
def it_client(db_env, seed, monkeypatch):
    from app import create_app
    from library_shared.redis_client import RedisGateway
    from services import passwords

    monkeypatch.setattr(passwords, "BCRYPT_ROUNDS", 4)
    application = create_app(redis_gateway=RedisGateway(FakeRedis()))
    application.testing = True
    return application.test_client()


@pytest.fixture
def admin_h(make_token, seed):
    return bearer(make_token(seed["admin"], 2))


def _row(sql, usuario_id):
    return _one(
        sql,
        "SELECT nombre_completo, email, password_hash, role_id, es_administrador, activo, fecha_registro "
        "FROM usuarios WHERE usuario_id = %s",
        (usuario_id,),
    )


# ---------------------------------------------------------------------------


def test_list_and_get_never_return_password_hash(it_client, admin_h, seed):
    response = it_client.get("/users", headers=admin_h)

    assert response.status_code == 200
    body = response.get_json()
    assert body["pagination"]["total"] == 3
    assert {u["email"] for u in body["data"]} == {"admin.it@example.com", "user.it@example.com", "buyer.it@example.com"}
    assert "password" not in response.get_data(as_text=True)
    assert "$2b$" not in response.get_data(as_text=True)

    me = it_client.get("/users/me", headers=admin_h).get_json()["data"]
    assert me["usuario_id"] == seed["admin"] and me["role"] == "ADMIN"


def test_create_user_and_trigger_keeps_es_administrador_false(it_client, admin_h, sql):
    response = it_client.post(
        "/users",
        json={"nombre_completo": "Nuevo IT", "email": "Nuevo.IT@Example.com", "password": "Password123"},
        headers=admin_h,
    )

    assert response.status_code == 201
    new_id = response.get_json()["data"]["usuario_id"]
    nombre, email, password_hash, role_id, es_admin, activo, _ = _row(sql, new_id)
    assert (email, role_id, es_admin, activo) == ("nuevo.it@example.com", 1, False, True)
    assert bcrypt.checkpw(b"Password123", password_hash.encode())


def test_second_admin_is_409_both_from_precheck_and_from_unique_index(it_client, admin_h, monkeypatch, sql):
    body = {"nombre_completo": "Otro Admin", "email": "otro.admin@example.com", "password": "Password123", "role_id": 2}

    first = it_client.post("/users", json=body, headers=admin_h)
    assert first.status_code == 409
    assert first.get_json()["code"] == "ADMIN_ALREADY_EXISTS"

    from repositories import user_repository

    monkeypatch.setattr(user_repository, "admin_exists", lambda *_a, **_k: False)
    second = it_client.post("/users", json=body, headers=admin_h)
    assert second.status_code == 409
    assert second.get_json()["code"] == "ADMIN_ALREADY_EXISTS"  # ux_usuarios_un_solo_administrador
    assert _one(sql, "SELECT count(*) FROM usuarios WHERE email = 'otro.admin@example.com'")[0] == 0


def test_duplicate_email_is_409_case_insensitive_and_from_unique_constraint(it_client, admin_h, sql, monkeypatch):
    # Legacy row with uppercase letters (the UNIQUE constraint is case-sensitive).
    _one(
        sql,
        "INSERT INTO usuarios (nombre_completo, email, password_hash) VALUES ('Legacy', 'Legacy@Example.com', 'x') "
        "RETURNING usuario_id",
    )
    body = {"nombre_completo": "Dup", "email": "legacy@example.com", "password": "Password123"}
    assert it_client.post("/users", json=body, headers=admin_h).get_json()["code"] == "EMAIL_ALREADY_EXISTS"

    from repositories import user_repository

    monkeypatch.setattr(user_repository, "email_taken", lambda *_a, **_k: False)
    body["email"] = "user.it@example.com"
    response = it_client.post("/users", json=body, headers=admin_h)
    assert response.status_code == 409
    assert response.get_json()["code"] == "EMAIL_ALREADY_EXISTS"  # usuarios_email_key


def test_unknown_role_is_400_from_precheck_and_from_foreign_key(it_client, admin_h, monkeypatch):
    body = {"nombre_completo": "R", "email": "r@example.com", "password": "Password123", "role_id": 99}
    assert it_client.post("/users", json=body, headers=admin_h).get_json()["code"] == "INVALID_ROLE"

    from repositories import user_repository

    monkeypatch.setattr(user_repository, "role_exists", lambda *_a, **_k: True)
    response = it_client.post("/users", json=body, headers=admin_h)
    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_ROLE"  # fk_usuarios_role


def test_patch_partial_only_changes_given_field(it_client, admin_h, seed, sql):
    before = _row(sql, seed["user"])

    response = it_client.patch(f"/users/{seed['user']}", json={"activo": False}, headers=admin_h)

    assert response.status_code == 200
    after = _row(sql, seed["user"])
    assert after[5] is False
    assert after[:5] == before[:5] and after[6] == before[6]


def test_put_and_password_change(it_client, admin_h, seed, sql):
    body = {"nombre_completo": "User Put", "email": "user.put@example.com", "role_id": 1, "activo": True}
    old_hash = _row(sql, seed["user"])[2]

    assert it_client.put(f"/users/{seed['user']}", json=body, headers=admin_h).status_code == 200
    assert _row(sql, seed["user"])[2] == old_hash

    assert it_client.patch(f"/users/{seed['user']}", json={"password": "NuevaClave999"}, headers=admin_h).status_code == 200
    assert bcrypt.checkpw(b"NuevaClave999", _row(sql, seed["user"])[2].encode())


def test_promotion_writes_role_id_and_trigger_syncs_es_administrador(it_client, make_token, seed, sql):
    # Simulate "no admin in the database" (the token still says ADMIN).
    _one(sql, "UPDATE usuarios SET role_id = 1 WHERE usuario_id = %s RETURNING usuario_id", (seed["admin"],))
    headers = bearer(make_token(seed["admin"], 2))

    response = it_client.patch(f"/users/{seed['user']}", json={"role_id": 2}, headers=headers)

    assert response.status_code == 200
    _, _, _, role_id, es_admin, _, _ = _row(sql, seed["user"])
    assert (role_id, es_admin) == (2, True)
    assert _one(sql, "SELECT count(*) FROM usuarios WHERE es_administrador <> (role_id = 2)")[0] == 0


def test_last_admin_protection(it_client, admin_h, seed, sql):
    admin = seed["admin"]
    before = _row(sql, admin)

    assert it_client.delete(f"/users/{admin}", headers=admin_h).get_json()["code"] == "LAST_ADMIN_REQUIRED"
    assert it_client.patch(f"/users/{admin}", json={"activo": False}, headers=admin_h).get_json()["code"] == (
        "LAST_ADMIN_REQUIRED"
    )
    assert it_client.patch(f"/users/{admin}", json={"role_id": 1}, headers=admin_h).get_json()["code"] == (
        "LAST_ADMIN_REQUIRED"
    )
    assert _row(sql, admin) == before


def test_delete_user_with_orders_is_409_and_history_is_kept(it_client, admin_h, seed, sql, monkeypatch):
    response = it_client.delete(f"/users/{seed['buyer']}", headers=admin_h)
    assert response.status_code == 409
    assert response.get_json()["code"] == "USER_HAS_ORDER_HISTORY"

    from repositories import user_repository

    monkeypatch.setattr(user_repository, "has_orders", lambda *_a, **_k: False)
    response = it_client.delete(f"/users/{seed['buyer']}", headers=admin_h)
    assert response.status_code == 409
    assert response.get_json()["code"] == "USER_HAS_ORDER_HISTORY"  # fk_pedidos_usuario RESTRICT

    assert _row(sql, seed["buyer"]) is not None
    assert _one(sql, "SELECT usuario_id FROM pedidos WHERE pedido_id = %s", (seed["pedido"],))[0] == seed["buyer"]


def test_delete_cascades_login_tables(it_client, admin_h, seed, sql):
    uid = seed["user"]
    _one(
        sql,
        "INSERT INTO usuario_detalle (usuario_id, nombre, apellido_paterno) VALUES (%s, 'U', 'IT') "
        "RETURNING usuario_id",
        (uid,),
    )
    _one(
        sql,
        "INSERT INTO usuario_verificacion_email (usuario_id, token_hash, fecha_expiracion) "
        "VALUES (%s, %s, now() + interval '1 hour') RETURNING verificacion_id",
        (uid, "h" * 64),
    )

    response = it_client.delete(f"/users/{uid}", headers=admin_h)

    assert response.status_code == 200
    assert _row(sql, uid) is None
    assert _one(sql, "SELECT count(*) FROM usuario_detalle WHERE usuario_id = %s", (uid,))[0] == 0
    assert _one(sql, "SELECT count(*) FROM usuario_verificacion_email WHERE usuario_id = %s", (uid,))[0] == 0
    assert it_client.get(f"/users/{uid}", headers=admin_h).status_code == 404


def _login_with_real_login_service(db_env: dict, email: str, password: str) -> dict:
    """Runs apps/services/login's own login_user against the same database."""
    script = (
        "import json, os, sys\n"
        "from services.auth_service import login_user\n"
        "from utils.errors import ServiceError\n"
        "try:\n"
        "    print(json.dumps(login_user({'email': os.environ['T_EMAIL'], 'password': os.environ['T_PASSWORD']})))\n"
        "except ServiceError as exc:\n"
        "    print(json.dumps({'error': exc.code}))\n"
    )
    env = {
        **os.environ,
        **db_env,
        "SECRET_KEY": "login-it-secret",
        "T_EMAIL": email,
        "T_PASSWORD": password,
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=LOGIN_DIR, env=env, capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0 and "ModuleNotFoundError" in result.stderr:
        pytest.skip("login dependencies not installed in this interpreter")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_login_service_accepts_users_created_and_changed_by_users(it_client, admin_h, db_env):
    created = it_client.post(
        "/users",
        json={"nombre_completo": "Compat IT", "email": "Compat.IT@Example.com", "password": "CreadaPorUsers1"},
        headers=admin_h,
    ).get_json()["data"]

    assert _login_with_real_login_service(db_env, "compat.it@example.com", "CreadaPorUsers1") == {
        "id": created["usuario_id"],
        "email": "compat.it@example.com",
        "role_id": 1,
    }

    it_client.patch(f"/users/{created['usuario_id']}", json={"password": "CambiadaPorUsers2"}, headers=admin_h)
    assert _login_with_real_login_service(db_env, "compat.it@example.com", "CreadaPorUsers1") == {
        "error": "INVALID_CREDENTIALS"
    }
    assert _login_with_real_login_service(db_env, "compat.it@example.com", "CambiadaPorUsers2")["id"] == (
        created["usuario_id"]
    )

    # Deactivated by Users -> Login refuses it.
    it_client.patch(f"/users/{created['usuario_id']}", json={"activo": False}, headers=admin_h)
    assert _login_with_real_login_service(db_env, "compat.it@example.com", "CambiadaPorUsers2") == {
        "error": "INVALID_CREDENTIALS"
    }
