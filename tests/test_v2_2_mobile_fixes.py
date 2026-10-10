import unittest
import os
import tempfile
from io import BytesIO
from PIL import Image

from core.compiler import compile_pdf, get_chapter_page_count, get_chapter_page_bytes
from core.optimizer import optimize_panel_image
from database.db import init_db, get_or_create_series, add_or_update_chapter, get_chapters_for_series, get_series_by_id


class TestV22MobileFixes(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_db.db")
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pure_python_pdf_page_counting_and_extraction(self):
        # Create 3 synthetic RGB images
        img_bytes_list = []
        for i in range(3):
            im = Image.new("RGB", (200, 300), color=(50 * i, 70, 90))
            buf = BytesIO()
            im.save(buf, format="JPEG")
            img_bytes_list.append(buf.getvalue())

        pdf_path = os.path.join(self.temp_dir.name, "chapter_test.pdf")
        ok = compile_pdf(img_bytes_list, pdf_path)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(pdf_path))

        # Test counting pages using pure Python fallback
        count = get_chapter_page_count(pdf_path, "pdf")
        self.assertEqual(count, 3)

        # Test extracting individual pages
        for idx in range(3):
            page_b = get_chapter_page_bytes(pdf_path, "pdf", idx)
            self.assertIsNotNone(page_b)
            self.assertTrue(len(page_b) > 100)
            # Ensure it is a valid JPEG
            test_im = Image.open(BytesIO(page_b))
            self.assertEqual(test_im.size, (200, 300))

    def test_optimizer_fallback_and_raw_bytes_preservation(self):
        # Create a sample image
        im = Image.new("RGB", (100, 100), color=(255, 0, 0))
        buf = BytesIO()
        im.save(buf, format="JPEG")
        raw = buf.getvalue()

        # Should optimize cleanly to JPEG
        opt_jpeg = optimize_panel_image(raw, max_width=1080, image_format="JPEG")
        self.assertIsNotNone(opt_jpeg)

        # In case of unrecognized bytes, raw bytes are safely preserved
        corrupted = b"NOT_A_REAL_IMAGE_HEADER_BYTES_JUST_SOME_RAW_STREAM_DATA" * 5
        recovered = optimize_panel_image(corrupted, image_format="JPEG")
        self.assertEqual(recovered, corrupted)

    def test_db_connection_closing_and_chapter_insert(self):
        # Test series registration
        s_id = get_or_create_series(
            slug="test-series",
            title="Test Series",
            db_path=self.db_path
        )
        self.assertIsInstance(s_id, int)

        # Test chapter insertion
        ch_id = add_or_update_chapter(
            series_id=s_id,
            chapter_num=1.0,
            title="Chapter 1",
            panel_count=20,
            file_format="pdf",
            status="completed",
            db_path=self.db_path
        )
        self.assertIsInstance(ch_id, int)

        # Verify series and chapter can be queried without locks
        series = get_series_by_id(s_id, db_path=self.db_path)
        self.assertIsNotNone(series)
        self.assertEqual(series["title"], "Test Series")

        chaps = get_chapters_for_series(s_id, db_path=self.db_path)
        self.assertEqual(len(chaps), 1)
        self.assertEqual(chaps[0]["chapter_num"], 1.0)
        self.assertEqual(chaps[0]["panel_count"], 20)


if __name__ == "__main__":
    unittest.main()

