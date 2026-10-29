import os
import sys
import unittest
import tempfile
import shutil
import xml.etree.ElementTree as ET

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import (
    init_db,
    get_or_create_series,
    get_series_by_id,
    update_series_rich_metadata
)
from core.metadata import (
    clean_search_title,
    fetch_mangadex_metadata,
    fetch_rich_metadata,
    generate_rich_comicinfo
)
from extractors.browser_sidecar import (
    is_flaresolverr_available,
    solve_with_flaresolverr
)


class TestV20Features(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="manhua_test_v20_")
        self.db_path = os.path.join(self.test_dir, "test_library.db")
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_search_title(self):
        """Title sanitizer should strip noisy aggregator and taxonomy keywords."""
        self.assertEqual(clean_search_title("Solo Leveling Chapter 150 [Official Scan]"), "Solo Leveling")
        self.assertEqual(clean_search_title("Martial Peak (Manhua) Season 2"), "Martial Peak")

    def test_mangadex_metadata_scraping(self):
        """MangaDex API should return rich author, artist, tags, and synopsis."""
        meta = fetch_mangadex_metadata("Solo Leveling")
        if meta is None:
            self.skipTest("MangaDex API unreachable in current test environment")
        self.assertIsNotNone(meta)
        self.assertTrue(len(meta["title"]) > 0)
        self.assertIn("Action", meta.get("genres", []) + meta.get("tags", []))
        self.assertIsNotNone(meta.get("synopsis"))
        self.assertTrue(len(meta["synopsis"]) > 10)
        self.assertIsNotNone(meta.get("age_rating"))

    def test_rich_comicinfo_generation(self):
        """Generated ComicInfo.xml must be valid XML with standard ComicRack/Komga tags."""
        dummy_meta = {
            "title": "Tower of God",
            "author": "SIU",
            "artist": "SIU",
            "genres": ["Action", "Fantasy", "Mystery"],
            "tags": ["Tower", "Floor", "Shinsu"],
            "synopsis": "What do you desire? Money and wealth? Honor and pride? Power and influence?",
            "status": "Ongoing",
            "year": 2010,
            "age_rating": "Teen"
        }

        xml_str = generate_rich_comicinfo(
            metadata=dummy_meta,
            chapter_num=45.0,
            chapter_title="Chapter 45",
            page_count=28,
            source_url="https://example.com/ch45"
        )

        self.assertIn("<Series>Tower of God</Series>", xml_str)
        self.assertIn("<Writer>SIU</Writer>", xml_str)
        self.assertIn("<Penciller>SIU</Penciller>", xml_str)
        self.assertIn("<Genre>Action, Fantasy, Mystery</Genre>", xml_str)
        self.assertIn("<Year>2010</Year>", xml_str)
        self.assertIn("<Manga>YesAndRightToLeft</Manga>", xml_str)
        self.assertIn("<Format>Digital</Format>", xml_str)

        # Validate XML parsability
        root = ET.fromstring(xml_str)
        self.assertEqual(root.tag, "ComicInfo")
        self.assertEqual(root.find("Number").text, "45")

    def test_database_rich_metadata_caching(self):
        """Rich metadata should persist cleanly in SQLite series record."""
        series_id = get_or_create_series(
            slug="omniscient-reader",
            title="Omniscient Reader's Viewpoint",
            db_path=self.db_path
        )

        sample_meta = {
            "author": "sing N song",
            "artist": "Sleepy-C",
            "synopsis": "Only I know the end of this world.",
            "genres": ["Action", "Apocalypse", "Fantasy"],
            "tags": ["Constellation", "Scenario"],
            "year": 2020,
            "status": "Ongoing",
            "mangadex_id": "md-12345"
        }

        update_series_rich_metadata(series_id, sample_meta, db_path=self.db_path)
        updated = get_series_by_id(series_id, db_path=self.db_path)

        self.assertEqual(updated["author"], "sing N song")
        self.assertEqual(updated["artist"], "Sleepy-C")
        self.assertIn("Apocalypse", updated["genres"])
        self.assertEqual(updated["year"], 2020)

    def test_flaresolverr_sidecar_graceful_handling(self):
        """FlareSolverr detector should handle unreachable endpoints gracefully without crashing."""
        # Bogus port to guarantee unreachable
        is_up = is_flaresolverr_available("http://127.0.0.1:59999/v1")
        self.assertFalse(is_up)

        res = solve_with_flaresolverr("https://example.com", endpoint="http://127.0.0.1:59999/v1", max_timeout=1000)
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
