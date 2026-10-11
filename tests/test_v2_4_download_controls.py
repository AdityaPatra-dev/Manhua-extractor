import asyncio
import unittest
from fastapi.testclient import TestClient
from app import app, download_progress
from core.downloader import download_panels_stream

class TestV24DownloadControls(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        download_progress["is_running"] = False
        download_progress["is_paused"] = False
        download_progress["is_cancelled"] = False

    def tearDown(self):
        download_progress["is_running"] = False
        download_progress["is_paused"] = False
        download_progress["is_cancelled"] = False

    def test_pause_resume_stop_when_idle(self):
        resp_p = self.client.post("/api/download/pause")
        self.assertEqual(resp_p.status_code, 400)
        self.assertFalse(resp_p.json()["success"])

        resp_r = self.client.post("/api/download/resume")
        self.assertEqual(resp_r.status_code, 400)
        self.assertFalse(resp_r.json()["success"])

        resp_s = self.client.post("/api/download/stop")
        self.assertEqual(resp_s.status_code, 400)
        self.assertFalse(resp_s.json()["success"])

    def test_pause_resume_stop_when_running(self):
        download_progress["is_running"] = True
        
        # Test Pause
        resp_p = self.client.post("/api/download/pause")
        self.assertEqual(resp_p.status_code, 200)
        self.assertTrue(resp_p.json()["success"])
        self.assertTrue(download_progress["is_paused"])
        self.assertEqual(download_progress["status"], "paused")

        # Test Resume
        resp_r = self.client.post("/api/download/resume")
        self.assertEqual(resp_r.status_code, 200)
        self.assertTrue(resp_r.json()["success"])
        self.assertFalse(download_progress["is_paused"])
        self.assertEqual(download_progress["status"], "downloading")

        # Test Stop
        resp_s = self.client.post("/api/download/stop")
        self.assertEqual(resp_s.status_code, 200)
        self.assertTrue(resp_s.json()["success"])
        self.assertTrue(download_progress["is_cancelled"])
        self.assertFalse(download_progress["is_paused"])
        self.assertEqual(download_progress["status"], "stopping")

    def test_downloader_stream_cancellation(self):
        urls = [
            "https://example.com/panel1.jpg",
            "https://example.com/panel2.jpg",
            "https://example.com/panel3.jpg"
        ]

        async def run_test():
            # Cancelled from the start
            res = await download_panels_stream(
                image_urls=urls,
                referer="https://example.com",
                is_cancelled_callback=lambda: True
            )
            self.assertEqual(res, [])

        asyncio.run(run_test())

    def test_series_grouping_by_title_and_slug(self):
        import tempfile
        import os
        from database.db import init_db, get_or_create_series, add_or_update_chapter, get_all_series, get_chapters_for_series
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_grouping.db")
        init_db(db_path)

        # Simulate 3 chapters with different chapter-like slugs
        s1 = get_or_create_series(slug="ch1-328363", title="Ultra After", db_path=db_path)
        c1 = add_or_update_chapter(s1, 1.0, title="Chapter 1", db_path=db_path)

        s2 = get_or_create_series(slug="ch2-328364", title="Ultra After", db_path=db_path)
        c2 = add_or_update_chapter(s2, 2.0, title="Chapter 2", db_path=db_path)

        s3 = get_or_create_series(slug="ch3-328365", title="Ultra After", db_path=db_path)
        c3 = add_or_update_chapter(s3, 3.0, title="Chapter 3", db_path=db_path)

        # Must return the SAME series ID
        self.assertEqual(s1, s2)
        self.assertEqual(s2, s3)

        # Only 1 series card should exist
        all_s = get_all_series(db_path=db_path)
        self.assertEqual(len(all_s), 1)
        self.assertEqual(all_s[0]["id"], s1)
        self.assertEqual(all_s[0]["total_chapters"], 3)

        # All 3 chapters belong to s1
        chaps = get_chapters_for_series(s1, db_path=db_path)
        self.assertEqual(len(chaps), 3)

    def test_database_deduplication_migration(self):
        import tempfile
        import os
        import sqlite3
        from database.db import init_db, get_all_series, get_chapters_for_series
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_migration.db")

        # Manually create duplicate series as existed previously
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE series (id INTEGER PRIMARY KEY, title TEXT, slug TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE chapters (id INTEGER PRIMARY KEY, series_id INTEGER, chapter_num REAL, status TEXT DEFAULT 'completed', UNIQUE(series_id, chapter_num))")
        conn.execute("INSERT INTO series VALUES (1, 'Ultra After', 'ch1-100', CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO series VALUES (2, 'Ultra After', 'ch2-101', CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO series VALUES (3, 'Ultra After', 'ch3-102', CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO chapters (id, series_id, chapter_num) VALUES (10, 1, 1.0)")
        conn.execute("INSERT INTO chapters (id, series_id, chapter_num) VALUES (11, 2, 2.0)")
        conn.execute("INSERT INTO chapters (id, series_id, chapter_num) VALUES (12, 3, 3.0)")
        conn.commit()
        conn.close()

        # Running init_db must merge the 3 series into 1
        init_db(db_path)
        all_s = get_all_series(db_path=db_path)
        self.assertEqual(len(all_s), 1)
        self.assertEqual(all_s[0]["id"], 1)

        # All 3 chapters should now be under series 1
        chaps = get_chapters_for_series(1, db_path=db_path)
        self.assertEqual(len(chaps), 3)

if __name__ == "__main__":
    unittest.main()

