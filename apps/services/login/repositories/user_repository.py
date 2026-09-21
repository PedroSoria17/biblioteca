from __future__ import annotations

from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


def get_user_by_email(conn: psycopg.Connection, email: str) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT usuario_id, nombre_completo, email, password_hash,
                   es_administrador, activo
            FROM usuarios
            WHERE email = %s
            """,
            (email,),
        )
        return cur.fetchone()


def create_user(conn: psycopg.Connection, nombre_completo: str, email: str, password_hash: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuarios (nombre_completo, email, password_hash)
            VALUES (%s, %s, %s)
            RETURNING usuario_id
            """,
            (nombre_completo, email, password_hash),
        )
        row = cur.fetchone()
        assert row is not None
        return row[0]


def create_user_detalle(
    conn: psycopg.Connection,
    usuario_id: int,
    nombre: str,
    apellido_paterno: str,
    apellido_materno: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuario_detalle
                (usuario_id, nombre, apellido_paterno, apellido_materno)
            VALUES (%s, %s, %s, %s)
            """,
            (usuario_id, nombre, apellido_paterno, apellido_materno),
        )


def create_verification_token(
    conn: psycopg.Connection, usuario_id: int, token_hash: str, expires_at: datetime
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuario_verificacion_email
                (usuario_id, token_hash, fecha_expiracion)
            VALUES (%s, %s, %s)
            """,
            (usuario_id, token_hash, expires_at),
        )


def get_verification_by_token_hash(conn: psycopg.Connection, token_hash: str) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT verificacion_id, usuario_id, fecha_expiracion, fecha_verificacion
            FROM usuario_verificacion_email
            WHERE token_hash = %s
            """,
            (token_hash,),
        )
        return cur.fetchone()


def mark_email_verified(conn: psycopg.Connection, usuario_id: int, verificacion_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE usuario_detalle
            SET email_verificado = TRUE, fecha_actualizacion = now()
            WHERE usuario_id = %s
            """,
            (usuario_id,),
        )
        cur.execute(
            """
            UPDATE usuario_verificacion_email
            SET fecha_verificacion = now()
            WHERE verificacion_id = %s
            """,
            (verificacion_id,),
        )
