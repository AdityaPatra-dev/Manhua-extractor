import unittest
from bs4 import BeautifulSoup
from extractors.hivescans import HiveScansExtractor


class TestHiveScansExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = HiveScansExtractor()

    def test_can_handle_domains(self):
        soup = BeautifulSoup("<html></html>", "html.parser")
        self.assertTrue(self.extractor.can_handle(soup, "https://void-scans.com/series/crocodile", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://voidscans.com/series/crocodile", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://hivescans.com/series/crocodile", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://hivetoons.org/series/crocodile", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://hivetoon.com/series/crocodile", ""))
        self.assertFalse(self.extractor.can_handle(soup, "https://asuracomic.net/series/solo", ""))

    def test_url_normalization(self):
        self.assertEqual(
            self.extractor._normalize_url("https://void-scans.com/series/crocodile"),
            "https://hivetoons.org/series/crocodile"
        )
        self.assertEqual(
            self.extractor._normalize_url("https://hivescans.com/series/crocodile/chapter-24"),
            "https://hivetoons.org/series/crocodile/chapter-24"
        )

    def test_extract_series_info(self):
        html = """
        <html><head>
          <meta property="og:title" content="Crocodile - Hive Toon">
          <meta property="og:description" content="A dark crime action webtoon.">
          <meta property="og:image" content="https://storage.hivetoon.com/public/upload/series/featured/banner.webp">
        </head><body>
          <h1>Crocodile</h1>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        info = self.extractor.extract_series_info(soup, "https://hivetoons.org/series/crocodile", html)
        self.assertEqual(info.get("title"), "Crocodile")
        self.assertEqual(info.get("synopsis"), "A dark crime action webtoon.")
        self.assertEqual(info.get("cover_url"), "https://storage.hivetoon.com/public/upload/series/featured/banner.webp")

    def test_extract_chapter_list_identifies_locked_chapters(self):
        html = """
        <html><body>
          <div class="chapter-item">
            <a href="/series/crocodile/chapter-24">Chapter 24</a>
          </div>
          <div class="chapter-item">
            <a href="/series/crocodile/chapter-28">
              <svg><path d="M12 1.5a5.25 5.25v3"></path></svg>
              Chapter 28
            </a>
          </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        chaps = self.extractor.extract_chapter_list(soup, "https://hivetoons.org/series/crocodile", html)
        self.assertEqual(len(chaps), 2)
        # Chapter 24 should be free
        self.assertFalse(chaps[0].get("is_locked"))
        self.assertNotIn("[Locked", chaps[0]["title"])
        # Chapter 28 should be identified as locked
        self.assertTrue(chaps[1].get("is_locked"))
        self.assertIn("[Locked", chaps[1]["title"])

    def test_extract_pages_rejects_locked_chapters(self):
        """Locked chapter pages must return 0 panels (not 1-2 random covers/avatars)."""
        locked_html = """
        <html><body>
          <h3>crocodile Chapter 28</h3>
          <p>Cost to Unlock: 40 coins</p>
          <p>Sign in to unlock this exciting chapter and continue your journey.</p>
          <img src="https://page-images.kakaoentcdn.com/download/resource?kid=avatar" class="h-10 w-10">
          <img src="https://storage.hivetoon.com/public/upload/series/featured/banner.webp">
        </body></html>
        """
        soup = BeautifulSoup(locked_html, "html.parser")
        pages = self.extractor.extract_pages(soup, "https://hivetoons.org/series/crocodile/chapter-28", locked_html)
        self.assertEqual(pages, [])

    def test_extract_pages_extracts_free_panels_and_excludes_ads(self):
        """Free chapters must extract only real comic panels, filtering avatars and promo banners."""
        free_html = """
        <html><body>
          <img src="https://page-images.kakaoentcdn.com/avatar.jpg" class="h-10 w-10">
          <img src="https://storage.hivetoon.com/public/upload/series/featured/promo.webp">
          <img src="https://storage.hivetoon.com/public/upload/series/crocodile/123/page-001.webp">
          <img src="https://storage.hivetoon.com/public/upload/series/crocodile/123/page-002.webp">
          <img src="https://storage.hivetoon.com/public/upload/settings/logo.png">
        </body></html>
        """
        soup = BeautifulSoup(free_html, "html.parser")
        pages = self.extractor.extract_pages(soup, "https://hivetoons.org/series/crocodile/chapter-24", free_html)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0], "https://storage.hivetoon.com/public/upload/series/crocodile/123/page-001.webp")
        self.assertEqual(pages[1], "https://storage.hivetoon.com/public/upload/series/crocodile/123/page-002.webp")


if __name__ == "__main__":
    unittest.main()
