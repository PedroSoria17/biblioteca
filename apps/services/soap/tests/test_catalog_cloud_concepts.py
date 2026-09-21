"""
Real tests for the /cloud-concepts filtering added on top of
list_cloud_concepts(). No PostgreSQL instance is reachable in this
environment (see README / 01_prompt_bilingue.md report, section K), so
these tests cover what can actually be executed without a database:

  - the exact set of Cloud Computing concept names used to filter the
    query (catches typos/omissions against the list given in the task);
  - that GET /cloud-concepts and GET /cloud-concepts?format=json still
    route correctly and fail safely (bilingual 500 INTERNAL_ERROR, no
    stack trace/SQL leak) when the database is unreachable, proving the
    new WHERE clause did not break routing or error handling.

The actual filtering behavior against real rows (does the endpoint really
return only IaaS/PaaS/SaaS/FaaS/... and exclude unrelated concepts) was
NOT executed here and remains listed under "Pendientes".
"""

import unittest
import xml.etree.ElementTree as ET

from app import create_app
from catalog.repository import CLOUD_COMPUTING_CONCEPT_NAMES


class CloudConceptNameAllowlistTests(unittest.TestCase):
    def test_allowlist_matches_the_names_given_in_the_task(self):
        expected = {
            "IaaS",
            "PaaS",
            "SaaS",
            "FaaS",
            "Bucket",
            "Public Cloud",
            "Private Cloud",
            "Hybrid Cloud",
            "Multicloud",
            "Serverless",
        }
        self.assertEqual(set(CLOUD_COMPUTING_CONCEPT_NAMES), expected)
        self.assertEqual(len(CLOUD_COMPUTING_CONCEPT_NAMES), len(expected))


class CloudConceptsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def test_cloud_concepts_default_xml_fails_safely_without_database(self):
        resp = self.client.get("/cloud-concepts")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.mimetype, "application/xml")
        root = ET.fromstring(resp.data)
        self.assertEqual(root.find("code").text, "INTERNAL_ERROR")
        self.assertNotIn(b"Traceback", resp.data)
        self.assertNotIn(b"psycopg2", resp.data)

    def test_cloud_concepts_format_json_fails_safely_without_database(self):
        resp = self.client.get("/cloud-concepts?format=json")
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.mimetype, "application/json")
        import json

        body = json.loads(resp.data)
        self.assertEqual(body["error"]["code"], "INTERNAL_ERROR")


if __name__ == "__main__":
    unittest.main()
