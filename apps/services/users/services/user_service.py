"""
Business rules of the users microservice.

Every write runs in ONE PostgreSQL transaction that first locks the target
row (SELECT ... FOR UPDATE), validates the rules, and only then writes. The
database constraints stay as the final barrier; their known violations are
translated to 409/400 instead of surfacing as 500:

- usuarios_email_key                -> 409 EMAIL_ALREADY_EXISTS
- ux_usuarios_un_solo_administrador -> 409 ADMIN_ALREADY_EXISTS
- fk_usuarios_role                  -> 400 INVALID_ROLE
- fk_pedidos_usuario (on DELETE)    -> 409 USER_HAS_ORDER_HISTORY
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg

from db.connection import open_connection, transaction
from library_shared.roles import ROLE_ADMIN
from repositories import user_repository as repo
from services.passwords import hash_password
from utils.errors import (
    ServiceError,
    admin_already_exists,
    admin_must_be_active,
    email_already_exists,
    invalid_role,
    last_admin_required,
    user_has_dependencies,
    user_has_order_history,
    user_not_found,
)


logger = logging.getLogger("users_microservice.users")

ADMIN_UNIQUE_INDEX = "ux_usuarios_un_solo_administrador"
ROLE_FOREIGN_KEY = "fk_usuarios_role"
ORDERS_FOREIGN_KEY = "fk_pedidos_usuario"


def _constraint_name(exc: psycopg.Error) -> str | None:
    diag = getattr(exc, "diag", None)
    return getattr(diag, "constraint_name", None) if diag is not None else None


def _translate_integrity_error(exc: psycopg.IntegrityError) -> ServiceError:
    constraint = _constraint_name(exc)
    if isinstance(exc, psycopg.errors.UniqueViolation):
        if constraint == ADMIN_UNIQUE_INDEX:
            return admin_already_exists()
        return email_already_exists()
    if isinstance(exc, psycopg.errors.ForeignKeyViolation):
        if constraint == ROLE_FOREIGN_KEY:
            return invalid_role()
        if constraint == ORDERS_FOREIGN_KEY:
            return user_has_order_history()
        return user_has_dependencies()
    # CHECK violations etc. are not expected from validated input: let the
    # generic handler log them and answer 500.
    raise exc


def to_public(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-ready user. password_hash is never part of `row` to begin with."""
    fecha = row.get("fecha_registro")
    return {
        "usuario_id": row["usuario_id"],
        "nombre_completo": row["nombre_completo"],
        "email": row["email"],
        "role_id": row["role_id"],
        "role": row.get("role"),
        "activo": row["activo"],
        "fecha_registro": fecha.isoformat() if hasattr(fecha, "isoformat") else fecha,
    }


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_users(limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    with open_connection() as conn:
        rows = repo.list_users(conn, limit, offset)
        total = repo.count_users(conn)
    return [to_public(row) for row in rows], total


def get_user(usuario_id: int) -> dict[str, Any]:
    with open_connection() as conn:
        row = repo.get_user(conn, usuario_id)
    if row is None:
        raise user_not_found()
    return to_public(row)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def create_user(values: dict[str, Any], actor_id: int) -> dict[str, Any]:
    role_id = values["role_id"]
    activo = values["activo"]

    if role_id == ROLE_ADMIN and not activo:
        raise admin_must_be_active()

    # Hash outside the transaction: bcrypt is deliberately slow and must not
    # extend the time rows/locks are held.
    password_hash = hash_password(values["password"])

    with transaction() as conn:
        if not repo.role_exists(conn, role_id):
            raise invalid_role()
        if repo.email_taken(conn, values["email"]):
            raise email_already_exists()
        if role_id == ROLE_ADMIN and repo.admin_exists(conn):
            raise admin_already_exists()

        try:
            usuario_id = repo.insert_user(
                conn, values["nombre_completo"], values["email"], password_hash, role_id, activo
            )
        except psycopg.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc

        row = repo.get_user(conn, usuario_id)

    logger.info("User %s created (role_id=%s) by admin %s", usuario_id, role_id, actor_id)
    return to_public(row)


def update_user(usuario_id: int, values: dict[str, Any], actor_id: int) -> dict[str, Any]:
    """
    Shared by PUT (all administrative fields) and PATCH (only the given
    ones). `values` only contains validated fields that the client sent, so
    PATCH never overwrites anything it did not mention.
    """
    password_hash = hash_password(values["password"]) if "password" in values else None

    with transaction() as conn:
        current = repo.get_user(conn, usuario_id, for_update=True)
        if current is None:
            raise user_not_found()

        new_role = values.get("role_id", current["role_id"])
        new_activo = values.get("activo", current["activo"])
        is_admin = current["role_id"] == ROLE_ADMIN

        if "role_id" in values and new_role != current["role_id"] and not repo.role_exists(conn, new_role):
            raise invalid_role()

        if is_admin and (new_role != ROLE_ADMIN or not new_activo):
            # Demoting or deactivating the admin: only allowed if another
            # active admin would remain (never true while
            # ux_usuarios_un_solo_administrador allows a single admin).
            if repo.count_other_active_admins(conn, usuario_id) == 0:
                raise last_admin_required()

        if not is_admin and new_role == ROLE_ADMIN:
            if not new_activo:
                raise admin_must_be_active()
            if repo.admin_exists(conn, exclude_usuario_id=usuario_id):
                raise admin_already_exists()

        if "email" in values and values["email"] != current["email"]:
            if repo.email_taken(conn, values["email"], exclude_usuario_id=usuario_id):
                raise email_already_exists()

        changes: dict[str, Any] = {}
        for field in ("nombre_completo", "email", "activo"):
            if field in values and values[field] != current[field]:
                changes[field] = values[field]
        if "role_id" in values and new_role != current["role_id"]:
            # Only role_id: the trigger derives es_administrador.
            changes["role_id"] = new_role
        if password_hash is not None:
            changes["password_hash"] = password_hash

        try:
            repo.update_user(conn, usuario_id, changes)
        except psycopg.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc

        row = repo.get_user(conn, usuario_id)

    changed = sorted("password" if c == "password_hash" else c for c in changes)
    logger.info("User %s updated by admin %s (fields=%s)", usuario_id, actor_id, ",".join(changed) or "-")
    return to_public(row)


def delete_user(usuario_id: int, actor_id: int) -> None:
    with transaction() as conn:
        current = repo.get_user(conn, usuario_id, for_update=True)
        if current is None:
            raise user_not_found()

        if current["role_id"] == ROLE_ADMIN and repo.count_other_active_admins(conn, usuario_id) == 0:
            raise last_admin_required()

        # Explicit check for a clear 409; fk_pedidos_usuario (RESTRICT) is
        # still the final guarantee if an order appears concurrently.
        if repo.has_orders(conn, usuario_id):
            raise user_has_order_history()

        try:
            repo.delete_user(conn, usuario_id)
        except psycopg.IntegrityError as exc:
            raise _translate_integrity_error(exc) from exc

    logger.info("User %s deleted by admin %s", usuario_id, actor_id)
