from __future__ import annotations

from db.connection import transaction
from db import repository
from soap.envelope import (
    build_obtener_conceptos_pendientes_response,
    build_obtener_progreso_usuario_response,
    build_registrar_clasificacion_response,
)
from soap.faults import (
    SoapServiceError,
    invalid_cloud_model,
    invalid_request,
)


ALLOWED_CLOUD_MODELS = {"IaaS", "PaaS", "SaaS", "FaaS"}


def _record_client_request(cliente: dict[str, str]) -> int:
    """
    Records the request in its own transaction so the counter survives
    even when the business operation later returns a controlled SOAP Fault.
    """
    with transaction() as conn:
        return repository.register_client_request(
            conn,
            tipo_cliente=cliente["tipo_cliente"],
            identificador=cliente["identificador"],
        )


def _save_classifier(
    conn,
    clasificador: dict[str, str],
) -> int:
    return repository.save_classifier(
        conn,
        nombre=clasificador["nombre"],
        apellidos=clasificador["apellidos"],
        correo=clasificador["correo"],
    )


def dispatch(operation: str, payload: dict) -> bytes:
    if operation == "ObtenerConceptosPendientes":
        cliente_id = _record_client_request(payload["cliente"])

        # cliente_id is deliberately recorded even though this operation
        # does not need to persist it elsewhere.
        _ = cliente_id

        with transaction() as conn:
            clasificador_id = _save_classifier(
                conn,
                payload["clasificador"],
            )

            conceptos, total = repository.get_pending_concepts(
                conn,
                clasificador_id=clasificador_id,
                limite=payload["limite"],
            )

        return build_obtener_conceptos_pendientes_response(
            conceptos,
            total,
        )

    if operation == "RegistrarClasificacion":
        cliente_id = _record_client_request(payload["cliente"])

        if payload["modelo_cloud"] not in ALLOWED_CLOUD_MODELS:
            raise invalid_cloud_model()

        with transaction() as conn:
            clasificador_id = _save_classifier(
                conn,
                payload["clasificador"],
            )

            fecha = repository.register_classification(
                conn,
                clasificador_id=clasificador_id,
                isbn=payload["isbn"],
                concepto_id=payload["concepto_id"],
                cliente_id=cliente_id,
                modelo_cloud=payload["modelo_cloud"],
            )

        return build_registrar_clasificacion_response(fecha)

    if operation == "ObtenerProgresoUsuario":
        _record_client_request(payload["cliente"])

        with transaction() as conn:
            clasificador_id = repository.find_classifier_by_email(
                conn,
                payload["correo"],
            )

            progreso = repository.get_progress(
                conn,
                clasificador_id=clasificador_id,
            )

        return build_obtener_progreso_usuario_response(progreso)

    raise invalid_request(f"Operación no soportada: {operation}.")
