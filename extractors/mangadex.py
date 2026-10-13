import re
import json
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import requests

from .base import BaseExtractor

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

class MangaDexExtractor(BaseExtractor):
    engine_id: str = "mangadex"
    name: str = "MangaDex (Official REST API)"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        return "mangadex.org" in url or "api.mangadex.org" in url

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        m = re.search(r'/(?:title|manga)/([a-f0-9\-]+)', url, re.I)
        if not m:
            # Maybe a chapter URL; inspect chapter to get manga ID
            m_ch = re.search(r'/chapter/([a-f0-9\-]+)', url, re.I)
            if m_ch:
                ch_id = m_ch.group(1)
                try:
                    r = requests.get(f"https://api.mangadex.org/chapter/{ch_id}", headers=DEFAULT_HEADERS, timeout=10)
                    if r.status_code == 200:
                        ch_data = r.json().get("data", {})
                        for rel in ch_data.get("relationships", []):
                            if rel.get("type") == "manga":
                                m = re.search(r'([a-f0-9\-]+)', rel.get("id", ""))
                                break
                except Exception:
                    pass

        if m:
            manga_id = m.group(1)
            try:
                r = requests.get(f"https://api.mangadex.org/manga/{manga_id}?includes[]=cover_art", headers=DEFAULT_HEADERS, timeout=10)
                if r.status_code == 200:
                    data = r.json().get("data", {})
                    attr = data.get("attributes", {})
                    title_dict = attr.get("title", {})
                    title = title_dict.get("en") or next(iter(title_dict.values()), "Unknown Series")
                    info["title"] = title
                    info["slug"] = manga_id

                    cover_file = None
                    for rel in data.get("relationships", []):
                        if rel.get("type") == "cover_art":
                            cover_file = rel.get("attributes", {}).get("fileName")
                            break
                    if cover_file:
                        info["cover_url"] = f"https://uploads.mangadex.org/covers/{manga_id}/{cover_file}.512.jpg"
            except Exception:
                pass

        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        m = re.search(r'/(?:title|manga)/([a-f0-9\-]+)', url, re.I)
        if not m:
            m_ch = re.search(r'/chapter/([a-f0-9\-]+)', url, re.I)
            if m_ch:
                ch_id = m_ch.group(1)
                try:
                    r = requests.get(f"https://api.mangadex.org/chapter/{ch_id}", headers=DEFAULT_HEADERS, timeout=10)
                    if r.status_code == 200:
                        ch_data = r.json().get("data", {})
                        for rel in ch_data.get("relationships", []):
                            if rel.get("type") == "manga":
                                m = re.search(r'([a-f0-9\-]+)', rel.get("id", ""))
                                break
                except Exception:
                    pass

        if not m:
            return super().extract_chapter_list(soup, url, html)

        manga_id = m.group(1)
        chapters: List[Dict[str, Any]] = []
        try:
            # Query chapters in English first, fall back to all languages if 0
            for lang_param in ["&translatedLanguage[]=en", ""]:
                feed_url = f"https://api.mangadex.org/manga/{manga_id}/feed?order[chapter]=asc&limit=500{lang_param}"
                r = requests.get(feed_url, headers=DEFAULT_HEADERS, timeout=15)
                if r.status_code == 200:
                    feed_data = r.json().get("data", [])
                    if feed_data:
                        seen_ch_nums = set()
                        for item in feed_data:
                            attr = item.get("attributes", {})
                            # Skip external publisher redirect chapters (e.g. Bilibili/Webnovel paywalled)
                            if attr.get("externalUrl"):
                                continue

                            raw_ch = attr.get("chapter") or "1"
                            try:
                                ch_num = float(raw_ch)
                            except ValueError:
                                ch_num = 1.0

                            # Avoid duplicate same-chapter uploads from different scan groups in catalog
                            if ch_num in seen_ch_nums:
                                continue
                            seen_ch_nums.add(ch_num)

                            ch_title = attr.get("title")
                            disp_title = f"Chapter {raw_ch}" + (f": {ch_title}" if ch_title else "")

                            chapters.append({
                                "chapter_num": ch_num,
                                "title": disp_title,
                                "url": f"https://mangadex.org/chapter/{item['id']}"
                            })
                    if chapters:
                        break
        except Exception:
            pass

        if chapters:
            chapters.sort(key=lambda x: x["chapter_num"])
            return chapters

        return super().extract_chapter_list(soup, url, html)

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        m = re.search(r'/chapter/([a-f0-9\-]+)', url, re.I)
        if not m:
            return []

        ch_id = m.group(1)
        try:
            r = requests.get(f"https://api.mangadex.org/at-home/server/{ch_id}", headers=DEFAULT_HEADERS, timeout=15)
            if r.status_code == 200:
                data = r.json()
                base_url = data.get("baseUrl")
                ch_hash = data.get("chapter", {}).get("hash")
                files = data.get("chapter", {}).get("data", []) or data.get("chapter", {}).get("dataSaver", [])
                if base_url and ch_hash and files:
                    return [f"{base_url}/data/{ch_hash}/{f}" for f in files]
        except Exception:
            pass
        return []

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        return None

