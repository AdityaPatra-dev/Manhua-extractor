import re
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from bs4 import BeautifulSoup
import requests

from .base import BaseExtractor

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://hitomi.la/",
    "Accept": "*/*",
}

# Cached GG routing parameters
_GG_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "b": "1792922401/",
    "default_o": 0,
    "case_o": 1,
    "cases": set()
}


class HitomiExtractor(BaseExtractor):
    engine_id: str = "hitomi"
    name: str = "Hitomi.la"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower = (url or "").lower()
        return "hitomi.la" in lower or "gold-usergeneratedcontent.net" in lower

    @staticmethod
    def extract_gallery_id(url: str) -> Optional[int]:
        """Extract gallery ID integer from any hitomi.la URL."""
        if not url:
            return None
        # Clean query/hash parameters
        clean_url = url.split("?")[0].split("#")[0].rstrip("/")
        # Regex matching /<category>/<name>-<id>.html or /reader/<id>.html or /galleries/<id>.html
        m = re.search(r'[-/](\d+)\.html$', clean_url, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
        # Fallback: any trailing sequence of digits
        m_digits = re.findall(r'(\d+)', clean_url)
        if m_digits:
            try:
                return int(m_digits[-1])
            except ValueError:
                pass
        return None

    @classmethod
    def get_gg_params(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch and dynamically parse Hitomi's gg.js routing rules with 1-hour in-memory cache."""
        now = time.time()
        if not force_refresh and (now - _GG_CACHE["timestamp"]) < 3600 and _GG_CACHE["b"]:
            return _GG_CACHE

        try:
            r = requests.get(
                "https://ltn.gold-usergeneratedcontent.net/gg.js",
                headers=DEFAULT_HEADERS,
                timeout=10
            )
            if r.status_code == 200 and r.text:
                text = r.text
                b_match = re.search(r"b:\s*'([^']+)'", text)
                b_val = b_match.group(1) if b_match else _GG_CACHE["b"]

                default_o_match = re.search(r'var\s+o\s*=\s*(\d+);', text)
                default_o = int(default_o_match.group(1)) if default_o_match else 0

                case_o_match = re.search(r'o\s*=\s*(\d+);\s*break;', text)
                case_o = int(case_o_match.group(1)) if case_o_match else (1 - default_o)

                cases = set(map(int, re.findall(r'case\s+(\d+):', text)))

                _GG_CACHE["timestamp"] = now
                _GG_CACHE["b"] = b_val
                _GG_CACHE["default_o"] = default_o
                _GG_CACHE["case_o"] = case_o
                _GG_CACHE["cases"] = cases
        except Exception:
            pass

        return _GG_CACHE

    @classmethod
    def build_image_url(cls, image_hash: str, ext: str = "webp") -> str:
        """Construct full-resolution CDN image URL using dynamic gg routing."""
        if not image_hash or len(image_hash) < 3:
            return ""

        gg = cls.get_gg_params()
        m1 = image_hash[-3:-1]
        m2 = image_hash[-1]
        try:
            g = int(m2 + m1, 16)
        except ValueError:
            g = 0
        s_val = str(g)

        m_val = gg["case_o"] if g in gg["cases"] else gg["default_o"]

        if ext == "webp":
            subdomain = f"w{1 + m_val}"
        elif ext == "avif":
            subdomain = f"a{1 + m_val}"
        else:
            subdomain = f"{chr(97 + m_val)}a"

        return f"https://{subdomain}.gold-usergeneratedcontent.net/{gg['b']}{s_val}/{image_hash}.{ext}"

    @classmethod
    def build_thumbnail_url(cls, image_hash: str) -> str:
        """Construct big thumbnail URL."""
        if not image_hash or len(image_hash) < 3:
            return ""
        return f"https://atn.gold-usergeneratedcontent.net/webpbigtn/{image_hash[-1]}/{image_hash[-3:-1]}/{image_hash}.webp"

    @classmethod
    def fetch_gallery_info(cls, gallery_id: int) -> Optional[Dict[str, Any]]:
        """Fetch static gallery JSON metadata from ltn CDN."""
        url = f"https://ltn.gold-usergeneratedcontent.net/galleries/{gallery_id}.js"
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=12)
            if r.status_code == 200 and r.text:
                m = re.search(r'var\s+galleryinfo\s*=\s*(\{.*\})', r.text, re.DOTALL)
                if m:
                    return json.loads(m.group(1))
        except Exception:
            pass
        return None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        gid = self.extract_gallery_id(url)
        if not gid:
            return info

        ginfo = self.fetch_gallery_info(gid)
        if not ginfo:
            return info

        title = ginfo.get("title") or ginfo.get("japanese_title") or f"Gallery {gid}"
        info["title"] = title
        info["slug"] = f"hitomi-{gid}"

        files = ginfo.get("files", [])
        if files and files[0].get("hash"):
            info["cover_url"] = self.build_thumbnail_url(files[0]["hash"])

        # Extract artists
        artists = [a.get("artist") for a in (ginfo.get("artists") or []) if a and a.get("artist")]
        if artists:
            info["author"] = ", ".join(artists)

        # Tags and characters
        tags = [t.get("tag") for t in (ginfo.get("tags") or []) if t and t.get("tag")]
        characters = [c.get("character") for c in (ginfo.get("characters") or []) if c and c.get("character")]
        parodies = [p.get("parody") for p in (ginfo.get("parodys") or []) if p and p.get("parody")]

        desc_lines = []
        if ginfo.get("type"):
            desc_lines.append(f"Type: {ginfo.get('type').title()}")
        if ginfo.get("language"):
            desc_lines.append(f"Language: {ginfo.get('language').title()}")
        if artists:
            desc_lines.append(f"Artist(s): {', '.join(artists)}")
        if parodies:
            desc_lines.append(f"Series/Parody: {', '.join(parodies)}")
        if characters:
            desc_lines.append(f"Character(s): {', '.join(characters)}")
        if tags:
            desc_lines.append(f"Tags: {', '.join(tags)}")

        info["description"] = "\n".join(desc_lines)
        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        gid = self.extract_gallery_id(url)
        if not gid:
            return super().extract_chapter_list(soup, url, html)

        ginfo = self.fetch_gallery_info(gid)
        file_count = len(ginfo.get("files", [])) if ginfo else 0
        disp_title = f"Complete ({file_count} Pages)" if file_count > 0 else "Complete Work"

        return [
            {
                "chapter_num": 1.0,
                "title": disp_title,
                "url": f"https://hitomi.la/reader/{gid}.html"
            }
        ]

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        gid = self.extract_gallery_id(url)
        if not gid:
            return []

        ginfo = self.fetch_gallery_info(gid)
        if not ginfo or not ginfo.get("files"):
            return []

        pages: List[str] = []
        for f in ginfo["files"]:
            h = f.get("hash")
            if h:
                pages.append(self.build_image_url(h, ext="webp"))

        return pages

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        return None
