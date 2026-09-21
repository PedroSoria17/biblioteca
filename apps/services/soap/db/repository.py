from __future__ import annotations

from decimal import Decimal
from typing import Any

from psycopg2 import Error as PostgreSQLError

from soap.faults import (
    book_concept_not_found,
    concept_not_found,
    duplicate_classification,
    internal_error,
    invalid_cloud_model,
)


POSTGRES_FAULTS = {
    "P1001": invalid_cloud_model,
    "P1002": concept_not_found,
    "P1003": book_concept_not_found,
    "P1004": duplicate_classification,
}


def _map_postgres_error(exc: PostgreSQLError):
    factory = POSTGRES_FAULTS.get(exc.pgcode)

    if factory is not None:
        return factory()

    return internal_error()


def save_classifier(
    conn,
    *,
    nombre: str,
    apellidos: str,
    correo: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT soap_module.fn_clasificador_guardar(
                %s, %s, %s
            );
            """,
            (nombre, apellidos, correo),
        )
        return int(cur.fetchone()[0])


def find_classifier_by_email(conn, correo: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT clasificador_id
            FROM soap_module.clasificadores
            WHERE lower(correo) = lower(%s)
              AND activo = TRUE;
            """,
            (correo,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None


def register_client_request(
    conn,
    *,
    tipo_cliente: str,
    identificador: str,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT soap_module.fn_cliente_registrar_peticion(
                %s, %s
            );
            """,
            (tipo_cliente, identificador),
        )
        return int(cur.fetchone()[0])


def get_pending_concepts(
    conn,
    *,
    clasificador_id: int,
    limite: int,
) -> tuple[list[dict[str, Any]], int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                isbn,
                titulo_libro,
                categoria,
                concepto_id,
                concepto,
                definicion,
                total_pendientes
            FROM soap_module.fn_conceptos_pendientes(
                %s, %s
            );
            """,
            (clasificador_id, limite),
        )

        rows = cur.fetchall()

    conceptos = [
        {
            "isbn": row[0],
            "titulo_libro": row[1],
            "categoria": row[2],
            "concepto_id": int(row[3]),
            "concepto": row[4],
            "definicion": row[5],
        }
        for row in rows
    ]

    total = int(rows[0][6]) if rows else 0
    return conceptos, total


def register_classification(
    conn,
    *,
    clasificador_id: int,
    isbn: str,
    concepto_id: int,
    cliente_id: int,
    modelo_cloud: str,
):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT soap_module.fn_registrar_clasificacion(
                    %s, %s, %s, %s, %s
                );
                """,
                (
                    clasificador_id,
                    isbn,
                    concepto_id,
                    cliente_id,
                    modelo_cloud,
                ),
            )
            return cur.fetchone()[0]
    except PostgreSQLError as exc:
        raise _map_postgres_error(exc) from exc


def get_progress(
    conn,
    *,
    clasificador_id: int | None,
) -> dict[str, Any]:
    # A user who has never classified anything has valid progress = 0%.
    if clasificador_id is None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT concepto_id)
                FROM public.libro_concepto;
                """
            )
            total_catalogo = int(cur.fetchone()[0])

        return {
            "total_catalogo": total_catalogo,
            "total_clasificados": 0,
            "total_pendientes": total_catalogo,
            "porcentaje_completado": Decimal("0.00"),
        }

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                total_catalogo,
                total_clasificados,
                total_pendientes,
                porcentaje_completado
            FROM soap_module.fn_progreso_usuario(%s);
            """,
            (clasificador_id,),
        )
        row = cur.fetchone()

    return {
        "total_catalogo": int(row[0]),
        "total_clasificados": int(row[1]),
        "total_pendientes": int(row[2]),
        "porcentaje_completado": row[3],
    }
