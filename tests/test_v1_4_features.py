import os
import sys
import unittest
import tempfile
import shutil
from io import BytesIO
from PIL import Image, ImageDraw

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import (
    init_db,
    add_promo_signature,
    get_all_promo_signatures,
    delete_promo_signature
)
from core.ad_filter import (
    compute_perceptual_hash,
    hash_distance,
    match_promo_signature,
    filter_chapter_panels
)
from core.scrobbler import (
    verify_anilist_token,
    verify_mal_token,
    search_anilist_manga
)


class TestV14Features(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="manhua_test_v14_")
        self.db_path = os.path.join(self.test_dir, "test_library.db")
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_image(self, width: int, height: int, pattern: str = "promo") -> bytes:
        im = Image.new("RGB", (width, height), (255, 255, 255))
        d = ImageDraw.Draw(im)
        if pattern == "promo":
            d.rectangle([0, 0, width, height // 3], fill=(255, 0, 0))
            d.rectangle([0, 2 * height // 3, width, height], fill=(0, 0, 255))
        elif pattern == "story1":
            d.rectangle([width // 4, height // 4, 3 * width // 4, 3 * height // 4], fill=(0, 200, 100))
        elif pattern == "story2":
            d.rectangle([0, height // 3, width, 2 * height // 3], fill=(180, 80, 200))
        buf = BytesIO()
        im.save(buf, format="JPEG")
        return buf.getvalue()

    def test_perceptual_hash_scale_invariance(self):
        """Perceptual hash should be invariant to image scaling and resolution."""
        raw_promo_highres = self._create_test_image(1080, 1600, pattern="promo")
        raw_promo_lowres = self._create_test_image(540, 800, pattern="promo")
        raw_comic_panel = self._create_test_image(1080, 1600, pattern="story1")

        h_high = compute_perceptual_hash(raw_promo_highres)
        h_low = compute_perceptual_hash(raw_promo_lowres)
        h_comic = compute_perceptual_hash(raw_comic_panel)

        self.assertIsNotNone(h_high)
        self.assertIsNotNone(h_low)
        self.assertIsNotNone(h_comic)
        self.assertEqual(len(h_high), 32)

        # Distance between scaled variants of promo should be very small (<= 4)
        dist_promo = hash_distance(h_high, h_low)
        # Distance between promo and comic panel should be high (> 20)
        dist_diff = hash_distance(h_high, h_comic)

        self.assertLessEqual(dist_promo, 4)
        self.assertGreater(dist_diff, 20)

    def test_database_promo_signatures(self):
        """Test adding, querying, and deleting promo signatures in SQLite."""
        raw_promo = self._create_test_image(800, 1200, pattern="promo")
        phash = compute_perceptual_hash(raw_promo)

        sig_id = add_promo_signature(phash=phash, label="Asura Watermark", match_threshold=8, db_path=self.db_path)
        self.assertGreater(sig_id, 0)

        sigs = get_all_promo_signatures(db_path=self.db_path)
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0]["label"], "Asura Watermark")
        self.assertEqual(sigs[0]["phash"], phash)

        deleted = delete_promo_signature(sig_id, db_path=self.db_path)
        self.assertTrue(deleted)
        sigs_after = get_all_promo_signatures(db_path=self.db_path)
        self.assertEqual(len(sigs_after), 0)

    def test_filter_chapter_panels(self):
        """Verify that filter_chapter_panels removes matching promos and retains story pages."""
        promo_img = self._create_test_image(800, 1200, pattern="promo")
        promo_hash = compute_perceptual_hash(promo_img)

        story_page_1 = self._create_test_image(800, 1200, pattern="story1")
        story_page_2 = self._create_test_image(800, 1200, pattern="story2")

        # Panel list: [Promo, Story 1, Story 2, Promo]
        panels = [promo_img, story_page_1, story_page_2, promo_img]
        known_sigs = [{"id": 1, "phash": promo_hash, "match_threshold": 8, "label": "Promo"}]

        cleaned, removed = filter_chapter_panels(panels, known_signatures=known_sigs)
        self.assertEqual(removed, 2)
        self.assertEqual(len(cleaned), 2)

    def test_tracker_validation_and_search(self):
        """Verify tracker validation error handling and live search."""
        # Invalid token rejection
        anilist_res = verify_anilist_token("invalid_token_12345")
        self.assertFalse(anilist_res["success"])

        mal_res = verify_mal_token("invalid_mal_token_12345")
        self.assertFalse(mal_res["success"])

        # Live metadata search on AniList (public unauthenticated endpoint, may rate-limit with 429)
        found = search_anilist_manga("Solo Leveling")
        if found is not None:
            self.assertEqual(found["id"], 105398)
            self.assertIn("Solo Leveling", [found["title"], found.get("romaji")])


if __name__ == "__main__":
    unittest.main()
