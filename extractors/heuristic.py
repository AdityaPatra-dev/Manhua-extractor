import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from .base import BaseExtractor

class HeuristicExtractor(BaseExtractor):
    engine_id: str = "heuristic"
    name: str = "Universal Heuristic Fallback"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        # Fallback catches everything
        return True

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Find the container with the largest density of chapter panel images
        containers = soup.find_all(["div", "article", "main", "section"])
        best_container = None
        max_valid_images = 0

        for c in containers:
            imgs = c.find_all("img")
            if len(imgs) > max_valid_images:
                valid_count = sum(1 for img in imgs if self._is_potential_panel(img))
                if valid_count > max_valid_images:
                    max_valid_images = valid_count
                    best_container = c

        images = best_container.find_all("img") if best_container else soup.find_all("img")

        raw_urls = []
        for img in images:
            if not self._is_potential_panel(img):
                continue
            val = (
                img.get("data-src") or
                img.get("data-lazy-src") or
                img.get("data-original") or
                img.get("data-url") or
                img.get("src")
            )
            clean = self.clean_image_url(val, base_url)
            if clean:
                raw_urls.append(clean)

        return self.deduplicate_urls(raw_urls)

    def _is_potential_panel(self, img) -> bool:
        src = (img.get("data-src") or img.get("src") or "").lower()
        if not src or src.startswith("data:"):
            return False

        # Filter out comments, avatars, widgets, and footers via parent hierarchy
        parent = img.find_parent()
        while parent:
            classes = " ".join(parent.get("class", [])).lower()
            pid = str(parent.get("id", "")).lower()
            if any(bad in classes or bad in pid for bad in [
                "comment", "disqus", "author", "user-profile", "sidebar", "widget", "footer"
            ]):
                return False
            parent = parent.find_parent()

        filename = src.split("?")[0].split("/")[-1]
        if any(bad in filename for bad in ["logo", "icon", "banner", "loader", "discord", "patreon"]):
            return False
        if re.search(r'[-_.]avatar[-_.]|^avatar[-_.]', filename):
            return False
        if any(bad in src for bad in ["/ads/", "/ad/", "-ads-", "_ads_", "/advertisement/"]):
            return False

        return True

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        # 1. Check link text cues
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            rel = a.get("rel", "")
            if "next" in text or "›" in text or "»" in text or "next" in rel:
                href = a["href"].strip()
                if href and href != "#" and href != current_url and href.startswith("http"):
                    return href

        # 2. Heuristic URL incrementation fallback
        m = re.search(r'(chapter[-/])(\d+)', current_url, re.I)
        if m:
            prefix = m.group(1)
            num = int(m.group(2))
            next_url = current_url[:m.start()] + f"{prefix}{num + 1}" + current_url[m.end():]
            return next_url

        return None

