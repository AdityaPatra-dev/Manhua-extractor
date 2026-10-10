import json
import os
import unittest
from fastapi.testclient import TestClient
from app import app, get_local_ip

class TestMobilePWAFeatures(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_pwa_manifest_validity(self):
        manifest_path = os.path.join(os.path.dirname(__file__), "..", "static", "manifest.json")
        self.assertTrue(os.path.exists(manifest_path), "manifest.json must exist in static/")
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("name"), "Manhua Extractor & Web Reader")
        self.assertEqual(data.get("display"), "standalone")
        self.assertEqual(data.get("start_url"), "/")
        self.assertIn("icons", data)
        self.assertTrue(len(data["icons"]) > 0)

    def test_pwa_icon_exists(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "static", "icon.svg")
        self.assertTrue(os.path.exists(icon_path), "icon.svg must exist in static/")
        with open(icon_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("<svg", content)

    def test_network_info_endpoint(self):
        resp = self.client.get("/api/network/info")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("lan_ip", data)
        self.assertIn("web_url", data)
        self.assertIn("opds_url", data)
        self.assertTrue(data["opds_url"].endswith("/opds/v1.2/catalog"))

    def test_opds_catalog_endpoint(self):
        resp = self.client.get("/opds/v1.2/catalog")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/atom+xml", resp.headers.get("content-type", ""))
        self.assertIn("<feed", resp.text)
        self.assertIn("Universal Manhua Extractor Library", resp.text)

if __name__ == "__main__":
    unittest.main()
