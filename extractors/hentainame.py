import re
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup

from .base import BaseExtractor

DEFAULT_HEADERS = {
    "User-Agent": "curl/7.88.1",
    "Referer": "https://www.hentai.name/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class HentaiNameExtractor(BaseExtractor):
    engine_id: str = "hentainame"
    name: str = "hentai.name"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower = (url or "").lower()
        return "hentai.name" in lower

    @staticmethod
    def extract_gallery_id(url: str) -> Optional[int]:
        if not url:
            return None
        clean_url = url.split("?")[0].split("#")[0].rstrip("/")
        m = re.search(r'/g/(\d+)', clean_url)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        m_digits = re.findall(r'(\d+)', clean_url)
        if m_digits:
            try:
                return int(m_digits[0])
            except ValueError:
                pass
        return None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        gid = self.extract_gallery_id(url)

        # Title
        title_el = soup.select_one("h1, .gallery-title, .title")
        if title_el:
            info["title"] = title_el.get_text(strip=True)
        elif soup.title:
            info["title"] = (soup.title.string or "").strip()

        # Cover
        cover_el = soup.select_one("img[src*='poster'], img[data-src*='poster'], .poster img, .cover img")
        if cover_el:
            info["cover_url"] = cover_el.get("src") or cover_el.get("data-src")

        # Tags
        tags = []
        for t in soup.select("a[href*='/tag/'], a[href*='/tags/'], .tags a"):
            txt = t.get_text(strip=True)
            txt_clean = re.sub(r'\s*\d+$', '', txt).strip()
            if txt_clean and txt_clean not in tags:
                tags.append(txt_clean)
        if tags:
            info["tags"] = tags
            info["genres"] = tags

        # Artists
        artists = []
        for a in soup.select("a[href*='/artist/'], a[href*='/artists/']"):
            atxt = re.sub(r'\s*\d+$', '', a.get_text(strip=True)).strip()
            if atxt and atxt not in artists:
                artists.append(atxt)
        if artists:
            info["author"] = ", ".join(artists)

        info["slug"] = f"hentainame-{gid}" if gid else "hentainame-gallery"
        info["status"] = "Completed"
        info["type"] = "Doujinshi / Manga"
        return info

    def extract_chapter_number(self, url: str, title: Optional[str] = None) -> float:
        return 1.0

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        gid = self.extract_gallery_id(url)
        if not gid:
            return super().extract_chapter_list(soup, url, html)

        # Calculate pages from thumbnails with _thumb
        thumb_imgs = [img for img in soup.select("img") if "_thumb." in (img.get("src") or "")]
        page_count = len(thumb_imgs)
        disp_title = f"Complete Work ({page_count} Pages)" if page_count > 0 else "Complete Work"
        target_url = f"https://www.hentai.name/g/{gid}/"

        return [
            {
                "chapter_num": 1.0,
                "title": disp_title,
                "url": target_url
            }
        ]

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        thumb_urls = []
        for img in soup.select("img"):
            src = img.get("src") or img.get("data-src") or ""
            if "_thumb." in src:
                thumb_urls.append(src)

        dedup = list(dict.fromkeys(thumb_urls))
        if dedup:
            return [u.replace("_thumb.", ".") for u in dedup]

        return []

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        return None

