from contextlib import contextmanager

import psycopg2

from config.settings import get_settings


def open_connection():
    settings = get_settings()

    return psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_database,
        user=settings.pg_user,
        password=settings.pg_password,
        connect_timeout=5,
        application_name="library_soap_service",
    )


@contextmanager
def transaction():
    """
    Opens one PostgreSQL transaction.

    Commit occurs only when the block finishes successfully.
    Any exception produces a rollback before the connection is closed.
    """
    conn = open_connection()

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
