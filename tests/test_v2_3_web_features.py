import os
import shutil
import tempfile
import unittest
from fastapi.testclient import TestClient
from database.db import (
    init_db,
    get_or_create_series,
    add_or_update_chapter,
    get_series_by_id,
    get_chapter_by_id,
    get_chapters_for_series,
    delete_series,
    delete_chapter
)
from app import app, DOWNLOADS_DIR

class TestV23WebFeatures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        init_db(self.db_path)
        self.client = TestClient(app)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_delete_chapter_db(self):
        s_id = get_or_create_series("Test Manga", "test-manga", db_path=self.db_path)
        c_id = add_or_update_chapter(s_id, 1.0, title="Chapter 1", db_path=self.db_path)
        
        self.assertIsNotNone(get_chapter_by_id(c_id, db_path=self.db_path))
        ok = delete_chapter(c_id, db_path=self.db_path)
        self.assertTrue(ok)
        self.assertIsNone(get_chapter_by_id(c_id, db_path=self.db_path))

    def test_delete_series_cascade_db(self):
        s_id = get_or_create_series("Cascade Manga", "cascade-manga", db_path=self.db_path)
        c1 = add_or_update_chapter(s_id, 1.0, title="Chapter 1", db_path=self.db_path)
        c2 = add_or_update_chapter(s_id, 2.0, title="Chapter 2", db_path=self.db_path)
        
        self.assertEqual(len(get_chapters_for_series(s_id, db_path=self.db_path)), 2)
        ok = delete_series(s_id, db_path=self.db_path)
        self.assertTrue(ok)
        self.assertIsNone(get_series_by_id(s_id, db_path=self.db_path))
        self.assertEqual(len(get_chapters_for_series(s_id, db_path=self.db_path)), 0)

    def test_api_delete_chapter_and_file(self):
        s_id = get_or_create_series("File Delete Series", "file-del-series")
        test_file = os.path.join(self.temp_dir, "test_chap.cbz")
        with open(test_file, "w") as f:
            f.write("dummy cbz data")

        c_id = add_or_update_chapter(s_id, 99.0, title="Chapter 99", file_path=test_file, status="completed")
        self.assertTrue(os.path.exists(test_file))

        resp = self.client.delete(f"/api/chapters/{c_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("success"))
        # Verify file removed from disk
        self.assertFalse(os.path.exists(test_file))
        # Verify chapter removed from DB
        self.assertIsNone(get_chapter_by_id(c_id))

        # Cleanup series
        delete_series(s_id)

    def test_api_series_storage_path(self):
        s_id = get_or_create_series("storage-path-series", "Storage Path Series")
        resp = self.client.get(f"/api/library/{s_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertIn("storage_dir", data)
        self.assertTrue(data["storage_dir"].endswith("storage-path-series"))

        delete_series(s_id)

    def test_sidecar_nodriver_registration(self):
        from extractors.browser_sidecar import solve_with_nodriver
        self.assertTrue(callable(solve_with_nodriver))

if __name__ == "__main__":
    unittest.main()
