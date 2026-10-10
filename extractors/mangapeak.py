import re
import time
import datetime
import hashlib
import requests
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from .base import BaseExtractor

class MangaPeakExtractor(BaseExtractor):
    """
    Extractor for MangaPeak theme sites (e.g. RoliaScan).
    These sites use authenticated/tokenized REST endpoints:
    - /auth/chapter-content?chapter_id=...
    - /auth/manga-chapters?manga_id=... with dynamic md5 anti-scraping tokens
    """
    engine_id: str = "mangapeak"
    name: str = "MangaPeak (RoliaScan)"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        if "roliascan.com" in url or "mangapeak" in html:
            return True
        if soup.select_one("#reader-media, #tab-chapters, body[data-chapter-id], body[data-manga-id]"):
            return True
        return False

    def extract_chapter_number(self, url: str, title: Optional[str] = None) -> float:
        # Match RoliaScan format like /ch1-328363/
        m = re.search(r'/ch(\d+(?:\.\d+)?)-\d+', url, re.I)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return super().extract_chapter_number(url, title)

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        
        # RoliaScan covers are often in media tags with 'cover' in the filename
        cover_cand = soup.select_one("img[src*='cover'], img[data-src*='cover'], .comic-info img, .summary_image img")
        if cover_cand:
            src = cover_cand.get("src") or cover_cand.get("data-src")
            if src and src.startswith("http"):
                info["cover_url"] = src

        return info

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        # 1. Look for explicit next chapter links
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if "next chapter" in text or "next" == text:
                href = a["href"].strip()
                if "/read/" in href and href != current_url:
                    return href
        # 2. Heuristic selector
        for a in soup.select("a.ch-next-btn, a[rel='next'], a.next-chapter"):
            href = a.get("href", "").strip()
            if href and href != current_url:
                return href
        return None

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        parsed = urlparse(url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Identify chapter_id
        chapter_id = None
        body = soup.find("body")
        if body and body.get("data-chapter-id"):
            chapter_id = body.get("data-chapter-id")
        
        if not chapter_id:
            m = re.search(r'/ch\d+-(\d+)', url)
            if m:
                chapter_id = m.group(1)

        # 2. Fetch images from /auth/chapter-content API
        if chapter_id:
            try:
                api_url = f"{base_origin}/auth/chapter-content?chapter_id={chapter_id}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": url,
                    "Accept": "application/json"
                }
                resp = requests.get(api_url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and data.get("images"):
                        return self.deduplicate_urls(data["images"])
            except Exception:
                pass

        # Fallback to DOM parsing
        return super().extract_pages(soup, url, html)

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        parsed = urlparse(url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Identify manga_id
        manga_id = None
        body = soup.find("body")
        if body and body.get("data-manga-id"):
            manga_id = body.get("data-manga-id")
        
        if not manga_id:
            cl = soup.select_one(".chapter-list[data-manga-id]")
            if cl:
                manga_id = cl.get("data-manga-id")
        
        if not manga_id:
            m = re.search(r'data-manga-id=[\"\'](\d+)[\"\']', html)
            if m:
                manga_id = m.group(1)

        # 2. Query authenticated /auth/manga-chapters endpoint using MD5 anti-scraping token
        if manga_id:
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                hour = now.strftime("%Y%m%d%H")
                timestamp = int(time.time())
                secret = f"mng_ch_{hour}"
                token = hashlib.md5(f"{timestamp}{secret}".encode()).hexdigest()[:16]

                api_url = f"{base_origin}/auth/manga-chapters?manga_id={manga_id}&offset=0&limit=500&order=ASC&_t={token}&_ts={timestamp}"
                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": url,
                    "Accept": "application/json"
                }
                resp = requests.get(api_url, headers=headers, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") and data.get("chapters"):
                        result = []
                        seen_urls = set()
                        for c in data["chapters"]:
                            ch_url = c.get("url")
                            if not ch_url or ch_url in seen_urls:
                                continue
                            seen_urls.add(ch_url)
                            ch_raw = str(c.get("chapter") or "1")
                            try:
                                ch_num = float(ch_raw)
                            except ValueError:
                                ch_num = 1.0
                            
                            custom_title = c.get("title")
                            if custom_title and custom_title not in ("N/A", "", "None"):
                                title_str = f"Chapter {ch_raw}: {custom_title}"
                            else:
                                title_str = f"Chapter {ch_raw}"

                            result.append({
                                "chapter_num": ch_num,
                                "title": title_str,
                                "url": ch_url
                            })
                        if result:
                            return result
            except Exception:
                pass

        # Fallback to standard selector list
        return super().extract_chapter_list(soup, url, html)
