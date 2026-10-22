import os
import shutil
import tempfile
import unittest
from fastapi.testclient import TestClient

from app import app, download_queue_manager, DownloadRequest
from core.compiler import compile_pdf, compile_cbz, get_chapter_page_count, get_chapter_page_bytes, detect_file_format
from database.db import init_db, get_or_create_series, add_or_update_chapter, get_chapters_for_series

class TestDownloadQueueAndFormats(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        download_queue_manager.queue.clear()
        download_queue_manager.history.clear()
        download_queue_manager.active_job = None
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_queue.db")
        init_db(self.db_path)

    def tearDown(self):
        download_queue_manager.queue.clear()
        download_queue_manager.history.clear()
        download_queue_manager.active_job = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_series_queue_enqueue(self):
        # 1. Enqueue 3 chapters of Manhua A
        req_a = DownloadRequest(
            url="https://example.com/manhua_a/ch1",
            series_title="Manhua Alpha",
            chapter_urls=["https://example.com/manhua_a/ch1", "https://example.com/manhua_a/ch2", "https://example.com/manhua_a/ch3"],
            format="pdf"
        )
        job_a = download_queue_manager.enqueue(req_a)
        self.assertEqual(job_a["series_title"], "Manhua Alpha")
        self.assertEqual(job_a["total_chapters"], 3)
        self.assertEqual(job_a["format"], "pdf")

        # 2. Enqueue 2 chapters of Manhua B
        req_b = DownloadRequest(
            url="https://example.com/manhua_b/ch1",
            series_title="Manhua Beta",
            chapter_urls=["https://example.com/manhua_b/ch1", "https://example.com/manhua_b/ch2"],
            format="cbz"
        )
        job_b = download_queue_manager.enqueue(req_b)
        self.assertEqual(job_b["series_title"], "Manhua Beta")
        self.assertEqual(job_b["total_chapters"], 2)
        self.assertEqual(job_b["format"], "cbz")

        state = download_queue_manager.get_state()
        all_job_ids = [j["id"] for j in state["queue"]]
        if state["active_job"]:
            all_job_ids.insert(0, state["active_job"]["id"])

        self.assertIn(job_a["id"], all_job_ids)
        self.assertIn(job_b["id"], all_job_ids)

    def test_queue_pause_resume_cancel(self):
        req = DownloadRequest(url="https://example.com/series/ch1", series_title="Solo Level")
        job = download_queue_manager.enqueue(req)

        # Pause job
        self.assertTrue(download_queue_manager.pause_job(job["id"]))
        self.assertTrue(job.get("is_paused"))

        # Resume job
        self.assertTrue(download_queue_manager.resume_job(job["id"]))
        self.assertFalse(job.get("is_paused"))

        # Cancel job
        self.assertTrue(download_queue_manager.cancel_job(job["id"]))
        state = download_queue_manager.get_state()
        self.assertTrue(any(h["id"] == job["id"] and h["status"] == "cancelled" for h in state["history"]))

    def test_mixed_formats_pdf_and_cbz_coexistence(self):
        # 1x1 transparent/white JPEG byte
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGB", (100, 100), color="white")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        sample_panel = buf.getvalue()

        series_id = get_or_create_series("test-mixed-series", "Test Mixed Series", db_path=self.db_path)
        series_dir = os.path.join(self.temp_dir, "Test Mixed Series")
        os.makedirs(series_dir, exist_ok=True)

        # Chapter 1: PDF format
        pdf_path = os.path.join(series_dir, "test_mixed_series_Ch_1.pdf")
        self.assertTrue(compile_pdf([sample_panel], pdf_path))
        self.assertTrue(os.path.exists(pdf_path))
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=1.0,
            title="Chapter 1",
            file_path=pdf_path,
            file_format="pdf",
            file_size=os.path.getsize(pdf_path),
            status="completed",
            db_path=self.db_path
        )

        # Chapter 2: CBZ format
        cbz_path = os.path.join(series_dir, "test_mixed_series_Ch_2.cbz")
        self.assertTrue(compile_cbz([sample_panel], cbz_path, series_title="Test Mixed Series", chapter_num=2.0))
        self.assertTrue(os.path.exists(cbz_path))
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=2.0,
            title="Chapter 2",
            file_path=cbz_path,
            file_format="cbz",
            file_size=os.path.getsize(cbz_path),
            status="completed",
            db_path=self.db_path
        )

        # Verify database has both chapters with respective formats
        chaps = get_chapters_for_series(series_id, db_path=self.db_path)
        self.assertEqual(len(chaps), 2)
        ch1 = next(c for c in chaps if c["chapter_num"] == 1.0)
        ch2 = next(c for c in chaps if c["chapter_num"] == 2.0)
        self.assertEqual(ch1["file_format"], "pdf")
        self.assertEqual(ch2["file_format"], "cbz")

        # Verify page count and page extraction work for both
        self.assertEqual(get_chapter_page_count(ch1["file_path"], ch1["file_format"]), 1)
        self.assertEqual(get_chapter_page_count(ch2["file_path"], ch2["file_format"]), 1)
        self.assertIsNotNone(get_chapter_page_bytes(ch1["file_path"], ch1["file_format"], 0))
        self.assertIsNotNone(get_chapter_page_bytes(ch2["file_path"], ch2["file_format"], 0))

        # Test format detection resilience
        self.assertEqual(detect_file_format(pdf_path), "pdf")
        self.assertEqual(detect_file_format(cbz_path), "cbz")

    def test_overwriting_chapter_with_different_format(self):
        from PIL import Image
        from io import BytesIO
        img = Image.new("RGB", (100, 100), color="blue")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        sample_panel = buf.getvalue()

        series_id = get_or_create_series("test-overwrite-series", "Test Overwrite Series", db_path=self.db_path)
        series_dir = os.path.join(self.temp_dir, "Test Overwrite Series")
        os.makedirs(series_dir, exist_ok=True)

        # 1. Download Chapter 1 as PDF
        pdf_path = os.path.join(series_dir, "test_overwrite_series_Ch_1.pdf")
        self.assertTrue(compile_pdf([sample_panel], pdf_path))
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=1.0,
            title="Chapter 1",
            file_path=pdf_path,
            file_format="pdf",
            file_size=os.path.getsize(pdf_path),
            status="completed",
            db_path=self.db_path
        )
        self.assertTrue(os.path.exists(pdf_path))

        # 2. Re-download Chapter 1 as CBZ (overwriting format)
        cbz_path = os.path.join(series_dir, "test_overwrite_series_Ch_1.cbz")
        self.assertTrue(compile_cbz([sample_panel], cbz_path, series_title="Test Overwrite Series", chapter_num=1.0))
        # Simulate overwrite cleanup logic from app.py
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=1.0,
            title="Chapter 1",
            file_path=cbz_path,
            file_format="cbz",
            file_size=os.path.getsize(cbz_path),
            status="completed",
            db_path=self.db_path
        )

        chaps = get_chapters_for_series(series_id, db_path=self.db_path)
        self.assertEqual(len(chaps), 1)
        self.assertEqual(chaps[0]["file_format"], "cbz")
        self.assertTrue(os.path.exists(cbz_path))
        self.assertFalse(os.path.exists(pdf_path))

if __name__ == "__main__":
    unittest.main()

