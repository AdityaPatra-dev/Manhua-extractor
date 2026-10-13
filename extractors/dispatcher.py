import re
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Optional, Any, Tuple
from bs4 import BeautifulSoup
try:
    import cloudscraper
except ImportError:
    cloudscraper = None
import requests

from .base import BaseExtractor
from .mangadex import MangaDexExtractor
from .modern_ssr import ModernSSRExtractor
from .madara import MadaraExtractor
from .mangastream import MangaStreamExtractor
from .aggregator import AggregatorExtractor
from .mangapeak import MangaPeakExtractor
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
            MangaDexExtractor(),
            ModernSSRExtractor(),
            MadaraExtractor(),
            MangaStreamExtractor(),
            AggregatorExtractor(),
            MangaPeakExtractor(),
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

    @staticmethod
    def _is_challenge_page(html: str) -> bool:
        if not html:
            return True
        lower = html.lower()
        return any(marker in lower for marker in (
            "just a moment",
            "performing security verification",
            "cf-browser-verification",
            "challenges.cloudflare.com",
            "cf-turnstile",
            "__cf_chl_opt"
        ))

    def fetch_page(self, url: str) -> Tuple[int, str, BeautifulSoup]:
        """Fetch URL using curl_cffi Chrome impersonation, falling back to Cloudscraper, then Browser Sidecar."""
        headers = DEFAULT_HEADERS.copy()
        headers["Referer"] = url
        if self.cffi_session and "User-Agent" in self.cffi_session.headers:
            headers["User-Agent"] = self.cffi_session.headers["User-Agent"]

        # 0. Check database clearance cache for valid cf_clearance
        try:
            from database.db import get_clearance_cookie
            domain = urlparse(url).netloc
            cached_cf = get_clearance_cookie(domain)
            if cached_cf:
                headers["Cookie"] = cached_cf["cookie_string"]
                if cached_cf.get("user_agent"):
                    headers["User-Agent"] = cached_cf["user_agent"]
        except Exception:
            pass

        # 1. Try curl_cffi with full Chrome 124 TLS signature (includes cached clearance cookies)
        if self.cffi_session:
            try:
                resp = self.cffi_session.get(url, headers=headers, timeout=25)
                if resp.status_code == 200 and not self._is_challenge_page(resp.text):
                    html = resp.text
                    soup = BeautifulSoup(html, "html.parser")
                    return resp.status_code, html, soup
            except Exception:
                pass

        # 2. Fallback to Cloudscraper
        try:
            resp = self.scraper.get(url, headers=headers, timeout=25)
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            resp = None
            html = ""
            soup = BeautifulSoup("", "html.parser")

        # 3. Fallback to Browser Sidecar (FlareSolverr / nodriver) if blocked
        is_blocked = (resp is None) or (resp.status_code in (403, 503)) or self._is_challenge_page(html)
        if is_blocked:
            try:
                from .browser_sidecar import fetch_protected_page
                from database.db import get_setting
                flaresolverr_url = get_setting("flaresolverr_url", "http://localhost:8191/v1")
                sidecar_res = fetch_protected_page(url, flaresolverr_url=flaresolverr_url)
                if sidecar_res and sidecar_res.get("success") and sidecar_res.get("text"):
                    # Cache clearance cookies and User-Agent in session so subsequent requests don't need browser!
                    cookies = sidecar_res.get("cookies")
                    user_agent = sidecar_res.get("user_agent")
                    if cookies:
                        if self.cffi_session:
                            for k, v in cookies.items():
                                self.cffi_session.cookies.set(k, v)
                        for k, v in cookies.items():
                            self.scraper.cookies.set(k, v)
                    if user_agent:
                        if self.cffi_session:
                            self.cffi_session.headers["User-Agent"] = user_agent
                        self.scraper.headers["User-Agent"] = user_agent

                    html = sidecar_res["text"]
                    soup = BeautifulSoup(html, "html.parser")
                    return 200, html, soup
            except Exception:
                pass

        status_code = resp.status_code if resp is not None else 500
        return status_code, html, soup

    def analyze_url(self, url: str) -> Dict[str, Any]:
        """Analyze a page, match the appropriate engine, and extract panels + navigation."""
        status_code, html, soup = self.fetch_page(url)

        if status_code != 200:
            error_msg = f"HTTP {status_code}"
            if status_code in (403, 503) and ("cloudflare" in html.lower() or "just a moment" in html.lower() or "challenges.cloudflare.com" in html.lower()):
                error_msg = f"Cloudflare Bot Protection (HTTP {status_code}) - Site requires an interactive browser challenge"
            return {
                "success": False,
                "status_code": status_code,
                "error": error_msg,
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
            error_msg = f"Failed to connect (HTTP {status_code})"
            if status_code in (403, 503) and ("cloudflare" in html.lower() or "just a moment" in html.lower() or "challenges.cloudflare.com" in html.lower()):
                error_msg = f"Cloudflare Bot Protection (HTTP {status_code}) - Site requires an interactive browser challenge"
            return {
                "success": False,
                "error": error_msg,
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

        # Check for HTMX or dynamic chapter list endpoints (e.g. WeebCentral full-chapter-list)
        hx_endpoint = soup.select_one("[hx-get*='full-chapter-list'], [hx-get*='chapter'], [data-hx-get*='full-chapter-list']")
        if hx_endpoint:
            hx_url = hx_endpoint.get("hx-get") or hx_endpoint.get("data-hx-get")
            if hx_url:
                full_hx_url = urljoin(url, hx_url)
                hx_code, hx_html, hx_soup = self.fetch_page(full_hx_url)
                if hx_code == 200:
                    hx_chaps = matched_engine.extract_chapter_list(hx_soup, full_hx_url, hx_html)
                    if len(hx_chaps) > len(chapters):
                        chapters = hx_chaps

        # If we got very few chapters or 0 chapters, check if url is a chapter reader page
        # and attempt to fetch the parent series page to get the full catalog
        is_chapter_page = bool(re.search(r'/(?:chapter|ch|c)[-_/\d]', url, re.I))
        series_url = url
        if is_chapter_page or len(chapters) <= 1:
            candidate_parent = None

            # 1. Check DOM breadcrumbs / series links first
            bc_links = soup.select(
                "ol.breadcrumb li a, div.breadcrumb a, div.c-breadcrumb a, "
                "a.back-to-series, a.all-chapters, div.allc a, "
                "a[href*='/manga/'], a[href*='/series/'], a[href*='/comics/']"
            )
            for bc in bc_links:
                h = bc.get("href", "").strip()
                if h and not re.search(r'/(?:chapter|ch|c)[-_/\d]', h, re.I):
                    full_bc = urljoin(url, h)
                    parsed_bc = urlparse(full_bc)
                    parsed_cur = urlparse(url)
                    if (full_bc != url and parsed_bc.netloc == parsed_cur.netloc 
                            and len(parsed_bc.path.strip('/')) > 0
                            and parsed_bc.path.strip('/') not in ("manga", "series", "comics", "webtoon")):
                        candidate_parent = full_bc
                        break

            # 2. Regex fallback if breadcrumbs didn't yield a valid parent
            if not candidate_parent:
                clean_parent = re.sub(r'/(?:chapter|ch|c)[-_/].*$', '/', url, flags=re.I)
                if clean_parent == url:
                    clean_parent = re.sub(r'/chapter/\d+.*$', '', url, flags=re.I)
                if clean_parent != url:
                    candidate_parent = clean_parent

            if candidate_parent:
                series_url = candidate_parent
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

        # Fallback: guarantee at least the current chapter is returned so the user can download or browse it
        if not chapters:
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


