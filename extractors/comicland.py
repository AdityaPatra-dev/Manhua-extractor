import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from extractors.base import BaseExtractor

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
import requests


class ComicLandExtractor(BaseExtractor):
    """
    Dedicated Extractor for ComicLand (comicland.org).
    ComicLand uses a React / Vite SPA frontend with a REST JSON backend at https://api.comicland.org/api.
    """

    def __init__(self):
        super().__init__()
        self.engine_id = "comicland"
        self.name = "ComicLand"
        self.api_base = "https://api.comicland.org/api"
        self.headers = {
            "Referer": "https://comicland.org/",
            "Origin": "https://comicland.org",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }

    def _http_get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            if HAS_CURL_CFFI:
                r = cffi_requests.get(url, params=params, headers=self.headers, impersonate="chrome120", timeout=12)
            else:
                r = requests.get(url, params=params, headers=self.headers, timeout=12)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None

    def can_handle(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> bool:
        domain = urlparse(url).netloc.lower()
        return "comicland.org" in domain

    def _extract_slug(self, url: str) -> Optional[str]:
        # Formats: /comic/{slug} or /comic/{slug}/chapter/{index}
        m = re.search(r'/comic/([a-zA-Z0-9_\-]+)', url)
        if m:
            return m.group(1)
        return None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> Dict[str, Any]:
        slug = self._extract_slug(url)
        if not slug:
            return {
                "title": "ComicLand Series",
                "slug": "comicland-series",
                "cover_url": None,
                "synopsis": ""
            }

        res = self._http_get(f"{self.api_base}/comic/detail", params={"slug": slug})
        if res and isinstance(res.get("data"), dict):
            d = res["data"]
            return {
                "title": d.get("title") or slug.replace("-", " ").title(),
                "slug": d.get("slug") or slug,
                "cover_url": d.get("cover_url"),
                "synopsis": d.get("description") or ""
            }

        return {
            "title": slug.replace("-", " ").title(),
            "slug": slug,
            "cover_url": None,
            "synopsis": ""
        }

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> List[Dict[str, Any]]:
        slug = self._extract_slug(url)
        if not slug:
            return []

        res = self._http_get(f"{self.api_base}/comic/detail", params={"slug": slug})
        if not res or not isinstance(res.get("data"), dict):
            return []

        d = res["data"]
        raw_chaps = d.get("chapters", [])
        chapters = []
        for ch in raw_chaps:
            idx = ch.get("chapter_index")
            if idx is not None:
                ch_title = ch.get("title") or f"Chapter {idx}"
                ch_url = f"https://comicland.org/comic/{slug}/chapter/{idx}"
                chapters.append({
                    "chapter_num": float(idx),
                    "title": ch_title,
                    "url": ch_url
                })
        chapters.sort(key=lambda x: x["chapter_num"])
        return chapters

    def extract_pages(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> List[str]:
        slug = self._extract_slug(url)
        idx_match = re.search(r'/chapter/(\d+)', url)
        if not slug or not idx_match:
            return []

        ch_index = int(idx_match.group(1))
        res = self._http_get(f"{self.api_base}/chapter/pages_by_index", params={"slug": slug, "index": ch_index})
        if not res or not isinstance(res.get("data"), dict):
            return []

        pages = res["data"].get("pages", [])
        clean_urls = [self.clean_image_url(p, "https://comicland.org/") for p in pages if p]
        return self.deduplicate_urls([p for p in clean_urls if p])

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        slug = self._extract_slug(current_url)
        idx_match = re.search(r'/chapter/(\d+)', current_url)
        if slug and idx_match:
            return f"https://comicland.org/comic/{slug}/chapter/{int(idx_match.group(1)) + 1}"
        return None

