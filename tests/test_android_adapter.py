import os
import tempfile
import unittest
from fastapi.testclient import TestClient

class TestAndroidAdapter(unittest.TestCase):
    def test_android_paths_configuration(self):
        import android_entry
        with tempfile.TemporaryDirectory() as tmp_internal, tempfile.TemporaryDirectory() as tmp_down:
            android_entry.configure_android_paths(tmp_internal, tmp_down)
            self.assertEqual(os.environ.get("MANHUA_IS_ANDROID"), "1")
            self.assertIn(tmp_internal, os.environ.get("MANHUA_DB_PATH"))
            self.assertEqual(os.environ.get("MANHUA_DOWNLOADS_DIR"), tmp_down)
            self.assertTrue(os.path.exists(os.path.join(tmp_internal, "manhua_extractor.db")))

    def test_health_check_endpoint(self):
        from app import app
        client = TestClient(app)
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")

    def test_server_status_helpers(self):
        import android_entry
        self.assertEqual(android_entry.get_server_port(), 8000)
        self.assertFalse(android_entry.is_server_running())

if __name__ == "__main__":
    unittest.main()
