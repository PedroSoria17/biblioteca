from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib import request, error
import xml.etree.ElementTree as ET


SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
TNS = "http://udem.edu/iac/library-classifier/v1"

NS = {
    "soap": SOAP_NS,
    "tns": TNS,
}

ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("tns", TNS)


@dataclass
class SoapFaultError(Exception):
    http_status: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def _text(parent: ET.Element, name: str, value: Any) -> ET.Element:
    node = ET.SubElement(parent, ET.QName(TNS, name))
    node.text = str(value)
    return node


def _base_envelope(request_name: str) -> tuple[ET.Element, ET.Element]:
    envelope = ET.Element(ET.QName(SOAP_NS, "Envelope"))
    body = ET.SubElement(envelope, ET.QName(SOAP_NS, "Body"))
    operation = ET.SubElement(body, ET.QName(TNS, request_name))
    return envelope, operation


def _add_classifier(
    parent: ET.Element,
    *,
    nombre: str,
    apellidos: str,
    correo: str,
) -> None:
    clasificador = ET.SubElement(
        parent,
        ET.QName(TNS, "clasificador"),
    )
    _text(clasificador, "nombre", nombre)
    _text(clasificador, "apellidos", apellidos)
    _text(clasificador, "correo", correo)


def _add_client(
    parent: ET.Element,
    *,
    tipo_cliente: str,
    identificador: str,
) -> None:
    cliente = ET.SubElement(
        parent,
        ET.QName(TNS, "cliente"),
    )
    _text(cliente, "tipoCliente", tipo_cliente)
    _text(cliente, "identificador", identificador)


def _xml_bytes(envelope: ET.Element) -> bytes:
    return ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
    )


class LibrarySoapClient:
    def __init__(
        self,
        endpoint: str,
        *,
        tipo_cliente: str = "desktop-python",
        identificador: str = "tkinter-596630",
        timeout: int = 10,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.tipo_cliente = tipo_cliente
        self.identificador = identificador
        self.timeout = timeout

    def _send(self, payload: bytes) -> tuple[int, bytes]:
        req = request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "Accept": "text/xml",
            },
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return response.status, response.read()

        except error.HTTPError as exc:
            response_body = exc.read()
            self._raise_fault(exc.code, response_body)
            raise

        except error.URLError as exc:
            raise ConnectionError(
                f"No fue posible conectar con {self.endpoint}: {exc.reason}"
            ) from exc

    def _raise_fault(self, status: int, xml_bytes: bytes) -> None:
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            raise SoapFaultError(
                status,
                "HTTP_ERROR",
                f"El servidor respondió HTTP {status} sin un SOAP Fault válido.",
            ) from exc

        fault = root.find(".//soap:Fault", NS)

        if fault is None:
            raise SoapFaultError(
                status,
                "HTTP_ERROR",
                f"El servidor respondió HTTP {status}.",
            )

        fault_string = fault.findtext("faultstring") or "Error SOAP"
        code = fault.findtext(".//tns:codigo", default="SOAP_FAULT", namespaces=NS)
        message = fault.findtext(
            ".//tns:mensaje",
            default=fault_string,
            namespaces=NS,
        )

        raise SoapFaultError(status, code, message)

    def obtener_conceptos_pendientes(
        self,
        *,
        nombre: str,
        apellidos: str,
        correo: str,
        limite: int = 50,
    ) -> list[dict[str, Any]]:
        envelope, operation = _base_envelope(
            "ObtenerConceptosPendientesRequest"
        )

        _add_classifier(
            operation,
            nombre=nombre,
            apellidos=apellidos,
            correo=correo,
        )
        _add_client(
            operation,
            tipo_cliente=self.tipo_cliente,
            identificador=self.identificador,
        )
        _text(operation, "limite", limite)

        _, body = self._send(_xml_bytes(envelope))
        root = ET.fromstring(body)

        rows: list[dict[str, Any]] = []

        for item in root.findall(".//tns:conceptos/tns:concepto", NS):
            rows.append(
                {
                    "isbn": item.findtext("tns:isbn", default="", namespaces=NS),
                    "titulo": item.findtext(
                        "tns:tituloLibro",
                        default="",
                        namespaces=NS,
                    ),
                    "categoria": item.findtext(
                        "tns:categoria",
                        default="",
                        namespaces=NS,
                    ),
                    "concepto_id": int(
                        item.findtext(
                            "tns:conceptoId",
                            default="0",
                            namespaces=NS,
                        )
                    ),
                    "concepto": item.findtext(
                        "tns:concepto",
                        default="",
                        namespaces=NS,
                    ),
                    "definicion": item.findtext(
                        "tns:definicion",
                        default="",
                        namespaces=NS,
                    ),
                }
            )

        return rows

    def registrar_clasificacion(
        self,
        *,
        nombre: str,
        apellidos: str,
        correo: str,
        isbn: str,
        concepto_id: int,
        modelo_cloud: str,
    ) -> dict[str, str]:
        envelope, operation = _base_envelope(
            "RegistrarClasificacionRequest"
        )

        _add_classifier(
            operation,
            nombre=nombre,
            apellidos=apellidos,
            correo=correo,
        )
        _add_client(
            operation,
            tipo_cliente=self.tipo_cliente,
            identificador=self.identificador,
        )

        _text(operation, "isbn", isbn)
        _text(operation, "conceptoId", concepto_id)
        _text(operation, "modeloCloud", modelo_cloud)

        _, body = self._send(_xml_bytes(envelope))
        root = ET.fromstring(body)

        return {
            "registrada": root.findtext(
                ".//tns:registrada",
                default="false",
                namespaces=NS,
            ),
            "mensaje": root.findtext(
                ".//tns:mensaje",
                default="",
                namespaces=NS,
            ),
            "fecha": root.findtext(
                ".//tns:fechaClasificacion",
                default="",
                namespaces=NS,
            ),
        }

    def obtener_progreso_usuario(
        self,
        *,
        correo: str,
    ) -> dict[str, str]:
        envelope, operation = _base_envelope(
            "ObtenerProgresoUsuarioRequest"
        )

        _text(operation, "correo", correo)

        _add_client(
            operation,
            tipo_cliente=self.tipo_cliente,
            identificador=self.identificador,
        )

        _, body = self._send(_xml_bytes(envelope))
        root = ET.fromstring(body)

        return {
            "total_catalogo": root.findtext(
                ".//tns:totalCatalogo",
                default="0",
                namespaces=NS,
            ),
            "total_clasificados": root.findtext(
                ".//tns:totalClasificados",
                default="0",
                namespaces=NS,
            ),
            "total_pendientes": root.findtext(
                ".//tns:totalPendientes",
                default="0",
                namespaces=NS,
            ),
            "porcentaje": root.findtext(
                ".//tns:porcentajeCompletado",
                default="0",
                namespaces=NS,
            ),
        }
