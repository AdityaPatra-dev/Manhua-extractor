import unittest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from extractors.hitomi import HitomiExtractor
from extractors.dispatcher import ExtractorDispatcher
from core.search.dispatcher import SearchDispatcher, TIER_1_SOURCES


class TestHitomiExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = HitomiExtractor()

    def test_can_handle(self):
        soup = BeautifulSoup("", "html.parser")
        self.assertTrue(self.extractor.can_handle(soup, "https://hitomi.la/reader/4280659.html#1", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://hitomi.la/manga/banshuel-4280659.html", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://hitomi.la/doujinshi/adventure-123456.html", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://hitomi.la/galleries/987654.html", ""))
        self.assertFalse(self.extractor.can_handle(soup, "https://asuracomic.net/manga/solo-leveling", ""))
        self.assertFalse(self.extractor.can_handle(soup, "https://mangadex.org/title/123", ""))

    def test_extract_gallery_id(self):
        self.assertEqual(self.extractor.extract_gallery_id("https://hitomi.la/reader/4280659.html#1"), 4280659)
        self.assertEqual(self.extractor.extract_gallery_id("https://hitomi.la/reader/4280659.html"), 4280659)
        self.assertEqual(self.extractor.extract_gallery_id("https://hitomi.la/manga/test-title-4280659.html"), 4280659)
        self.assertEqual(self.extractor.extract_gallery_id("https://hitomi.la/doujinshi/sample-work-998877.html?lang=en"), 998877)
        self.assertEqual(self.extractor.extract_gallery_id("https://hitomi.la/galleries/112233.html"), 112233)
        self.assertIsNone(self.extractor.extract_gallery_id("https://hitomi.la/"))
        self.assertIsNone(self.extractor.extract_gallery_id(""))

    def test_build_thumbnail_url(self):
        h = "b1eafd1bdf8359e2ab86cfdbdb1d26b87ceffee29fed50c9ef991b8ac9903a07"
        tn_url = self.extractor.build_thumbnail_url(h)
        self.assertTrue(tn_url.startswith("https://atn.gold-usergeneratedcontent.net/webpbigtn/"))
        self.assertTrue(tn_url.endswith(f"/7/a0/{h}.webp"))

    def test_build_image_url(self):
        h = "b1eafd1bdf8359e2ab86cfdbdb1d26b87ceffee29fed50c9ef991b8ac9903a07"
        img_url = self.extractor.build_image_url(h, ext="webp")
        self.assertIn("gold-usergeneratedcontent.net", img_url)
        self.assertIn(f"/1952/{h}.webp", img_url)
        self.assertTrue(img_url.startswith("https://w1.") or img_url.startswith("https://w2."))

    @patch.object(HitomiExtractor, "fetch_gallery_info")
    def test_extract_series_info_and_chapters(self, mock_fetch):
        mock_fetch.return_value = {
            "id": 4280659,
            "title": "Sample Hitomi Gallery",
            "japanese_title": "サンプル",
            "type": "doujinshi",
            "language": "english",
            "artists": [{"artist": "FamousArtist"}],
            "parodys": [{"parody": "Original"}],
            "tags": [{"tag": "comedy"}, {"tag": "school"}],
            "files": [
                {"name": "01.jpg", "hash": "aaaabbbbccccdddd111122223333444455556666777788889999aaaabbbb0a07", "haswebp": 1},
                {"name": "02.jpg", "hash": "bbbbccccddddeeee111122223333444455556666777788889999aaaabbbb1b08", "haswebp": 1}
            ]
        }

        soup = BeautifulSoup("", "html.parser")
        url = "https://hitomi.la/reader/4280659.html"

        info = self.extractor.extract_series_info(soup, url, "")
        self.assertEqual(info["title"], "Sample Hitomi Gallery")
        self.assertEqual(info["slug"], "hitomi-4280659")
        self.assertEqual(info["author"], "FamousArtist")
        self.assertIn("Type: Doujinshi", info["description"])
        self.assertIn("Tags: comedy, school", info["description"])

        chapters = self.extractor.extract_chapter_list(soup, url, "")
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0]["chapter_num"], 1.0)
        self.assertEqual(chapters[0]["title"], "Complete (2 Pages)")
        self.assertEqual(chapters[0]["url"], "https://hitomi.la/reader/4280659.html")

        pages = self.extractor.extract_pages(soup, url, "")
        self.assertEqual(len(pages), 2)
        self.assertTrue(pages[0].endswith(".webp"))
        self.assertTrue(pages[1].endswith(".webp"))

    def test_dispatcher_includes_hitomi(self):
        dispatcher = ExtractorDispatcher()
        engine_ids = [e.engine_id for e in dispatcher.engines]
        self.assertIn("hitomi", engine_ids)

        tier1_keys = [s["key"] for s in TIER_1_SOURCES]
        self.assertIn("hitomi", tier1_keys)


if __name__ == "__main__":
    unittest.main()
