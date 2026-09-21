from __future__ import annotations

from decimal import Decimal
from typing import Any
import xml.etree.ElementTree as ET

from soap.faults import (
    SOAP_NS,
    TNS,
    SoapServiceError,
    invalid_email,
    invalid_request,
    invalid_xml,
)


ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("tns", TNS)


SUPPORTED_OPERATIONS = {
    "ObtenerConceptosPendientesRequest",
    "RegistrarClasificacionRequest",
    "ObtenerProgresoUsuarioRequest",
}


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _children_by_local_name(element: ET.Element) -> dict[str, ET.Element]:
    return {local_name(child.tag): child for child in list(element)}


def _required_text(parent: ET.Element, name: str) -> str:
    children = _children_by_local_name(parent)
    element = children.get(name)

    if element is None or element.text is None or not element.text.strip():
        raise invalid_request(f"Falta el campo obligatorio '{name}'.")

    return element.text.strip()


def _optional_text(parent: ET.Element, name: str) -> str | None:
    children = _children_by_local_name(parent)
    element = children.get(name)

    if element is None or element.text is None:
        return None

    value = element.text.strip()
    return value or None


def _complex(parent: ET.Element, name: str) -> ET.Element:
    children = _children_by_local_name(parent)
    element = children.get(name)

    if element is None:
        raise invalid_request(f"Falta el elemento obligatorio '{name}'.")

    return element


def _parse_email(value: str) -> str:
    value = value.strip().lower()

    if len(value) > 255 or "@" not in value:
        raise invalid_email()

    local, _, domain = value.partition("@")

    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise invalid_email()

    return value


def _parse_clasificador(element: ET.Element) -> dict[str, str]:
    return {
        "nombre": _required_text(element, "nombre"),
        "apellidos": _required_text(element, "apellidos"),
        "correo": _parse_email(_required_text(element, "correo")),
    }


def _parse_cliente(element: ET.Element) -> dict[str, str]:
    return {
        "tipo_cliente": _required_text(element, "tipoCliente"),
        "identificador": _required_text(element, "identificador"),
    }


def parse_request(xml_bytes: bytes) -> tuple[str, dict[str, Any]]:
    """
    Parses a SOAP 1.1 Envelope manually using ElementTree.

    It intentionally does not use Spyne/Zeep on the server.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise invalid_xml() from exc

    if local_name(root.tag) != "Envelope":
        raise invalid_xml()

    body = None

    for child in root:
        if local_name(child.tag) == "Body":
            body = child
            break

    if body is None:
        raise invalid_request("El SOAP Envelope no contiene Body.")

    operations = list(body)

    if len(operations) != 1:
        raise invalid_request(
            "SOAP Body debe contener exactamente una operación."
        )

    operation_element = operations[0]
    request_name = local_name(operation_element.tag)

    if request_name not in SUPPORTED_OPERATIONS:
        raise invalid_request(
            f"Operación SOAP no soportada: {request_name}."
        )

    if request_name == "ObtenerConceptosPendientesRequest":
        clasificador = _parse_clasificador(
            _complex(operation_element, "clasificador")
        )
        cliente = _parse_cliente(
            _complex(operation_element, "cliente")
        )

        limite_text = _optional_text(operation_element, "limite")
        limite = 50

        if limite_text is not None:
            try:
                limite = int(limite_text)
            except ValueError as exc:
                raise invalid_request(
                    "'limite' debe ser un entero positivo."
                ) from exc

            if limite < 1 or limite > 100:
                raise invalid_request(
                    "'limite' debe estar entre 1 y 100."
                )

        return "ObtenerConceptosPendientes", {
            "clasificador": clasificador,
            "cliente": cliente,
            "limite": limite,
        }

    if request_name == "RegistrarClasificacionRequest":
        clasificador = _parse_clasificador(
            _complex(operation_element, "clasificador")
        )
        cliente = _parse_cliente(
            _complex(operation_element, "cliente")
        )

        concepto_text = _required_text(
            operation_element,
            "conceptoId",
        )

        try:
            concepto_id = int(concepto_text)
        except ValueError as exc:
            raise invalid_request(
                "'conceptoId' debe ser un entero."
            ) from exc

        if concepto_id < 1:
            raise invalid_request(
                "'conceptoId' debe ser mayor que cero."
            )

        return "RegistrarClasificacion", {
            "clasificador": clasificador,
            "cliente": cliente,
            "isbn": _required_text(operation_element, "isbn"),
            "concepto_id": concepto_id,
            # Deliberately validated in the service layer after the
            # client request has been accounted for.
            "modelo_cloud": _required_text(
                operation_element,
                "modeloCloud",
            ),
        }

    # ObtenerProgresoUsuarioRequest
    cliente = _parse_cliente(
        _complex(operation_element, "cliente")
    )

    return "ObtenerProgresoUsuario", {
        "correo": _parse_email(
            _required_text(operation_element, "correo")
        ),
        "cliente": cliente,
    }


def _new_envelope(response_name: str) -> tuple[ET.Element, ET.Element]:
    envelope = ET.Element(ET.QName(SOAP_NS, "Envelope"))
    body = ET.SubElement(envelope, ET.QName(SOAP_NS, "Body"))
    response = ET.SubElement(body, ET.QName(TNS, response_name))
    return envelope, response


def _text(parent: ET.Element, name: str, value: Any) -> None:
    element = ET.SubElement(parent, ET.QName(TNS, name))

    if isinstance(value, bool):
        element.text = "true" if value else "false"
    elif isinstance(value, Decimal):
        element.text = format(value, "f")
    else:
        element.text = str(value)


def build_obtener_conceptos_pendientes_response(
    conceptos: list[dict[str, Any]],
    total_pendientes: int,
) -> bytes:
    envelope, response = _new_envelope(
        "ObtenerConceptosPendientesResponse"
    )

    _text(response, "totalPendientes", total_pendientes)
    conceptos_element = ET.SubElement(
        response,
        ET.QName(TNS, "conceptos"),
    )

    for row in conceptos:
        concepto = ET.SubElement(
            conceptos_element,
            ET.QName(TNS, "concepto"),
        )
        _text(concepto, "isbn", row["isbn"])
        _text(concepto, "tituloLibro", row["titulo_libro"])
        _text(concepto, "categoria", row["categoria"])
        _text(concepto, "conceptoId", row["concepto_id"])
        _text(concepto, "concepto", row["concepto"])
        _text(concepto, "definicion", row["definicion"])

    return ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
    )


def build_registrar_clasificacion_response(
    fecha_clasificacion,
) -> bytes:
    envelope, response = _new_envelope(
        "RegistrarClasificacionResponse"
    )

    _text(response, "registrada", True)
    _text(
        response,
        "mensaje",
        "Clasificación registrada correctamente.",
    )
    _text(
        response,
        "fechaClasificacion",
        fecha_clasificacion.isoformat(),
    )

    return ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
    )


def build_obtener_progreso_usuario_response(
    progreso: dict[str, Any],
) -> bytes:
    envelope, response = _new_envelope(
        "ObtenerProgresoUsuarioResponse"
    )

    _text(response, "totalCatalogo", progreso["total_catalogo"])
    _text(
        response,
        "totalClasificados",
        progreso["total_clasificados"],
    )
    _text(
        response,
        "totalPendientes",
        progreso["total_pendientes"],
    )
    _text(
        response,
        "porcentajeCompletado",
        progreso["porcentaje_completado"],
    )

    return ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
    )
