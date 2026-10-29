import unittest
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from extractors.hentaifox import HentaiFoxExtractor
from extractors.threehentai import ThreeHentaiExtractor
from extractors.nhentaito import NHentaiToExtractor
from extractors.hentainame import HentaiNameExtractor
from extractors.nhentaicom import NHentaiComExtractor
from extractors.madara import MadaraExtractor
from extractors.dispatcher import ExtractorDispatcher
from core.search.dispatcher import SearchDispatcher, TIER_1_SOURCES, TIER_2_MADARA


class TestNewAdultSources(unittest.TestCase):

    def setUp(self):
        self.hentaifox = HentaiFoxExtractor()
        self.threehentai = ThreeHentaiExtractor()
        self.nhentaito = NHentaiToExtractor()
        self.hentainame = HentaiNameExtractor()
        self.nhentaicom = NHentaiComExtractor()
        self.madara = MadaraExtractor()
        self.dispatcher = ExtractorDispatcher()
        self.search_dispatcher = SearchDispatcher()

    # --- 1. HentaiFox Tests ---
    def test_hentaifox_can_handle_and_id(self):
        soup = BeautifulSoup("", "html.parser")
        self.assertTrue(self.hentaifox.can_handle(soup, "https://hentaifox.com/gallery/176004/", ""))
        self.assertTrue(self.hentaifox.can_handle(soup, "https://hentaifox.com/g/176004/1/", ""))
        self.assertFalse(self.hentaifox.can_handle(soup, "https://3hentai.net/d/775590", ""))
        self.assertEqual(self.hentaifox.extract_gallery_id("https://hentaifox.com/gallery/176004/"), 176004)
        self.assertEqual(self.hentaifox.extract_gallery_id("https://hentaifox.com/g/176004/5/"), 176004)

    def test_hentaifox_extract_series_info_and_chapters(self):
        html = """
        <div class="gallery_right">
            <h1>Okaa-san Diary</h1>
        </div>
        <div class="inner_thumb">
            <img data-src="https://i3.hentaifox.com/005/4282653/thumb.jpg" />
        </div>
        <ul class="tags">
            <li><a href="/tag/milf/">milf 500</a></li>
            <li><a href="/artist/marina/">marina 10</a></li>
        </ul>
        <span>Pages: 28</span>
        """
        soup = BeautifulSoup(html, "html.parser")
        info = self.hentaifox.extract_series_info(soup, "https://hentaifox.com/gallery/176004/", html)
        self.assertEqual(info["title"], "Okaa-san Diary")
        self.assertEqual(info["cover_url"], "https://i3.hentaifox.com/005/4282653/thumb.jpg")
        self.assertIn("milf", info["tags"])
        self.assertIn("marina", info["author"])

        chaps = self.hentaifox.extract_chapter_list(soup, "https://hentaifox.com/gallery/176004/", html)
        self.assertEqual(len(chaps), 1)
        self.assertEqual(chaps[0]["chapter_num"], 1.0)
        self.assertIn("28 Pages", chaps[0]["title"])

    # --- 2. 3Hentai Tests ---
    def test_threehentai_can_handle_and_id(self):
        soup = BeautifulSoup("", "html.parser")
        self.assertTrue(self.threehentai.can_handle(soup, "https://3hentai.net/d/775590", ""))
        self.assertTrue(self.threehentai.can_handle(soup, "https://3hentai.net/d/775590/1", ""))
        self.assertFalse(self.threehentai.can_handle(soup, "https://nhentai.to/g/691494", ""))
        self.assertEqual(self.threehentai.extract_gallery_id("https://3hentai.net/d/775590"), 775590)

    def test_threehentai_extract_pages(self):
        html = """
        <h1>Relief Duty</h1>
        <div class="doujinshi-page">
            <img src="https://s1.3hentai.net/d2493730/1t.jpg" />
            <img src="https://s1.3hentai.net/d2493730/2t.jpg" />
            <img src="https://s1.3hentai.net/d2493730/3t.webp" />
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        pages = self.threehentai.extract_pages(soup, "https://3hentai.net/d/775590", html)
        self.assertEqual(pages, [
            "https://s1.3hentai.net/d2493730/1.jpg",
            "https://s1.3hentai.net/d2493730/2.jpg",
            "https://s1.3hentai.net/d2493730/3.webp"
        ])

    # --- 3. nhentai.to Tests ---
    def test_nhentaito_can_handle_and_id(self):
        soup = BeautifulSoup("", "html.parser")
        self.assertTrue(self.nhentaito.can_handle(soup, "https://nhentai.to/g/691494/", ""))
        self.assertTrue(self.nhentaito.can_handle(soup, "https://nhentai.to/g/691494/2/", ""))
        self.assertFalse(self.nhentaito.can_handle(soup, "https://hentai.name/g/196935/", ""))
        self.assertEqual(self.nhentaito.extract_gallery_id("https://nhentai.to/g/691494/"), 691494)

    def test_nhentaito_extract_pages(self):
        html = """
        <div id="thumbnail-container">
            <div class="thumb-container"><img src="https://supercdn.site/galleries/4270886/1t.webp" /></div>
            <div class="thumb-container"><img src="https://supercdn.site/galleries/4270886/2t.webp" /></div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        pages = self.nhentaito.extract_pages(soup, "https://nhentai.to/g/691494/", html)
        self.assertEqual(pages, [
            "https://supercdn.site/galleries/4270886/1.webp",
            "https://supercdn.site/galleries/4270886/2.webp"
        ])

    # --- 4. hentai.name Tests ---
    def test_hentainame_can_handle_and_id(self):
        soup = BeautifulSoup("", "html.parser")
        self.assertTrue(self.hentainame.can_handle(soup, "https://www.hentai.name/g/196935/", ""))
        self.assertFalse(self.hentainame.can_handle(soup, "https://nhentai.com/en/comic/test", ""))
        self.assertEqual(self.hentainame.extract_gallery_id("https://www.hentai.name/g/196935/"), 196935)

    def test_hentainame_extract_pages(self):
        html = """
        <img src="https://pics.hentai.name/000/196/196935/1_thumb.webp" />
        <img src="https://pics.hentai.name/000/196/196935/2_thumb.webp" />
        """
        soup = BeautifulSoup(html, "html.parser")
        pages = self.hentainame.extract_pages(soup, "https://www.hentai.name/g/196935/", html)
        self.assertEqual(pages, [
            "https://pics.hentai.name/000/196/196935/1.webp",
            "https://pics.hentai.name/000/196/196935/2.webp"
        ])

    # --- 5. nhentai.com Tests ---
    def test_nhentaicom_can_handle_and_slug(self):
        soup = BeautifulSoup("", "html.parser")
        self.assertTrue(self.nhentaicom.can_handle(soup, "https://nhentai.com/en/comic/test-comic-slug", ""))
        self.assertTrue(self.nhentaicom.can_handle(soup, "https://nhentai.com/en/comic/test-comic-slug/reader", ""))
        self.assertEqual(self.nhentaicom.extract_slug("https://nhentai.com/en/comic/test-comic-slug"), "test-comic-slug")
        self.assertEqual(self.nhentaicom.extract_slug("https://nhentai.com/en/comic/test-comic-slug/reader"), "test-comic-slug")

    @patch("requests.get")
    def test_nhentaicom_extract_pages(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "images": [
                {"page": 1, "source_url": "https://cdn.nhentai.com/nhentai/storage/images/717451/1.webp"},
                {"page": 2, "source_url": "https://cdn.nhentai.com/nhentai/storage/images/717451/2.webp"}
            ]
        }
        mock_get.return_value = mock_resp

        soup = BeautifulSoup("", "html.parser")
        pages = self.nhentaicom.extract_pages(soup, "https://nhentai.com/en/comic/my-slug", "")
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0], "https://cdn.nhentai.com/nhentai/storage/images/717451/1.webp")

    # --- 6. HentaiRead (Madara) Tests ---
    def test_hentairead_madara_can_handle(self):
        soup = BeautifulSoup("", "html.parser")
        self.assertTrue(self.madara.can_handle(soup, "https://hentairead.com/hentai/test-series/", ""))
        self.assertTrue(self.madara.can_handle(soup, "https://hentairead.com/hentai/test-series/chapter-1/", ""))

    # --- 7. Extractor Dispatcher Routing ---
    def test_dispatcher_engine_matching(self):
        soup = BeautifulSoup("", "html.parser")
        e1 = self.dispatcher.match_engine(soup, "https://hentaifox.com/gallery/123/", "")
        self.assertEqual(e1.engine_id, "hentaifox")

        e2 = self.dispatcher.match_engine(soup, "https://3hentai.net/d/456", "")
        self.assertEqual(e2.engine_id, "3hentai")

        e3 = self.dispatcher.match_engine(soup, "https://nhentai.to/g/789/", "")
        self.assertEqual(e3.engine_id, "nhentaito")

        e4 = self.dispatcher.match_engine(soup, "https://www.hentai.name/g/111/", "")
        self.assertEqual(e4.engine_id, "hentainame")

        e5 = self.dispatcher.match_engine(soup, "https://nhentai.com/en/comic/test", "")
        self.assertEqual(e5.engine_id, "nhentaicom")

        e6 = self.dispatcher.match_engine(soup, "https://hentairead.com/hentai/test/", "")
        self.assertEqual(e6.engine_id, "madara")

    # --- 8. Search Dispatcher Registrations ---
    def test_search_dispatcher_sources_registered(self):
        keys = {s["key"] for s in TIER_1_SOURCES}
        self.assertIn("hentaifox", keys)
        self.assertIn("3hentai", keys)
        self.assertIn("nhentaito", keys)
        self.assertIn("hentainame", keys)


if __name__ == "__main__":
    unittest.main()
