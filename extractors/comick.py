import re
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests

from .base import BaseExtractor

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

class ComicKExtractor(BaseExtractor):
    engine_id: str = "comick"
    name: str = "ComicK (Official API)"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        return any(domain in url.lower() for domain in ("comick.dev", "comick.io", "comick.app", "comick.cc"))

    def _extract_comic_slug(self, url: str) -> Optional[str]:
        m = re.search(r'/comic/([^/?#]+)', url, re.I)
        return m.group(1) if m else None

    def _extract_chapter_hid(self, url: str) -> Optional[str]:
        # e.g. /comic/slug/29Osbgc5-chapter-81-en
        m = re.search(r'/([a-zA-Z0-9_-]+)-chapter-', url, re.I)
        if m:
            return m.group(1)
        m2 = re.search(r'/chapter/([a-zA-Z0-9_-]+)', url, re.I)
        return m2.group(1) if m2 else None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        slug = self._extract_comic_slug(url)
        if not slug:
            return info

        for api_host in ("api.comick.dev", "api.comick.io", "api.comick.cc"):
            try:
                r = requests.get(f"https://{api_host}/comic/{slug}", headers=DEFAULT_HEADERS, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    comic = data.get("comic", {})
                    if comic:
                        info["title"] = comic.get("title") or info.get("title")
                        info["slug"] = comic.get("slug") or slug
                        info["hid"] = comic.get("hid")
                        bkey = comic.get("bkey")
                        if not bkey and comic.get("md_covers"):
                            bkey = comic["md_covers"][0].get("bkey")
                        if bkey:
                            info["cover_url"] = f"https://meo.comick.pictures/{bkey}"
                        info["synopsis"] = comic.get("desc") or ""
                        break
            except Exception:
                continue

        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        slug = self._extract_comic_slug(url)
        if not slug:
            return super().extract_chapter_list(soup, url, html)

        # Resolve comic HID
        hid = None
        for api_host in ("api.comick.dev", "api.comick.io", "api.comick.cc"):
            try:
                r = requests.get(f"https://{api_host}/comic/{slug}", headers=DEFAULT_HEADERS, timeout=8)
                if r.status_code == 200:
                    comic = r.json().get("comic", {})
                    hid = comic.get("hid")
                    break
            except Exception:
                continue

        if not hid:
            return super().extract_chapter_list(soup, url, html)

        chapters = []
        seen_nums = set()
        page = 1
        while True:
            try:
                r_ch = requests.get(
                    f"https://api.comick.dev/comic/{hid}/chapters?lang=en&limit=100&page={page}",
                    headers=DEFAULT_HEADERS,
                    timeout=10
                )
                if r_ch.status_code != 200:
                    break
                data = r_ch.json()
                items = data.get("chapters", [])
                if not items:
                    break
                for c in items:
                    chap_raw = c.get("chap")
                    if not chap_raw:
                        continue
                    try:
                        ch_num = float(chap_raw)
                    except ValueError:
                        continue
                    if ch_num in seen_nums:
                        continue
                    seen_nums.add(ch_num)
                    c_hid = c.get("hid")
                    sub_t = c.get("title")
                    extra = f" - {sub_t}" if sub_t else ""
                    ch_title = f"Chapter {chap_raw}{extra}"
                    ch_url = f"https://comick.dev/comic/{slug}/{c_hid}-chapter-{chap_raw}-en"
                    chapters.append({
                        "chapter_num": ch_num,
                        "title": ch_title,
                        "url": ch_url
                    })
                total = data.get("total", 0)
                if len(items) < 100 or len(chapters) >= total:
                    break
                page += 1
            except Exception:
                break

        if chapters:
            chapters.sort(key=lambda x: x["chapter_num"])
            return chapters

        return super().extract_chapter_list(soup, url, html)

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        hid = self._extract_chapter_hid(url)
        raw_urls = []
        if hid:
            for api_host in ("api.comick.dev", "api.comick.io", "api.comick.cc"):
                try:
                    r = requests.get(f"https://{api_host}/chapter/{hid}", headers=DEFAULT_HEADERS, timeout=8)
                    if r.status_code == 200:
                        ch_data = r.json().get("chapter", {})
                        md_imgs = ch_data.get("md_images") or ch_data.get("images") or []
                        for img in md_imgs:
                            bkey = img.get("b2key") or img.get("bkey") or img.get("name")
                            if bkey:
                                raw_urls.append(f"https://meo.comick.pictures/{bkey}")
                        if raw_urls:
                            break
                except Exception:
                    continue

        if not raw_urls:
            # Fallback to scraping CDN URLs from HTML / RSC payload
            for m in re.finditer(r'https?://meo\.comick\.pictures/[a-zA-Z0-9_.\-]+?\.(?:jpg|jpeg|png|webp)', html, re.I):
                raw_urls.append(m.group(0))

        if not raw_urls:
            for m in re.finditer(r'"b2key":\s*"([^"]+)"', html):
                raw_urls.append(f"https://meo.comick.pictures/{m.group(1)}")

        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        clean = [self.clean_image_url(u, base_url) for u in raw_urls]
        clean = [u for u in clean if u]
        return self.deduplicate_urls(clean)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        hid = self._extract_chapter_hid(current_url)
        if hid:
            try:
                r = requests.get(f"https://api.comick.dev/chapter/{hid}", headers=DEFAULT_HEADERS, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    nxt = data.get("next")
                    if nxt and isinstance(nxt, dict) and nxt.get("hid"):
                        slug = self._extract_comic_slug(current_url)
                        return f"https://comick.dev/comic/{slug}/{nxt['hid']}-chapter-{nxt.get('chap', 'next')}-en"
            except Exception:
                pass
        return None

