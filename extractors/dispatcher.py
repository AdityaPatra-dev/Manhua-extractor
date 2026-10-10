import re
from typing import Dict, List, Optional, Any, Tuple
from bs4 import BeautifulSoup
import cloudscraper
import requests

from .base import BaseExtractor
from .madara import MadaraExtractor
from .modern_ssr import ModernSSRExtractor
from .mangastream import MangaStreamExtractor
from .aggregator import AggregatorExtractor
from .heuristic import HeuristicExtractor

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

class ExtractorDispatcher:
    def __init__(self):
        # Register engines in priority order
        self.engines: List[BaseExtractor] = [
            ModernSSRExtractor(),
            MadaraExtractor(),
            MangaStreamExtractor(),
            AggregatorExtractor(),
            HeuristicExtractor()
        ]
        self.cffi_session = cffi_requests.Session(impersonate="chrome124") if HAS_CURL_CFFI else None
        try:
            self.scraper = cloudscraper.create_scraper()
        except Exception:
            self.scraper = requests.Session()

    def fetch_page(self, url: str) -> Tuple[int, str, BeautifulSoup]:
        """Fetch URL using curl_cffi Chrome impersonation, falling back to Cloudscraper."""
        headers = DEFAULT_HEADERS.copy()
        headers["Referer"] = url

        # 1. Try curl_cffi with full Chrome 124 TLS signature
        if self.cffi_session:
            try:
                resp = self.cffi_session.get(url, headers=headers, timeout=25)
                if resp.status_code == 200:
                    html = resp.text
                    soup = BeautifulSoup(html, "html.parser")
                    return resp.status_code, html, soup
            except Exception:
                pass

        # 2. Fallback to Cloudscraper
        resp = self.scraper.get(url, headers=headers, timeout=25)
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        return resp.status_code, html, soup

    def analyze_url(self, url: str) -> Dict[str, Any]:
        """Analyze a page, match the appropriate engine, and extract panels + navigation."""
        status_code, html, soup = self.fetch_page(url)

        if status_code != 200:
            return {
                "success": False,
                "status_code": status_code,
                "error": f"HTTP {status_code}",
                "url": url,
            }

        # Find best matching engine
        matched_engine: Optional[BaseExtractor] = None
        for engine in self.engines:
            if engine.can_handle(soup, url, html):
                matched_engine = engine
                break

        if not matched_engine:
            matched_engine = self.engines[-1]  # Heuristic fallback

        # Extract series metadata
        series_info = matched_engine.extract_series_info(soup, url, html)
        chapter_num = matched_engine.extract_chapter_number(url, series_info.get("title"))
        pages = matched_engine.extract_pages(soup, url, html)
        next_chapter_url = matched_engine.extract_next_chapter(soup, url)

        return {
            "success": True,
            "status_code": status_code,
            "engine_id": matched_engine.engine_id,
            "engine_name": matched_engine.name,
            "url": url,
            "series_title": series_info.get("title"),
            "series_slug": series_info.get("slug"),
            "series_cover": series_info.get("cover_url"),
            "chapter_num": chapter_num,
            "pages": pages,
            "panel_count": len(pages),
            "next_chapter_url": next_chapter_url
        }

# Global singleton
dispatcher = ExtractorDispatcher()

