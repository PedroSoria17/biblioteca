import unittest
import xml.etree.ElementTree as ET

from soap.envelope import parse_request
from soap.faults import SoapServiceError, build_fault


VALID_REQUEST = b"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:tns="http://udem.edu/iac/library-classifier/v1">
  <soap:Body>
    <tns:RegistrarClasificacionRequest>
      <tns:clasificador>
        <tns:nombre>Pedro</tns:nombre>
        <tns:apellidos>Soria</tns:apellidos>
        <tns:correo>pedro@example.com</tns:correo>
      </tns:clasificador>
      <tns:cliente>
        <tns:tipoCliente>desktop-python</tns:tipoCliente>
        <tns:identificador>tkinter-test</tns:identificador>
      </tns:cliente>
      <tns:isbn>9781000000032</tns:isbn>
      <tns:conceptoId>1</tns:conceptoId>
      <tns:modeloCloud>IaaS</tns:modeloCloud>
    </tns:RegistrarClasificacionRequest>
  </soap:Body>
</soap:Envelope>
"""


class EnvelopeTests(unittest.TestCase):
    def test_parse_registrar_clasificacion(self):
        operation, payload = parse_request(VALID_REQUEST)

        self.assertEqual(operation, "RegistrarClasificacion")
        self.assertEqual(payload["modelo_cloud"], "IaaS")
        self.assertEqual(payload["concepto_id"], 1)
        self.assertEqual(
            payload["clasificador"]["correo"],
            "pedro@example.com",
        )

    def test_invalid_xml_returns_service_error(self):
        with self.assertRaises(SoapServiceError) as context:
            parse_request(b"<broken")

        self.assertEqual(context.exception.code, "INVALID_XML")

    def test_fault_is_well_formed_xml(self):
        error = SoapServiceError(
            "TEST",
            "Mensaje seguro",
            400,
            "soap:Client",
        )
        xml = build_fault(error)
        ET.fromstring(xml)


if __name__ == "__main__":
    unittest.main()
