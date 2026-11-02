import unittest
from bs4 import BeautifulSoup
from extractors.vortexscans import VortexScansExtractor
from extractors.dispatcher import ExtractorDispatcher


class TestVortexScansExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = VortexScansExtractor()
        self.dispatcher = ExtractorDispatcher()

    def test_can_handle_domains(self):
        soup = BeautifulSoup("<html></html>", "html.parser")
        self.assertTrue(self.extractor.can_handle(soup, "https://vortexscans.org/series/the-legendary-mechanic", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://vortexcomics.org/series/the-legendary-mechanic", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://vortextoon.com/series/the-legendary-mechanic", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://vortexscans.io/series/the-legendary-mechanic", ""))
        self.assertTrue(self.extractor.can_handle(soup, "https://vortexscans.com/series/the-legendary-mechanic", ""))
        self.assertFalse(self.extractor.can_handle(soup, "https://asuracomic.net/series/solo", ""))

    def test_dispatcher_matches_vortexscans(self):
        url = "https://vortexscans.org/series/overpowered-sword/chapter-1"
        html = "<html><body><p>Vortex Scans</p></body></html>"
        soup = BeautifulSoup(html, "html.parser")
        engine = self.dispatcher.match_engine(soup, url, html)
        self.assertIsNotNone(engine)
        self.assertEqual(engine.engine_id, "vortexscans")

    def test_url_normalization(self):
        self.assertEqual(
            self.extractor._normalize_url("https://vortextoon.com/series/mechanic"),
            "https://vortexscans.org/series/mechanic"
        )
        self.assertEqual(
            self.extractor._normalize_url("https://vortexcomics.org/series/mechanic/chapter-10"),
            "https://vortexscans.org/series/mechanic/chapter-10"
        )

    def test_extract_series_info(self):
        html = """
        <html><head>
          <meta property="og:title" content="The Legendary Mechanic - Vortex Scans">
          <meta property="og:description" content="Han Xiao wakes up in the body of an NPC.">
          <meta property="og:image" content="https://storage.vortexscans.org/public/upload/series/featured/cover.webp">
        </head><body>
          <h1>The Legendary Mechanic - Vortex Scans</h1>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        info = self.extractor.extract_series_info(soup, "https://vortexscans.org/series/the-legendary-mechanic", html)
        self.assertEqual(info.get("title"), "The Legendary Mechanic")
        self.assertEqual(info.get("synopsis"), "Han Xiao wakes up in the body of an NPC.")
        self.assertEqual(info.get("cover_url"), "https://storage.vortexscans.org/public/upload/series/featured/cover.webp")

    def test_extract_chapter_list_identifies_locked_chapters(self):
        html = """
        <html><body>
          <div class="chapter-item">
            <a href="/series/mechanic/chapter-1">Chapter 1</a>
          </div>
          <div class="chapter-item">
            <a href="/series/mechanic/chapter-5" class="locked">
              <svg><path d="M12 1.5a5.25 5.25v3"></path></svg>
              Chapter 5
            </a>
          </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        chaps = self.extractor.extract_chapter_list(soup, "https://vortexscans.org/series/mechanic", html)
        self.assertEqual(len(chaps), 2)
        # Chapter 1 free
        self.assertFalse(chaps[0].get("is_locked"))
        self.assertNotIn("[Locked", chaps[0]["title"])
        # Chapter 5 locked
        self.assertTrue(chaps[1].get("is_locked"))
        self.assertIn("[Locked", chaps[1]["title"])

    def test_extract_pages_rejects_locked_chapters(self):
        """Locked chapter pages must return 0 panels rather than 2 random thumbnails/logos."""
        locked_html = """
        <html><body>
          <h3>Mechanic Chapter 5</h3>
          <p>Cost to Unlock: 50 coins</p>
          <p>Sign in to unlock this chapter.</p>
          <img src="https://storage.vortexscans.org/public/upload/series/featured/thumb.webp">
          <img src="https://vortexscans.org/assets/logo.png">
        </body></html>
        """
        soup = BeautifulSoup(locked_html, "html.parser")
        pages = self.extractor.extract_pages(soup, "https://vortexscans.org/series/mechanic/chapter-5", locked_html)
        self.assertEqual(pages, [])

    def test_extract_pages_extracts_free_panels_and_excludes_site_assets(self):
        """Free chapters must extract all comic panels and filter out logo, discord, and promo covers."""
        free_html = """
        <html><body>
          <img src="https://vortexscans.org/assets/logo.png">
          <img src="https://vortexscans.org/assets/discord-banner.jpg">
          <img src="https://storage.vortexscans.org/public/upload/series/featured/banner.webp">
          <div class="reading-content">
            <img src="https://storage.vortexscans.org/public/upload/series/mechanic/ch1/001.webp">
            <img src="https://storage.vortexscans.org/public/upload/series/mechanic/ch1/002.webp">
            <img src="https://storage.vortexscans.org/public/upload/series/mechanic/ch1/003.webp">
          </div>
          <img src="https://storage.vortexscans.org/public/upload/settings/footer.png">
        </body></html>
        """
        soup = BeautifulSoup(free_html, "html.parser")
        pages = self.extractor.extract_pages(soup, "https://vortexscans.org/series/mechanic/chapter-1", free_html)
        self.assertEqual(len(pages), 3)
        self.assertEqual(pages[0], "https://storage.vortexscans.org/public/upload/series/mechanic/ch1/001.webp")
        self.assertEqual(pages[1], "https://storage.vortexscans.org/public/upload/series/mechanic/ch1/002.webp")
        self.assertEqual(pages[2], "https://storage.vortexscans.org/public/upload/series/mechanic/ch1/003.webp")

    def test_extract_pages_prevents_2_random_images_fallback(self):
        """If only 2 random images (cover + logo) exist in the page, extractor rejects them."""
        bogus_html = """
        <html><body>
          <img src="https://vortexscans.org/assets/logo.png">
          <img src="https://storage.vortexscans.org/public/upload/series/featured/cover.webp">
        </body></html>
        """
        soup = BeautifulSoup(bogus_html, "html.parser")
        pages = self.extractor.extract_pages(soup, "https://vortexscans.org/series/mechanic/chapter-1", bogus_html)
        self.assertEqual(pages, [])


if __name__ == "__main__":
    unittest.main()

