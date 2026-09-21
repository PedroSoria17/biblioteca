from __future__ import annotations

from contextlib import contextmanager

import psycopg

from config import get_settings


def open_connection() -> psycopg.Connection:
    settings = get_settings()

    return psycopg.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=5,
        application_name="login_microservice",
    )


@contextmanager
def transaction():
    """
    Opens one PostgreSQL transaction for the lifetime of the block.

    Commit happens only when the block finishes without raising. Any
    exception rolls back everything executed inside the block before the
    connection is closed, so a failure partway through (e.g. the
    usuario_detalle insert during /register) never leaves a partially
    created user behind.
    """
    conn = open_connection()

    try:
        with conn.transaction():
            yield conn
    finally:
        conn.close()
