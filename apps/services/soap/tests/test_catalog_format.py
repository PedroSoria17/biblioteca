"""
Real tests for catalog/format.py, independent of PostgreSQL: no database
connection is required to resolve the `format` query parameter.
"""

import unittest

from catalog.errors import CatalogError
from catalog.format import get_response_format


class FakeRequest:
    def __init__(self, args: dict[str, str]) -> None:
        self.args = args


class GetResponseFormatTests(unittest.TestCase):
    def test_missing_format_defaults_to_xml(self):
        self.assertEqual(get_response_format(FakeRequest({})), "xml")

    def test_explicit_xml(self):
        self.assertEqual(get_response_format(FakeRequest({"format": "xml"})), "xml")

    def test_explicit_json(self):
        self.assertEqual(get_response_format(FakeRequest({"format": "json"})), "json")

    def test_uppercase_is_normalized(self):
        self.assertEqual(get_response_format(FakeRequest({"format": "JSON"})), "json")

    def test_empty_value_defaults_to_xml(self):
        self.assertEqual(get_response_format(FakeRequest({"format": ""})), "xml")

    def test_unsupported_value_raises_invalid_format(self):
        with self.assertRaises(CatalogError) as ctx:
            get_response_format(FakeRequest({"format": "csv"}))

        self.assertEqual(ctx.exception.code, "INVALID_FORMAT")
        self.assertEqual(ctx.exception.http_status, 400)


if __name__ == "__main__":
    unittest.main()
