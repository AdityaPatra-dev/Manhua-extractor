from __future__ import annotations

import re
import json
import urllib.parse
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests

from .base import BaseExtractor

HIPERDEX_AUTH_HEADER = "x-cfg-auth"
HIPERDEX_AUTH_VAL = "yceqt7qgu004"
HIPERDEX_BASE = "https://hiperdex.tv"

class HiperdexExtractor(BaseExtractor):
    engine_id: str = "hiperdex"
    name: str = "Hiperdex tRPC Engine"

    def __init__(self):
        super().__init__()
        self._session = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Origin": HIPERDEX_BASE,
                "Referer": f"{HIPERDEX_BASE}/",
                HIPERDEX_AUTH_HEADER: HIPERDEX_AUTH_VAL
            })
            try:
                s.get(f"{HIPERDEX_BASE}/", timeout=8)
            except Exception:
                pass
            self._session = s
        return self._session

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower = url.lower()
        return "hiperdex.com" in lower or "hiperdex.tv" in lower

    def _extract_slug_and_ch_num(self, url: str) -> tuple[str, Optional[float]]:
        # e.g. https://hiperdex.tv/manga/excuse-me-this-is-my-room-16524ba3/120
        # or https://hiperdex.tv/manga/excuse-me-this-is-my-room-16524ba3
        parsed = urlparse(url)
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        slug = ""
        ch_num = None
        if len(parts) >= 2 and parts[0] == "manga":
            slug = parts[1]
            if len(parts) >= 3:
                try:
                    ch_num = float(parts[2])
                except ValueError:
                    pass
        elif len(parts) == 1:
            slug = parts[0]
        return slug, ch_num

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        slug, _ = self._extract_slug_and_ch_num(url)
        info = super().extract_series_info(soup, url, html)
        if not slug:
            return info

        s = self._get_session()
        try:
            q_url = f"{HIPERDEX_BASE}/api/trpc/series.bySlug?input=" + urllib.parse.quote(json.dumps({"json": {"slug": slug}}))
            r = s.get(q_url, timeout=10)
            if r.status_code == 200:
                data = r.json().get("result", {}).get("data", {}).get("json", {})
                if data:
                    title = data.get("title") or info.get("title")
                    cover = data.get("coverUrl") or data.get("thumbnailUrl") or info.get("cover_url")
                    synopsis = data.get("synopsis") or ""
                    return {
                        "title": title,
                        "slug": slug,
                        "cover_url": cover,
                        "synopsis": synopsis,
                        "series_id": data.get("id")
                    }
        except Exception:
            pass

        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        slug, _ = self._extract_slug_and_ch_num(url)
        if not slug:
            return super().extract_chapter_list(soup, url, html)

        s = self._get_session()
        try:
            # 1. Resolve series ID from slug
            q_url = f"{HIPERDEX_BASE}/api/trpc/series.bySlug?input=" + urllib.parse.quote(json.dumps({"json": {"slug": slug}}))
            r = s.get(q_url, timeout=10)
            if r.status_code != 200:
                return []
            series_data = r.json().get("result", {}).get("data", {}).get("json", {})
            series_id = series_data.get("id")
            if not series_id:
                return []

            # 2. Get chapters
            ch_url = f"{HIPERDEX_BASE}/api/trpc/series.chapters?input=" + urllib.parse.quote(json.dumps({"json": {"seriesId": series_id}}))
            r_ch = s.get(ch_url, timeout=12)
            if r_ch.status_code != 200:
                return []
            raw_chaps = r_ch.json().get("result", {}).get("data", {}).get("json", [])

            chapters = []
            for ch in raw_chaps:
                num = ch.get("number")
                if num is None:
                    continue
                ch_title = ch.get("title") or f"Chapter {num:g}"
                ch_page_url = f"{HIPERDEX_BASE}/manga/{slug}/{num}"
                chapters.append({
                    "chapter_num": float(num),
                    "title": ch_title,
                    "url": ch_page_url,
                    "chapter_id": ch.get("id")
                })

            chapters.sort(key=lambda x: x["chapter_num"])
            return chapters
        except Exception:
            pass

        return super().extract_chapter_list(soup, url, html)

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        slug, ch_num = self._extract_slug_and_ch_num(url)
        if not slug:
            return super().extract_pages(soup, url, html)

        s = self._get_session()
        try:
            # 1. Resolve series ID to get chapter list
            q_url = f"{HIPERDEX_BASE}/api/trpc/series.bySlug?input=" + urllib.parse.quote(json.dumps({"json": {"slug": slug}}))
            r = s.get(q_url, timeout=10)
            if r.status_code != 200:
                return []
            series_data = r.json().get("result", {}).get("data", {}).get("json", {})
            series_id = series_data.get("id")

            # 2. Find matching chapter ID
            ch_url = f"{HIPERDEX_BASE}/api/trpc/series.chapters?input=" + urllib.parse.quote(json.dumps({"json": {"seriesId": series_id}}))
            r_ch = s.get(ch_url, timeout=12)
            if r_ch.status_code != 200:
                return []
            raw_chaps = r_ch.json().get("result", {}).get("data", {}).get("json", [])

            target_chapter_id = None
            for ch in raw_chaps:
                if ch_num is not None and ch.get("number") == ch_num:
                    target_chapter_id = ch.get("id")
                    break
            
            if not target_chapter_id and raw_chaps:
                target_chapter_id = raw_chaps[-1].get("id")
                ch_num = raw_chaps[-1].get("number")

            if not target_chapter_id:
                return []

            # 3. Query chapterPages
            pg_url = f"{HIPERDEX_BASE}/api/trpc/reader.chapterPages?input=" + urllib.parse.quote(json.dumps({
                "json": {"seriesSlug": slug, "chapterNumber": ch_num, "chapterId": target_chapter_id}
            }))
            r_pg = s.get(pg_url, timeout=12)
            if r_pg.status_code != 200:
                return []

            pages_raw = r_pg.json().get("result", {}).get("data", {}).get("json", [])
            urls = []
            for p in pages_raw:
                if isinstance(p, dict):
                    img_u = p.get("webpUrl") or p.get("avifUrl") or p.get("url")
                    if img_u:
                        urls.append(img_u)
                elif isinstance(p, str):
                    urls.append(p)

            clean = [self.clean_image_url(u, HIPERDEX_BASE) for u in urls if u]
            clean = [u for u in clean if u]
            if clean:
                return self.deduplicate_urls(clean)
        except Exception:
            pass

        return super().extract_pages(soup, url, html)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        slug, ch_num = self._extract_slug_and_ch_num(current_url)
        if slug and ch_num is not None:
            return f"{HIPERDEX_BASE}/manga/{slug}/{ch_num + 1:g}"
        return None

