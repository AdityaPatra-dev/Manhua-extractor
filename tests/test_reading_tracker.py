import unittest
import os
import tempfile
import sqlite3
from database.db import (
    init_db,
    get_or_create_series,
    add_or_update_chapter,
    update_reading_progress,
    get_all_series,
    get_series_by_id
)
from core.metadata import titles_match

class TestReadingTrackerAndMetadata(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_library.db")
        init_db(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_resume_chapter_tracking(self):
        # 1. Create series
        s_id = get_or_create_series(
            slug="test-manhua",
            title="Test Manhua",
            source_url="https://example.com/test-manhua/ch1",
            db_path=self.db_path
        )

        # Add 3 chapters
        c1 = add_or_update_chapter(s_id, 1.0, title="Chapter 1", status="completed", db_path=self.db_path)
        c2 = add_or_update_chapter(s_id, 2.0, title="Chapter 2", status="completed", db_path=self.db_path)
        c3 = add_or_update_chapter(s_id, 3.0, title="Chapter 3", status="completed", db_path=self.db_path)

        # Before any reading: resume should be first chapter (Chapter 1)
        all_s = get_all_series(db_path=self.db_path)
        self.assertEqual(len(all_s), 1)
        self.assertEqual(all_s[0]["resume_chapter_id"], c1)
        self.assertEqual(all_s[0]["resume_chapter_num"], 1.0)

        # User reads chapter 2 (read_status = 1, page = 5)
        update_reading_progress(c2, 1, 5, db_path=self.db_path)
        all_s = get_all_series(db_path=self.db_path)
        self.assertEqual(all_s[0]["resume_chapter_id"], c2)
        self.assertEqual(all_s[0]["resume_chapter_num"], 2.0)
        self.assertEqual(all_s[0]["last_read_page"], 5)

        # User completes chapter 2 (read_status = 2) -> resume should jump to chapter 3
        update_reading_progress(c2, 2, 10, db_path=self.db_path)
        all_s = get_all_series(db_path=self.db_path)
        self.assertEqual(all_s[0]["resume_chapter_id"], c3)
        self.assertEqual(all_s[0]["resume_chapter_num"], 3.0)

        # Also verify get_series_by_id
        detail = get_series_by_id(s_id, db_path=self.db_path)
        self.assertEqual(detail["resume_chapter_id"], c3)
        self.assertEqual(detail["source_url"], "https://example.com/test-manhua/ch1")

    def test_titles_match_validation(self):
        # Exact and alternate titles should match
        self.assertTrue(titles_match("Island of Stars and Chains", "Island of Stars and Chains"))
        self.assertTrue(titles_match("Island of Stars and Chains", "Other Title", ["The Island Where Stars and Chains Rise"]))
        self.assertTrue(titles_match("The Island Where Stars and Chains Rise", "Island of Stars and Chains"))

        # Completely unrelated manga should NOT match
        self.assertFalse(titles_match("Island of Stars and Chains", "Moto Kyuutei Renkinjutsushi no Watashi"))
        self.assertFalse(titles_match("Island of Stars and Chains", "Solo Leveling"))
        self.assertFalse(titles_match("Island of Stars and Chains", "One Step Divine Fist"))

    def test_resolve_cover_from_search_cache(self):
        from core.search.clustering import resolve_cover_from_search
        from database.db import set_cached_search

        # Mock search cluster in test DB
        mock_cluster = [{
            "canonical_title": "Island of Stars and Chains",
            "title": "Island of Stars and Chains",
            "cover_url": "https://arenascan.com/covers/island.webp",
            "sources": []
        }]
        set_cached_search("island of stars and chains", mock_cluster, db_path=self.db_path)

        resolved = resolve_cover_from_search("Island of Stars and Chains", db_path=self.db_path)
        self.assertEqual(resolved, "https://arenascan.com/covers/island.webp")

    def test_chapter_number_extraction_with_trailing_slash(self):
        from extractors.dispatcher import dispatcher
        extractor = dispatcher.engines[-1]  # Heuristic / base extractor
        
        self.assertEqual(extractor.extract_chapter_number("https://arenascan.com/island-of-stars-and-chains-1/"), 1.0)
        self.assertEqual(extractor.extract_chapter_number("https://arenascan.com/island-of-stars-and-chains-2/"), 2.0)
        self.assertEqual(extractor.extract_chapter_number("https://arenascan.com/island-of-stars-and-chains-3/"), 3.0)
        self.assertEqual(extractor.extract_chapter_number("https://example.com/manga/solo/chapter-10.5/"), 10.5)

        # Test FanFox and aggregator date formatted titles
        self.assertEqual(extractor.extract_chapter_number("https://fanfox.net/manga/slug/c015/1.html", "Ch.015 Sep 01,2021"), 15.0)
        self.assertEqual(extractor.extract_chapter_number("https://fanfox.net/manga/slug/c132/1.html", "Ch.132 Sep 07,2024"), 132.0)
        self.assertEqual(extractor.extract_chapter_number("https://fanfox.net/manga/slug/c169/1.html", "Ch.169 Feb 12,2026"), 169.0)
        self.assertEqual(extractor.extract_chapter_number("https://fanfox.net/manga/slug/c207/1.html", "Ch.207 Oct 15,2026"), 207.0)
        self.assertEqual(extractor.extract_chapter_number("https://ravenscans.org/manga/slug-chapter-1/", "Chapter 1"), 1.0)
        self.assertEqual(extractor.extract_chapter_number("https://ravenscans.org/manga/slug-chapter-202/", "Chapter 202"), 202.0)

    def test_next_chapter_heuristic_increment(self):
        from extractors.heuristic import HeuristicExtractor
        h = HeuristicExtractor()
        next_url = h.extract_next_chapter(None, "https://arenascan.com/island-of-stars-and-chains-1/")
        self.assertEqual(next_url, "https://arenascan.com/island-of-stars-and-chains-2/")

        next_url2 = h.extract_next_chapter(None, "https://example.com/manga/title-ch-5")
        self.assertEqual(next_url2, "https://example.com/manga/title-ch-6")

if __name__ == "__main__":
    unittest.main()


