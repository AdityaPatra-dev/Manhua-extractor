import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from .base import BaseExtractor

class AggregatorExtractor(BaseExtractor):
    engine_id: str = "aggregator"
    name: str = "Aggregator (Manganato / Kakalot / MangaBuddy)"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower_url = url.lower()
        if any(host in lower_url for host in ["manganato", "mangakakalot", "mangabuddy", "readmanganato"]):
            return True
        if soup.find(class_="container-chapter-reader") and soup.find(class_="navi-change-chapter"):
            return True
        if soup.find(class_="panel-read-story"):
            return True
        return False

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        container = (
            soup.find(class_="container-chapter-reader") or
            soup.find(class_="panel-read-story") or
            soup.find(id="chapter-images") or
            soup.find(class_="chapter-content")
        )

        images = container.find_all("img") if container else []
        raw_urls = []
        for img in images:
            val = img.get("src") or img.get("data-src")
            clean = self.clean_image_url(val, base_url)
            if clean:
                raw_urls.append(clean)

        return self.deduplicate_urls(raw_urls)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        candidates = [
            soup.select_one("a.navi-change-chapter-btn-next"),
            soup.select_one("a.btn-next"),
            soup.select_one("a.next-btn"),
            soup.select_one("div.navi-change-chapter a.next"),
            soup.select_one("a[rel='next']")
        ]

        for cand in candidates:
            if cand and cand.get("href"):
                href = cand["href"].strip()
                if href and href != "#" and href != current_url and href.startswith("http"):
                    return href
        return None

