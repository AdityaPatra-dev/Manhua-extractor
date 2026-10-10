import os
import sys
import unittest
import tempfile
import shutil
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from extractors.base import BaseExtractor
from extractors.dispatcher import dispatcher
from database.db import (
    init_db,
    get_or_create_series,
    add_or_update_chapter,
    get_downloaded_chapters_map
)


class DummyExtractor(BaseExtractor):
    def can_handle(self, soup, url, html):
        return True
    def extract_pages(self, soup, url, html):
        return []
    def extract_next_chapter(self, soup, current_url):
        return None


class TestStep1SeriesInspector(unittest.TestCase):
    def setUp(self):
        self.extractor = DummyExtractor()
        self.test_dir = tempfile.mkdtemp(prefix="manhua_test_step1_")
        self.db_path = os.path.join(self.test_dir, "test_library.db")
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_extract_chapter_list_from_select(self):
        """Should accurately extract all chapters from reader <select> element."""
        mock_html = """
        <html>
            <body>
                <select class="single-chapter-select">
                    <option value="https://example.com/series/chapter-1">Chapter 1 - The Start</option>
                    <option value="https://example.com/series/chapter-2">Chapter 2</option>
                    <option value="https://example.com/series/chapter-3.5">Chapter 3.5 - Side Story</option>
                    <option value="#">Select Chapter</option>
                </select>
            </body>
        </html>
        """
        soup = BeautifulSoup(mock_html, "html.parser")
        chapters = self.extractor.extract_chapter_list(soup, "https://example.com/series/chapter-1", mock_html)

        self.assertEqual(len(chapters), 3)
        self.assertEqual(chapters[0]["chapter_num"], 1.0)
        self.assertEqual(chapters[1]["chapter_num"], 2.0)
        self.assertEqual(chapters[2]["chapter_num"], 3.5)
        self.assertEqual(chapters[2]["title"], "Chapter 3.5 - Side Story")

    def test_extract_chapter_list_from_links(self):
        """Should extract chapters from <a> tags and sort logically."""
        mock_html = """
        <html>
            <body>
                <div class="eplister">
                    <ul>
                        <li><a href="/manga/solo/chapter-20/">Chapter 20</a></li>
                        <li><a href="/manga/solo/chapter-1/">Chapter 1</a></li>
                        <li><a href="/manga/solo/chapter-5/">Chapter 5</a></li>
                    </ul>
                </div>
            </body>
        </html>
        """
        soup = BeautifulSoup(mock_html, "html.parser")
        chapters = self.extractor.extract_chapter_list(soup, "https://example.com/manga/solo/", mock_html)

        self.assertEqual(len(chapters), 3)
        # Verify logical ascending sort order
        self.assertEqual(chapters[0]["chapter_num"], 1.0)
        self.assertEqual(chapters[1]["chapter_num"], 5.0)
        self.assertEqual(chapters[2]["chapter_num"], 20.0)

    def test_cross_reference_local_downloaded_chapters(self):
        """Database helper should accurately mark downloaded chapters in catalog."""
        # 1. Create series and insert chapter 1 as completed
        series_id = get_or_create_series(
            slug="solo-leveling",
            title="Solo Leveling",
            cover_url="https://example.com/cover.jpg",
            source_url="https://example.com/manga/solo",
            db_path=self.db_path
        )
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=1.0,
            title="Chapter 1",
            source_url="https://example.com/manga/solo/chapter-1",
            panel_count=20,
            file_path="/downloads/Solo Leveling/Ch_1.cbz",
            file_format="cbz",
            file_size=1048576,
            status="completed",
            db_path=self.db_path
        )

        # 2. Query map
        dl_map = get_downloaded_chapters_map("Solo Leveling", db_path=self.db_path)
        self.assertIn(1.0, dl_map)
        self.assertNotIn(2.0, dl_map)
        self.assertEqual(dl_map[1.0]["status"], "completed")
        self.assertEqual(dl_map[1.0]["file_format"], "cbz")


if __name__ == "__main__":
    unittest.main()
