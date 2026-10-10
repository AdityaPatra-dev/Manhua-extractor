import re
from typing import Dict, List, Optional, Any, Tuple
from bs4 import BeautifulSoup
try:
    import cloudscraper
except ImportError:
    cloudscraper = None
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
        if cloudscraper is not None:
            try:
                self.scraper = cloudscraper.create_scraper()
            except Exception:
                self.scraper = requests.Session()
        else:
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

        # 3. Fallback to Browser Sidecar (FlareSolverr / Playwright) if blocked
        if resp.status_code in (403, 503):
            try:
                from .browser_sidecar import fetch_protected_page
                from database.db import get_setting
                flaresolverr_url = get_setting("flaresolverr_url", "http://localhost:8191/v1")
                sidecar_res = fetch_protected_page(url, flaresolverr_url=flaresolverr_url)
                if sidecar_res and sidecar_res.get("success") and sidecar_res.get("text"):
                    html = sidecar_res["text"]
                    soup = BeautifulSoup(html, "html.parser")
                    return 200, html, soup
            except Exception:
                pass

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

    def inspect_series(self, url: str) -> Dict[str, Any]:
        """
        Inspect a series or chapter URL, resolve the parent series,
        scrape the complete list of chapters, and cross-reference with local library.
        """
        status_code, html, soup = self.fetch_page(url)
        if status_code != 200:
            return {
                "success": False,
                "error": f"Failed to connect (HTTP {status_code})",
                "status_code": status_code,
                "url": url
            }

        # Find best matching engine
        matched_engine: Optional[BaseExtractor] = None
        for engine in self.engines:
            if engine.can_handle(soup, url, html):
                matched_engine = engine
                break
        if not matched_engine:
            matched_engine = self.engines[-1]

        series_info = matched_engine.extract_series_info(soup, url, html)
        chapters = matched_engine.extract_chapter_list(soup, url, html)

        # If we got very few chapters or 0 chapters, check if url is a chapter reader page
        # and attempt to fetch the parent series page to get the full catalog
        is_chapter_page = bool(re.search(r'/(?:chapter|ch|c)[-_/\d]', url, re.I))
        series_url = url
        if is_chapter_page or len(chapters) <= 1:
            clean_parent = re.sub(r'/(?:chapter|ch|c)[-_/].*$', '/', url, flags=re.I)
            if clean_parent == url:
                clean_parent = re.sub(r'/chapter/\d+.*$', '', url, flags=re.I)
            if clean_parent != url:
                series_url = clean_parent
                p_code, p_html, p_soup = self.fetch_page(series_url)
                if p_code == 200:
                    p_info = matched_engine.extract_series_info(p_soup, series_url, p_html)
                    if p_info.get("cover_url"):
                        series_info["cover_url"] = p_info["cover_url"]
                    if p_info.get("title") and len(p_info["title"]) > len(series_info.get("title") or ""):
                        series_info["title"] = p_info["title"]
                    p_chaps = matched_engine.extract_chapter_list(p_soup, series_url, p_html)
                    if len(p_chaps) > len(chapters):
                        chapters = p_chaps

        # Fallback: if single chapter, ensure at least that chapter is in list
        if not chapters and is_chapter_page:
            current_num = matched_engine.extract_chapter_number(url, series_info.get("title"))
            chapters.append({
                "chapter_num": current_num,
                "title": f"Chapter {current_num:g}",
                "url": url
            })

        # Sort chapters logically ascending
        chapters.sort(key=lambda x: x["chapter_num"])

        # Cross-reference with local SQLite library
        try:
            from database.db import get_downloaded_chapters_map
            downloaded_map = get_downloaded_chapters_map(series_info.get("title", ""))
        except Exception:
            downloaded_map = {}

        enriched_chapters = []
        for ch in chapters:
            ch_num = ch["chapter_num"]
            local_rec = downloaded_map.get(ch_num)
            if local_rec:
                enriched_chapters.append({
                    "chapter_num": ch_num,
                    "title": ch.get("title") or f"Chapter {ch_num:g}",
                    "url": ch["url"],
                    "is_downloaded": True,
                    "chapter_id": local_rec["id"],
                    "file_format": local_rec.get("file_format", "cbz"),
                    "file_size": local_rec.get("file_size", 0),
                    "read_status": local_rec.get("read_status", 0),
                    "last_read_page": local_rec.get("last_read_page", 0)
                })
            else:
                enriched_chapters.append({
                    "chapter_num": ch_num,
                    "title": ch.get("title") or f"Chapter {ch_num:g}",
                    "url": ch["url"],
                    "is_downloaded": False,
                    "chapter_id": None,
                    "file_format": None,
                    "file_size": 0,
                    "read_status": 0,
                    "last_read_page": 0
                })

        downloaded_count = sum(1 for c in enriched_chapters if c["is_downloaded"])

        return {
            "success": True,
            "series_title": series_info.get("title") or "Unknown Series",
            "series_slug": series_info.get("slug") or "series",
            "series_url": series_url,
            "cover_url": series_info.get("cover_url"),
            "synopsis": series_info.get("synopsis") or "",
            "engine_name": matched_engine.name,
            "total_chapters": len(enriched_chapters),
            "downloaded_count": downloaded_count,
            "chapters": enriched_chapters
        }

# Global singleton
dispatcher = ExtractorDispatcher()


