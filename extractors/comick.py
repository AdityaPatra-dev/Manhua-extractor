import re
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import requests

from .base import BaseExtractor

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
}

class ComicKExtractor(BaseExtractor):
    engine_id: str = "comick"
    name: str = "ComicK"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        return any(domain in url.lower() for domain in (
            "comick.live", "comick.dev", "comick.io", "comick.app", "comick.cc", "comick.top", "comick.art"
        ))

    def _normalize_url(self, url: str) -> str:
        # Normalize legacy/dead domains to comick.live
        for d in ("comick.dev", "comick.io", "comick.app", "comick.cc", "comick.top", "comick.art"):
            if d in url:
                url = url.replace(d, "comick.live")
        return url

    def _extract_comic_slug(self, url: str) -> Optional[str]:
        m = re.search(r'/comic/([^/?#]+)', url, re.I)
        return m.group(1) if m else None

    def _extract_chapter_hid(self, url: str) -> Optional[str]:
        # e.g. /comic/slug/29Osbgc5-chapter-81-en or /comic/9hhgCPLV/Y7nG2-chapter-1-en
        m = re.search(r'/([a-zA-Z0-9_-]+)-chapter-', url, re.I)
        if m:
            return m.group(1)
        m2 = re.search(r'/chapter/([a-zA-Z0-9_-]+)', url, re.I)
        return m2.group(1) if m2 else None

    def _parse_embedded_json(self, soup: BeautifulSoup, html: str = "") -> Optional[Dict[str, Any]]:
        if soup:
            for s in soup.find_all("script"):
                txt = (s.string or "").strip()
                if not txt.startswith("{") or not txt.endswith("}"):
                    continue
                if '"chapter":' in txt or '"comic":' in txt or '"firstChapters":' in txt:
                    try:
                        return json.loads(txt)
                    except Exception:
                        continue
        if html:
            m = re.search(r'<script[^>]*>\s*(\{(?:[^{}]*|"chapter":.*|"comic":.*)\})\s*</script>', html, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    pass
        return None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        norm_url = self._normalize_url(url)
        slug = self._extract_comic_slug(norm_url)
        if not slug:
            return info

        data = self._parse_embedded_json(soup, html)
        comic: Dict[str, Any] = {}
        if data:
            if "comic" in data and isinstance(data["comic"], dict):
                comic = data["comic"]
            elif "chapter" in data and isinstance(data.get("chapter"), dict):
                comic = data["chapter"].get("comic", {})
            elif "title" in data and "desc" in data:
                comic = data

        if comic:
            info["title"] = comic.get("title") or info.get("title")
            info["slug"] = comic.get("slug") or slug
            info["synopsis"] = comic.get("description") or comic.get("desc") or info.get("synopsis", "")

            cover = comic.get("default_thumbnail") or comic.get("cover_url")
            if not cover and comic.get("md_covers") and isinstance(comic["md_covers"], list):
                bkey = comic["md_covers"][0].get("bkey") or comic["md_covers"][0].get("b2key")
                if bkey:
                    cover = f"https://meo.comick.pictures/{bkey}"
            if not cover and comic.get("bkey"):
                cover = f"https://meo.comick.pictures/{comic['bkey']}"
            if cover:
                info["cover_url"] = cover

        if not info.get("title"):
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                info["title"] = og_title["content"].split(" - ")[0].strip()

        if not info.get("cover_url"):
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                info["cover_url"] = og_img["content"]

        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        norm_url = self._normalize_url(url)
        slug = self._extract_comic_slug(norm_url)
        data = self._parse_embedded_json(soup, html)

        chapter_list_raw = []
        if data and "chapterList" in data and isinstance(data["chapterList"], list):
            chapter_list_raw = data["chapterList"]

        # If on comic series page, extract first chapter and fetch chapterList from it
        if not chapter_list_raw and data and "firstChapters" in data and isinstance(data["firstChapters"], list):
            f_chaps = data["firstChapters"]
            en_first = next((c for c in f_chaps if c.get("lang") == "en" and c.get("hid")), None)
            if not en_first and f_chaps:
                en_first = f_chaps[0]
            if en_first and slug:
                first_url = f"https://comick.live/comic/{slug}/{en_first['hid']}-chapter-{en_first.get('chap', '1')}-{en_first.get('lang', 'en')}"
                try:
                    r = requests.get(first_url, headers=DEFAULT_HEADERS, timeout=8)
                    if r.status_code == 200:
                        sub_soup = BeautifulSoup(r.text, "html.parser")
                        sub_data = self._parse_embedded_json(sub_soup, r.text)
                        if sub_data and "chapterList" in sub_data:
                            chapter_list_raw = sub_data["chapterList"]
                except Exception:
                    pass

        if chapter_list_raw and slug:
            chapters = []
            seen_nums = set()
            has_en = any(c.get("lang") == "en" for c in chapter_list_raw)
            for c in chapter_list_raw:
                if has_en and c.get("lang") != "en":
                    continue
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
                lang = c.get("lang") or "en"
                sub_t = c.get("title")
                extra = f" - {sub_t}" if sub_t else ""
                ch_title = f"Chapter {chap_raw}{extra}"
                ch_url = f"https://comick.live/comic/{slug}/{c_hid}-chapter-{chap_raw}-{lang}"
                chapters.append({
                    "chapter_num": ch_num,
                    "title": ch_title,
                    "url": ch_url
                })
            if chapters:
                chapters.sort(key=lambda x: x["chapter_num"])
                return chapters

        return super().extract_chapter_list(soup, norm_url, html)

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        raw_urls: List[str] = []
        data = self._parse_embedded_json(soup, html)

        if data:
            ch_data = data.get("chapter", {}) if "chapter" in data else data
            images = ch_data.get("images") or ch_data.get("md_images") or []
            for img in images:
                if isinstance(img, dict):
                    u = img.get("url")
                    if u and u.startswith("http"):
                        raw_urls.append(u)
                    else:
                        bkey = img.get("b2key") or img.get("bkey") or img.get("name")
                        if bkey:
                            raw_urls.append(f"https://meo.comick.pictures/{bkey}")
                elif isinstance(img, str) and img.startswith("http"):
                    raw_urls.append(img)

        # Fallback 1: Search HTML for cdn*.comicknew.pictures image URLs
        if not raw_urls:
            for m in re.finditer(r'https?://(?:cdn[0-9]*\.)?comicknew\.pictures/[a-zA-Z0-9_./\-]+?\.(?:webp|jpg|jpeg|png)', html, re.I):
                u = m.group(0)
                if "/covers/" not in u and "/thumb" not in u and "logo" not in u:
                    raw_urls.append(u)

        # Fallback 2: Search HTML for meo.comick.pictures image URLs
        if not raw_urls:
            for m in re.finditer(r'https?://meo\.comick\.pictures/[a-zA-Z0-9_.\-]+?\.(?:jpg|jpeg|png|webp)', html, re.I):
                raw_urls.append(m.group(0))

        # Fallback 3: Search for b2key attributes in HTML
        if not raw_urls:
            for m in re.finditer(r'"b2key":\s*"([^"]+)"', html):
                raw_urls.append(f"https://meo.comick.pictures/{m.group(1)}")

        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        clean = [self.clean_image_url(u, base_url) for u in raw_urls]
        # Guarantee no logo or cover is mistaken for a comic page
        clean = [u for u in clean if u and "/covers/" not in u and "logo" not in u]
        return self.deduplicate_urls(clean)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        norm_url = self._normalize_url(current_url)
        slug = self._extract_comic_slug(norm_url)
        c_hid = self._extract_chapter_hid(norm_url)
        data = self._parse_embedded_json(soup, "")
        if data and "chapterList" in data and c_hid and slug:
            ch_list = data["chapterList"]
            for idx, ch in enumerate(ch_list):
                if ch.get("hid") == c_hid and idx > 0:
                    prev_or_next = ch_list[idx - 1]
                    c_num = prev_or_next.get("chap")
                    n_hid = prev_or_next.get("hid")
                    lang = prev_or_next.get("lang") or "en"
                    if n_hid and c_num:
                        return f"https://comick.live/comic/{slug}/{n_hid}-chapter-{c_num}-{lang}"
        return None
