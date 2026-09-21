"""
WS-Security extension point.

The initial three SOAP operations do not require WS-Security yet.
Tarea 1 will extend the WSDL and use this module to validate a
UsernameToken for ObtenerEstadisticasPorModelo.

Do not store real passwords or credentials in this file.
"""

WSSE_NS = (
    "http://docs.oasis-open.org/wss/2004/01/"
    "oasis-200401-wss-wssecurity-secext-1.0.xsd"
)


def validate_username_token(_soap_header) -> bool:
    raise NotImplementedError(
        "WS-Security will be implemented in Tarea 1."
    )
