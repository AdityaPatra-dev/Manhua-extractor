import unittest
from bs4 import BeautifulSoup
from extractors.comick import ComicKExtractor
from extractors.dispatcher import ExtractorDispatcher


class TestComicKExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = ComicKExtractor()
        self.dispatcher = ExtractorDispatcher()

    def test_can_handle_domains(self):
        soup = BeautifulSoup("<html></html>", "html.parser")
        self.assertTrue(self.extractor.can_handle(soup, "https://comick.live/comic/hero", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://comick.dev/comic/hero", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://comick.io/comic/hero", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://comick.app/comic/hero", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://comick.cc/comic/hero", ""))
        self.assertFalse(self.extractor.can_handle(soup, "https://mangadex.org/title/123", ""))

    def test_url_normalization(self):
        self.assertEqual(
            self.extractor._normalize_url("https://comick.dev/comic/hero"),
            "https://comick.live/comic/hero"
        )
        self.assertEqual(
            self.extractor._normalize_url("https://comick.io/comic/9hhgCPLV/Y7nG2-chapter-1-en"),
            "https://comick.live/comic/9hhgCPLV/Y7nG2-chapter-1-en"
        )

    def test_extract_pages_from_embedded_json(self):
        html = """
        <html><head>
        <script>
        {
            "chapter": {
                "images": [
                    {"url": "https://cdn1.comicknew.pictures/hero/0_1.0/en/c5428769/0.webp"},
                    {"url": "https://cdn1.comicknew.pictures/hero/0_1.0/en/c5428769/1.webp"},
                    {"url": "https://cdn1.comicknew.pictures/hero/covers/cover.webp"}
                ]
            }
        }
        </script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        pages = self.extractor.extract_pages(soup, "https://comick.live/comic/hero/ch1", html)
        self.assertEqual(len(pages), 2)
        self.assertIn("https://cdn1.comicknew.pictures/hero/0_1.0/en/c5428769/0.webp", pages)
        self.assertIn("https://cdn1.comicknew.pictures/hero/0_1.0/en/c5428769/1.webp", pages)
        self.assertNotIn("https://cdn1.comicknew.pictures/hero/covers/cover.webp", pages)

    def test_extract_series_info_from_embedded_json(self):
        html = """
        <html><head>
        <script>
        {
            "id": 12345,
            "title": "Hero",
            "slug": "hero",
            "desc": "A legendary hero story.",
            "default_thumbnail": "https://cdn1.comicknew.pictures/hero/covers/cover.webp",
            "firstChapters": [
                {
                    "chap": "1",
                    "hid": "Y7nG2",
                    "lang": "en",
                    "title": "Prologue"
                }
            ]
        }
        </script>
        </head><body></body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        info = self.extractor.extract_series_info(soup, "https://comick.live/comic/hero", html)
        self.assertEqual(info.get("title"), "Hero")
        self.assertEqual(info.get("slug"), "hero")
        self.assertEqual(info.get("synopsis"), "A legendary hero story.")
        self.assertEqual(info.get("cover_url"), "https://cdn1.comicknew.pictures/hero/covers/cover.webp")


if __name__ == "__main__":
    unittest.main()
