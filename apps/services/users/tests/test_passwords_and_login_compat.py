"""
Passwords written by Users must be accepted by Login.

Login verifies with bcrypt.checkpw (apps/services/login/services/auth_service.py).
The last test runs Login's REAL _check_password in a separate process (its
top-level modules `config`, `services`... have the same names as ours, so
they cannot be imported in this process), without copying its code.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import bcrypt
import pytest

from services import passwords


LOGIN_DIR = Path(__file__).resolve().parents[2] / "login"


def test_hash_password_uses_bcrypt_with_login_cost():
    hashed = passwords.hash_password("PasswordSeguro123!")

    assert hashed.startswith("$2b$12$")
    assert passwords.BCRYPT_ROUNDS == 12
    assert bcrypt.checkpw(b"PasswordSeguro123!", hashed.encode())
    assert not bcrypt.checkpw(b"otra-clave", hashed.encode())


def test_same_password_gets_different_salts():
    assert passwords.hash_password("PasswordSeguro123!") != passwords.hash_password("PasswordSeguro123!")


def test_non_ascii_password_roundtrip():
    hashed = passwords.hash_password("Contraseña-ñandú-ü")

    assert bcrypt.checkpw("Contraseña-ñandú-ü".encode("utf-8"), hashed.encode())


def test_created_and_patched_passwords_verify_like_login(client, admin_headers, user_db):
    created = client.post(
        "/users",
        json={"nombre_completo": "Compat", "email": "compat@example.com", "password": "Creada12345"},
        headers=admin_headers,
    ).get_json()["data"]
    stored = user_db.users[created["usuario_id"]]["password_hash"]
    assert bcrypt.checkpw(b"Creada12345", stored.encode())

    client.patch(f"/users/{created['usuario_id']}", json={"password": "Cambiada6789"}, headers=admin_headers)
    stored = user_db.users[created["usuario_id"]]["password_hash"]
    assert bcrypt.checkpw(b"Cambiada6789", stored.encode())
    assert not bcrypt.checkpw(b"Creada12345", stored.encode())


def test_passwords_never_reach_the_logs(client, admin_headers, caplog):
    caplog.set_level("DEBUG")

    client.post(
        "/users",
        json={"nombre_completo": "Log", "email": "log@example.com", "password": "NoDebeVerse123"},
        headers=admin_headers,
    )
    client.patch("/users/2", json={"password": "TampocoEsta456"}, headers=admin_headers)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "NoDebeVerse123" not in logged
    assert "TampocoEsta456" not in logged
    assert "$2b$" not in logged
    assert "User 2 updated by admin 1 (fields=password)" in logged


@pytest.mark.skipif(not (LOGIN_DIR / "services" / "auth_service.py").exists(), reason="login service not found")
def test_login_check_password_accepts_hash_written_by_users():
    password = "Compatible-Login-123"
    hashed = passwords.hash_password(password)

    script = (
        "import os, sys\n"
        "from services.auth_service import _check_password\n"
        "ok = _check_password(os.environ['T_PASSWORD'], os.environ['T_HASH'])\n"
        "bad = _check_password('wrong-password', os.environ['T_HASH'])\n"
        "sys.exit(0 if ok and not bad else 1)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=LOGIN_DIR,
        env={**os.environ, "T_PASSWORD": password, "T_HASH": hashed},
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0 and "ModuleNotFoundError" in result.stderr:
        pytest.skip("login dependencies not installed in this interpreter")
    assert result.returncode == 0, result.stderr
