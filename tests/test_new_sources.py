import unittest
from bs4 import BeautifulSoup
from extractors.comicland import ComicLandExtractor
from extractors.manhwa18 import Manhwa18Extractor
from extractors.heuristic import HeuristicExtractor
from core.search.dispatcher import search_dispatcher, TIER_2_MADARA


class TestNewSources(unittest.TestCase):
    def test_comicland_can_handle(self):
        ext = ComicLandExtractor()
        soup = BeautifulSoup("<html></html>", "html.parser")
        self.assertTrue(ext.can_handle(soup, "https://comicland.org/comic/some-series"))
        self.assertFalse(ext.can_handle(soup, "https://manga18fx.com/manga/some-series"))

    def test_manhwa18_can_handle(self):
        ext = Manhwa18Extractor()
        soup = BeautifulSoup("<html></html>", "html.parser")
        self.assertTrue(ext.can_handle(soup, "https://manhwa18.net/manga/some-series"))
        self.assertFalse(ext.can_handle(soup, "https://comicland.org/comic/some-series"))

    def test_heuristic_base64_slides(self):
        ext = HeuristicExtractor()
        html = '''
        <html><body>
        <script>
        var slides_p_path = ["aHR0cHM6Ly9jZG4ubWFuZ2ExOC5jbHViL21hbmdhL3Rlc3QvMDEuanBn", "aHR0cHM6Ly9jZG4ubWFuZ2ExOC5jbHViL21hbmdhL3Rlc3QvMDIuanBn"];
        </script>
        </body></html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        pages = ext.extract_pages(soup, "https://manga18.club/manhwa/test/chapter-1", html)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0], "https://cdn.manga18.club/manga/test/01.jpg")
        self.assertEqual(pages[1], "https://cdn.manga18.club/manga/test/02.jpg")

    def test_search_dispatcher_new_sources_registered(self):
        keys = {s["key"] for s in TIER_2_MADARA}
        fast_keys = {s["key"] for s in search_dispatcher.get_sources_for_tier("fast")}
        expected = [
            "toongod", "hentai20", "manhwaclub",
            "comicland", "manhwa18", "toontop", "manga18fx",
            "mangadass"
        ]
        for exp in expected:
            self.assertIn(exp, keys)
            self.assertIn(exp, fast_keys)

    def test_slug_filter_ignores_unrelated_manga_sidebar(self):
        ext = HeuristicExtractor()
        html = '''
        <html><body>
            <h1>Her Bodyguard</h1>
            <div class="bxcl">
                <ul>
                    <li><a href="/manga/her-bodyguard-uncensored/chapter-1"><span class="chapter-name">Chapter 1</span></a></li>
                    <li><a href="/manga/her-bodyguard-uncensored/chapter-2"><span class="chapter-name">Chapter 2</span></a></li>
                </ul>
            </div>
            <div class="sidebar-panel">
                <div class="chapter-item">
                    <a href="/manga/secret-class/chapter-320">Chapter 320</a>
                    <a href="/manga/other-manga/chapter-150">Chapter 150</a>
                </div>
            </div>
        </body></html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        chapters = ext.extract_chapter_list(soup, "https://mangadass.com/manga/her-bodyguard-uncensored", html)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]["chapter_num"], 1.0)
        self.assertEqual(chapters[0]["title"], "Chapter 1")
        self.assertEqual(chapters[1]["chapter_num"], 2.0)
        self.assertEqual(chapters[1]["title"], "Chapter 2")

    def test_modern_ssr_next_data_chapters_and_cover(self):
        from extractors.modern_ssr import ModernSSRExtractor
        ext = ModernSSRExtractor()
        html = '''
        <html><head>
            <script id="__NEXT_DATA__" type="application/json">
            {
                "props": {
                    "pageProps": {
                        "initialManga": {
                            "name": "Married Women's Apartment",
                            "slug": "married-womens-apartment",
                            "cover": "https://rx.toontop.io/covers/sample.webp",
                            "chapters": [
                                {"number": 2, "name": "Chapter 2", "url": "/married-womens-apartment/chapter-2"},
                                {"number": 1, "name": "Chapter 1", "url": "/married-womens-apartment/chapter-1"}
                            ]
                        }
                    }
                }
            }
            </script>
        </head><body></body></html>
        '''
        soup = BeautifulSoup(html, "html.parser")
        info = ext.extract_series_info(soup, "https://toontop.io/married-womens-apartment", html)
        self.assertEqual(info["title"], "Married Women's Apartment")
        self.assertEqual(info["cover_url"], "https://rx.toontop.io/covers/sample.webp")

        chapters = ext.extract_chapter_list(soup, "https://toontop.io/married-womens-apartment", html)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]["chapter_num"], 1.0)
        self.assertEqual(chapters[0]["title"], "Chapter 1")
        self.assertEqual(chapters[1]["chapter_num"], 2.0)
        self.assertEqual(chapters[1]["title"], "Chapter 2")


if __name__ == "__main__":
    unittest.main()

