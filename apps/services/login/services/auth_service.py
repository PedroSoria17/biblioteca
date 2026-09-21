from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import psycopg

from config import Settings, get_settings
from db.connection import open_connection, transaction
from repositories import user_repository as repo
from services import email_service
from utils.errors import (
    email_already_registered,
    invalid_credentials,
    invalid_input,
    invalid_token,
    token_expired,
)
from utils.tokens import generate_token, hash_token
from utils.validators import (
    MIN_PASSWORD_LENGTH,
    is_valid_email,
    is_valid_password,
    normalize_email,
    normalize_text,
)


logger = logging.getLogger("login_microservice.auth")

# bcrypt hashes are self-describing ($2b$<cost>$...), so this only affects
# hashes created by THIS service. Existing $2a$/$2b$ hashes written by the
# monolith's bcryptjs (cost 10) keep working unchanged: bcrypt.checkpw reads
# the cost from the stored hash itself, it does not need to match ours.
BCRYPT_ROUNDS = 12

REQUIRED_REGISTER_FIELDS = ("nombre", "apellido_paterno", "apellido_materno", "email", "password")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(BCRYPT_ROUNDS)).decode("utf-8")


def _check_password(password: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        # Stored hash is not a bcrypt hash bcrypt recognizes.
        return False


def register_user(payload: dict, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()

    if not isinstance(payload, dict):
        raise invalid_input("Request body must be a JSON object.")

    values: dict[str, str] = {}
    for field in REQUIRED_REGISTER_FIELDS:
        raw = payload.get(field)
        if raw is None or not str(raw).strip():
            raise invalid_input(f"Field '{field}' is required.")
        values[field] = normalize_text(str(raw))

    email = normalize_email(values["email"])
    if not is_valid_email(email):
        raise invalid_input("Field 'email' has an invalid format.")

    password = str(payload.get("password") or "")
    if not is_valid_password(password):
        raise invalid_input(
            f"Field 'password' must be at least {MIN_PASSWORD_LENGTH} characters long."
        )

    nombre = values["nombre"]
    apellido_paterno = values["apellido_paterno"]
    apellido_materno = values["apellido_materno"]
    nombre_completo = f"{nombre} {apellido_paterno} {apellido_materno}"

    password_hash = _hash_password(password)
    token = generate_token()
    token_hash = hash_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.email_token_expiration_minutes
    )

    with transaction() as conn:
        try:
            usuario_id = repo.create_user(conn, nombre_completo, email, password_hash)
        except psycopg.errors.UniqueViolation as exc:
            raise email_already_registered() from exc

        repo.create_user_detalle(conn, usuario_id, nombre, apellido_paterno, apellido_materno)
        repo.create_verification_token(conn, usuario_id, token_hash, expires_at)

    verification_url = f"{settings.public_base_url}/verify-email?token={token}"
    email_service.send_verification_email(settings, email, verification_url)

    if settings.dev_show_verification_link and not settings.mail_enabled:
        logger.info("[DEV] Verification URL for %s: %s", email, verification_url)

    return {"id": usuario_id, "email": email}


def login_user(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise invalid_input("Request body must be a JSON object.")

    email = normalize_email(str(payload.get("email") or ""))
    password = str(payload.get("password") or "")

    if not email or not password:
        raise invalid_input("Fields 'email' and 'password' are required.")

    with open_connection() as conn:
        user = repo.get_user_by_email(conn, email)

    # Same generic error for "no such email" and "wrong password" so the
    # response never leaks which of the two was the actual problem. This
    # also covers legacy users with no usuario_detalle row: they only need
    # usuarios.email / usuarios.password_hash / usuarios.activo to log in.
    if user is None or not user["activo"]:
        raise invalid_credentials()

    if not _check_password(password, user["password_hash"]):
        raise invalid_credentials()

    return {"id": user["usuario_id"], "email": user["email"]}


def verify_email(token: str) -> dict:
    token = normalize_text(token)
    if not token:
        raise invalid_token()

    token_hash = hash_token(token)

    with transaction() as conn:
        record = repo.get_verification_by_token_hash(conn, token_hash)

        if record is None:
            raise invalid_token()

        if record["fecha_verificacion"] is not None:
            # Idempotent: verifying an already-verified token is a
            # successful no-op, not an error.
            return {"message": "Email already verified"}

        if record["fecha_expiracion"] < datetime.now(timezone.utc):
            raise token_expired()

        repo.mark_email_verified(conn, record["usuario_id"], record["verificacion_id"])

    return {"message": "Email verified"}
