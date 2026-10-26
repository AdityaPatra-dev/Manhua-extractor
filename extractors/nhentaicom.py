import re
import json
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import requests

from .base import BaseExtractor

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://nhentai.com/",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
}


class NHentaiComExtractor(BaseExtractor):
    engine_id: str = "nhentaicom"
    name: str = "nHentai.com"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower = (url or "").lower()
        return "nhentai.com" in lower

    @staticmethod
    def extract_slug(url: str) -> Optional[str]:
        if not url:
            return None
        clean_url = url.split("?")[0].split("#")[0].rstrip("/")
        # Pattern: /comic/<slug> or /en/comic/<slug> or /reader/
        clean_url = re.sub(r'/reader(?:/\d+)?$', '', clean_url)
        m = re.search(r'/(?:comic|comics)/([^/]+)', clean_url)
        if m:
            return m.group(1)
        return None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        slug = self.extract_slug(url)

        # 1. Parse JSON-LD metadata if present
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                graph = data.get("@graph", [data])
                for node in graph:
                    types = node.get("@type", [])
                    if isinstance(types, str):
                        types = [types]
                    if any(t in ("Book", "ComicIssue", "ComicSeries") for t in types):
                        if node.get("name"):
                            info["title"] = node["name"]
                        if node.get("image"):
                            info["cover_url"] = node["image"]
                        if node.get("keywords"):
                            kws = [k.strip() for k in node["keywords"].split(",") if k.strip()]
                            info["tags"] = kws
                            info["genres"] = kws
                        if node.get("author"):
                            authors = node["author"]
                            if isinstance(authors, list):
                                a_names = [a.get("name") for a in authors if a.get("name")]
                                if a_names:
                                    info["author"] = ", ".join(a_names)
                            elif isinstance(authors, dict) and authors.get("name"):
                                info["author"] = authors["name"]
                        break
            except Exception:
                pass

        # 2. Fallbacks
        if not info.get("title"):
            title_el = soup.select_one("h1, .comic-title")
            if title_el:
                info["title"] = title_el.get_text(strip=True)
            elif soup.title:
                t = soup.title.string or ""
                info["title"] = re.sub(r'\s*\|\s*nHentai.*$', '', t, flags=re.I).strip()

        if not info.get("cover_url"):
            cover_el = soup.select_one("img[src*='storage/comics'], .cover img, #app img")
            if cover_el:
                info["cover_url"] = cover_el.get("src") or cover_el.get("data-src")

        info["slug"] = slug or "nhentaicom-comic"
        info["status"] = "Completed"
        info["type"] = "Doujinshi / Manga"
        return info

    def extract_chapter_number(self, url: str, title: Optional[str] = None) -> float:
        return 1.0

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        slug = self.extract_slug(url)
        page_count = 0

        # 1. Prefer API check for verified available images
        if slug:
            try:
                api_url = f"https://nhentai.com/api/comics/{slug}/images"
                headers = dict(DEFAULT_HEADERS)
                headers["Referer"] = f"https://nhentai.com/en/comic/{slug}/reader"
                r = requests.get(api_url, headers=headers, timeout=8)
                if r.status_code == 200:
                    d = r.json()
                    images = d.get("images", [])
                    if images:
                        page_count = len(images)
            except Exception:
                pass

        # 2. Check JSON-LD numberOfPages only if API didn't report 0 images
        if page_count <= 0 and not slug:
            for s in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(s.string)
                    graph = data.get("@graph", [data])
                    for node in graph:
                        if node.get("numberOfPages"):
                            page_count = int(node["numberOfPages"])
                            break
                except Exception:
                    pass

        if page_count <= 0:
            return []

        disp_title = f"Complete Work ({page_count} Pages)"
        target_url = f"https://nhentai.com/en/comic/{slug}" if slug else url

        return [
            {
                "chapter_num": 1.0,
                "title": disp_title,
                "url": target_url
            }
        ]

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        slug = self.extract_slug(url)
        if not slug:
            return []

        # Call nhentai.com JSON API: /api/comics/<slug>/images
        api_url = f"https://nhentai.com/api/comics/{slug}/images"
        headers = dict(DEFAULT_HEADERS)
        headers["Referer"] = f"https://nhentai.com/en/comic/{slug}/reader"

        try:
            r = requests.get(api_url, headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json()
                images = data.get("images", [])
                pages = []
                for img in images:
                    src = img.get("source_url")
                    if src:
                        pages.append(src)
                if pages:
                    return pages
        except Exception:
            pass

        return []

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        return None

