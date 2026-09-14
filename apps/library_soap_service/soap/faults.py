from dataclasses import dataclass
import xml.etree.ElementTree as ET


SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
TNS = "http://udem.edu/iac/library-classifier/v1"

ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("tns", TNS)


@dataclass
class SoapServiceError(Exception):
    code: str
    message: str
    http_status: int = 400
    fault_code: str = "soap:Client"

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def invalid_xml() -> SoapServiceError:
    return SoapServiceError(
        "INVALID_XML",
        "El documento XML recibido no es un SOAP Envelope válido.",
        400,
        "soap:Client",
    )


def invalid_request(message: str) -> SoapServiceError:
    return SoapServiceError(
        "INVALID_REQUEST",
        message,
        400,
        "soap:Client",
    )


def invalid_email() -> SoapServiceError:
    return SoapServiceError(
        "INVALID_EMAIL",
        "El correo proporcionado no tiene un formato válido.",
        400,
        "soap:Client",
    )


def invalid_cloud_model() -> SoapServiceError:
    return SoapServiceError(
        "INVALID_CLOUD_MODEL",
        "El modelo Cloud debe ser IaaS, PaaS, SaaS o FaaS.",
        400,
        "soap:Client",
    )


def concept_not_found() -> SoapServiceError:
    return SoapServiceError(
        "CONCEPT_NOT_FOUND",
        "El concepto solicitado no existe.",
        404,
        "soap:Client",
    )


def book_concept_not_found() -> SoapServiceError:
    return SoapServiceError(
        "BOOK_CONCEPT_NOT_FOUND",
        "El concepto no está asociado con el libro indicado.",
        404,
        "soap:Client",
    )


def duplicate_classification() -> SoapServiceError:
    return SoapServiceError(
        "DUPLICATE_CLASSIFICATION",
        "Este clasificador ya registró una clasificación para el concepto.",
        409,
        "soap:Client",
    )


def internal_error() -> SoapServiceError:
    return SoapServiceError(
        "INTERNAL_ERROR",
        "Ocurrió un error interno al procesar la solicitud.",
        500,
        "soap:Server",
    )


def build_fault(error: SoapServiceError) -> bytes:
    """
    Builds a SOAP 1.1 Fault.

    Technical details, SQL, stack traces and internal paths are intentionally
    excluded from the response sent to the client.
    """
    envelope = ET.Element(ET.QName(SOAP_NS, "Envelope"))
    body = ET.SubElement(envelope, ET.QName(SOAP_NS, "Body"))
    fault = ET.SubElement(body, ET.QName(SOAP_NS, "Fault"))

    fault_code = ET.SubElement(fault, "faultcode")
    fault_code.text = error.fault_code

    fault_string = ET.SubElement(fault, "faultstring")
    fault_string.text = error.message

    detail = ET.SubElement(fault, "detail")
    service_fault = ET.SubElement(detail, ET.QName(TNS, "ServiceFault"))

    code = ET.SubElement(service_fault, ET.QName(TNS, "codigo"))
    code.text = error.code

    message = ET.SubElement(service_fault, ET.QName(TNS, "mensaje"))
    message.text = error.message

    return ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
    )
