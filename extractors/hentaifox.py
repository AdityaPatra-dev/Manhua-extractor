import re
import json
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import requests

from .base import BaseExtractor

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://hentaifox.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class HentaiFoxExtractor(BaseExtractor):
    engine_id: str = "hentaifox"
    name: str = "HentaiFox"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower = (url or "").lower()
        return "hentaifox.com" in lower

    @staticmethod
    def extract_gallery_id(url: str) -> Optional[int]:
        if not url:
            return None
        clean_url = url.split("?")[0].split("#")[0].rstrip("/")
        m = re.search(r'/(?:gallery|g)/(\d+)', clean_url, re.IGNORECASE)
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
        title_el = soup.select_one(".gallery_right h1, .caption h1, .caption .g_title a, h1")
        if title_el:
            info["title"] = title_el.get_text(strip=True)
        elif soup.title:
            t = soup.title.string or ""
            info["title"] = re.sub(r'\s*-\s*HentaiFox.*$', '', t, flags=re.I).strip()

        # Cover
        cover_el = soup.select_one(".gallery_left img, .inner_thumb img, .cover img")
        if cover_el:
            info["cover_url"] = cover_el.get("data-src") or cover_el.get("src")

        # Tags & Metadata
        tags = []
        for t in soup.select("ul.tags a, .tag_row a"):
            txt = t.get_text(strip=True)
            txt_clean = re.sub(r'\s*\d+$', '', txt).strip()
            if txt_clean and txt_clean not in tags:
                tags.append(txt_clean)
        if tags:
            info["tags"] = tags
            info["genres"] = tags

        # Artists
        artists = []
        for a in soup.select('a[href*="/artist/"]'):
            atxt = re.sub(r'\s*\d+$', '', a.get_text(strip=True)).strip()
            if atxt and atxt not in artists:
                artists.append(atxt)
        if artists:
            info["author"] = ", ".join(artists)

        info["slug"] = f"hentaifox-{gid}" if gid else "hentaifox-gallery"
        info["status"] = "Completed"
        info["type"] = "Doujinshi / Manga"
        return info

    def extract_chapter_number(self, url: str, title: Optional[str] = None) -> float:
        return 1.0

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        gid = self.extract_gallery_id(url)
        if not gid:
            return super().extract_chapter_list(soup, url, html)

        # Determine page count
        page_count_str = None
        for span in soup.select("span, div, li"):
            txt = span.get_text(strip=True)
            m = re.search(r'pages:\s*(\d+)', txt, re.IGNORECASE)
            if m:
                page_count_str = m.group(1)
                break

        disp_title = f"Complete Work ({page_count_str} Pages)" if page_count_str else "Complete Work"
        target_url = f"https://hentaifox.com/gallery/{gid}/"

        return [
            {
                "chapter_num": 1.0,
                "title": disp_title,
                "url": target_url
            }
        ]

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        gid = self.extract_gallery_id(url)
        if not gid:
            return []

        # Fetch reader page 1 to get base URL and var g_th mapping
        reader_url = f"https://hentaifox.com/g/{gid}/1/"
        try:
            r = requests.get(reader_url, headers=DEFAULT_HEADERS, timeout=12)
            if r.status_code == 200 and r.text:
                r_text = r.text
                m_img = re.search(r'id=[\x22\x27]gimg[\x22\x27][^>]+data-src=[\x22\x27](https?://[^\x22\x27]+/)(\d+)\.(\w+)[\x22\x27]', r_text)
                base_url = m_img.group(1) if m_img else None

                # Look for $.parseJSON( ... );
                idx = r_text.find('$.parseJSON(')
                if idx != -1 and base_url:
                    e_idx = r_text.find(');', idx)
                    if e_idx != -1:
                        raw = r_text[idx + 12:e_idx].strip('\'\"')
                        gth = json.loads(raw)
                        ext_map = {'j': 'jpg', 'p': 'png', 'w': 'webp'}
                        pages = []
                        for p_num in sorted(gth.keys(), key=int):
                            spec = gth[p_num]
                            ext = ext_map.get(spec.split(',')[0], 'jpg')
                            pages.append(f"{base_url}{p_num}.{ext}")
                        if pages:
                            return pages
        except Exception:
            pass

        # Fallback: inspect gallery page thumbnails
        thumb_urls = []
        for img in soup.select(".gallery_thumb img, .preview_thumb img, .thumb img"):
            src = img.get("data-src") or img.get("src") or ""
            if "thumb.jpg" not in src and re.search(r'\d+t\.(?:jpg|png|webp)', src):
                thumb_urls.append(src)

        dedup = list(dict.fromkeys(thumb_urls))
        if dedup:
            return [re.sub(r't(\.(?:jpg|png|webp))$', r'\1', u) for u in dedup]

        return []

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        return None

