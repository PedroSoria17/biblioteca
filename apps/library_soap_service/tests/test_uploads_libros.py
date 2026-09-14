"""
Real tests for GET /uploads/libros/<filename>, added so Electron (or any
other XML consumer) can resolve the relative image URLs stored in
imagenes_libro.url (e.g. "/uploads/libros/foo.jpg") into an actual image.

No PostgreSQL is involved: this route only reads static files from
UPLOADS_LIBROS_DIR (config/settings.py), so it is fully testable with a
throwaway temp directory.
"""

import os
import tempfile
import unittest
from pathlib import Path

from app import create_app


class UploadsLibrosRouteTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)

        self.uploads_dir = Path(self._tmp_dir.name)
        (self.uploads_dir / "real-cover.jpg").write_bytes(b"fake-jpeg-bytes")

        self._previous_env = os.environ.get("UPLOADS_LIBROS_DIR")
        os.environ["UPLOADS_LIBROS_DIR"] = str(self.uploads_dir)
        self.addCleanup(self._restore_env)

        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def _restore_env(self):
        if self._previous_env is None:
            os.environ.pop("UPLOADS_LIBROS_DIR", None)
        else:
            os.environ["UPLOADS_LIBROS_DIR"] = self._previous_env

    def test_existing_file_is_served(self):
        resp = self.client.get("/uploads/libros/real-cover.jpg")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"fake-jpeg-bytes")

    def test_missing_file_returns_404_not_an_error_page_with_internals(self):
        resp = self.client.get("/uploads/libros/does-not-exist.jpg")
        self.assertEqual(resp.status_code, 404)

    def test_path_traversal_with_encoded_dotdot_cannot_escape_uploads_dir(self):
        # Attempt to read app.py (one level above uploads_dir) via a
        # traversal sequence embedded in the path segment.
        resp = self.client.get("/uploads/libros/..%2Fapp.py")
        self.assertEqual(resp.status_code, 404)
        self.assertNotIn(b"Flask", resp.data)

    def test_traversal_via_literal_dotdot_segment_cannot_escape_uploads_dir(self):
        resp = self.client.get("/uploads/libros/../app.py")
        self.assertIn(resp.status_code, (404, 400))


if __name__ == "__main__":
    unittest.main()
