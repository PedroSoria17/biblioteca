"""
Real functional tests against the actual Flask app (app.create_app()),
using app.test_client(). No PostgreSQL instance was reachable while
building this feature (see README), so only the parts of the REST
catalog that do not require an actual query are asserted end-to-end here:

  - /health (no database access at all);
  - ?format=csv on a data endpoint (format is resolved and rejected
    *before* any repository/database call is made);
  - the safety net for a data endpoint when the database call itself
    fails (confirms a controlled, bilingual 500 INTERNAL_ERROR is
    returned instead of a stack trace or a crash).

The happy path of /books, /books/<isbn>, /cloud-concepts and
/books-with-images against real data was NOT executed here and is listed
under "Pendientes" in the delivery report.
"""

import json
import unittest
import xml.etree.ElementTree as ET

from app import create_app


class CatalogHealthAndFormatTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def test_health_defaults_to_xml(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/xml")
        root = ET.fromstring(resp.data)
        self.assertEqual(root.tag, "health")
        self.assertEqual(root.find("status").text, "ok")
        self.assertEqual(root.find("service").text, "library_soap_service")

    def test_health_format_json(self):
        resp = self.client.get("/health?format=json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/json")
        body = json.loads(resp.data)
        self.assertEqual(body, {"status": "ok", "service": "library_soap_service"})

    def test_health_format_xml_explicit(self):
        resp = self.client.get("/health?format=xml")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/xml")

    def test_invalid_format_returns_400_before_touching_the_database(self):
        resp = self.client.get("/books?format=csv")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.mimetype, "application/xml")
        root = ET.fromstring(resp.data)
        self.assertEqual(root.find("code").text, "INVALID_FORMAT")

    def test_invalid_format_json_requested(self):
        # format itself is invalid, so the fallback documented in
        # catalog/http.py renders the error in the XML default.
        resp = self.client.get("/books/9781000000032?format=csv")
        self.assertEqual(resp.status_code, 400)
        root = ET.fromstring(resp.data)
        self.assertEqual(root.find("code").text, "INVALID_FORMAT")

    def test_books_endpoint_fails_safely_without_a_reachable_database(self):
        # No PostgreSQL instance is reachable in this environment. This
        # asserts the failure is handled: a safe, bilingual 500 response,
        # never a raw traceback, SQL text or credentials.
        resp = self.client.get("/books")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.mimetype, "application/xml")
        root = ET.fromstring(resp.data)
        self.assertEqual(root.find("code").text, "INTERNAL_ERROR")
        self.assertNotIn(b"Traceback", resp.data)
        self.assertNotIn(b"psycopg2", resp.data)

    def test_soap_endpoint_still_registered(self):
        # Confirms adding the catalog routes did not remove/shadow /soap.
        resp = self.client.post("/soap", data=b"not-xml", content_type="text/plain")
        self.assertEqual(resp.status_code, 415)


if __name__ == "__main__":
    unittest.main()
