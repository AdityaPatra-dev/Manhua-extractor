import re
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from .base import BaseExtractor

class MangaStreamExtractor(BaseExtractor):
    engine_id: str = "mangastream"
    name: str = "MangaStream / Themeia"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        if soup.find(id="readerarea") or soup.find(class_="reader-area"):
            return True
        if soup.find(class_="container-chapter-reader"):
            return True
        if "ts_reader" in html or "mangastream" in html.lower() or "themeia" in html.lower():
            return True
        if "themes/liliana" in html or "/ajax/image/list/chap/" in html:
            return True
        return False

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # 0. Check for Liliana AJAX chapter loading
        m_chap = re.search(r'CHAPTER_ID\s*=\s*[\"\']?(\d+)', html)
        if m_chap and "/ajax/image/list/chap/" in html:
            chap_id = m_chap.group(1)
            ajax_url = f"{base_url}/ajax/image/list/chap/{chap_id}"
            try:
                import cloudscraper
                s = cloudscraper.create_scraper()
                ajax_resp = s.post(
                    ajax_url,
                    headers={"Referer": url, "X-Requested-With": "XMLHttpRequest"},
                    timeout=15
                )
                if ajax_resp.status_code == 200:
                    ajax_data = ajax_resp.json()
                    if ajax_data.get("status") and ajax_data.get("html"):
                        ajax_soup = BeautifulSoup(ajax_data["html"], "html.parser")
                        ajax_urls = []
                        for a in ajax_soup.find_all("a", class_="readImg"):
                            href = a.get("href")
                            if href and href.startswith("http"):
                                clean = self.clean_image_url(href, base_url)
                                if clean:
                                    ajax_urls.append(clean)
                        if not ajax_urls:
                            for im in ajax_soup.find_all("img"):
                                u = im.get("data-src") or im.get("src")
                                clean = self.clean_image_url(u, base_url)
                                if clean:
                                    ajax_urls.append(clean)
                        if ajax_urls:
                            return self.deduplicate_urls(ajax_urls)
            except Exception:
                pass

        # 1. Check for inline JSON payload (ts_reader.run)
        m = re.search(r'ts_reader\.run\(\s*(\{.+?\})\s*\);', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                sources = data.get("sources", [])
                if sources and isinstance(sources, list):
                    images = sources[0].get("images", [])
                    clean_urls = []
                    for img in images:
                        clean = self.clean_image_url(img, base_url)
                        if clean:
                            clean_urls.append(clean)
                    if clean_urls:
                        return self.deduplicate_urls(clean_urls)
            except Exception:
                pass

        # 2. Extract from reader container
        container = (
            soup.find(id="readerarea") or
            soup.find(class_="reader-area") or
            soup.find(class_="container-chapter-reader")
        )

        images = container.find_all("img") if container else []
        if not images:
            images = soup.find_all("img", class_=lambda x: x and any(c in x for c in ["chapter-img", "ts-main-image"]))

        raw_urls = []
        for img in images:
            val = (
                img.get("data-src") or
                img.get("data-lazy-src") or
                img.get("data-url") or
                img.get("src")
            )
            clean = self.clean_image_url(val, base_url)
            if clean:
                raw_urls.append(clean)

        return self.deduplicate_urls(raw_urls)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        # 1. Check ts_reader.run payload
        m = re.search(r'ts_reader\.run\(\s*(\{.+?\})\s*\);', str(soup), re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                next_url = data.get("nextUrl")
                if next_url and next_url.startswith("http") and next_url != current_url:
                    return next_url
            except Exception:
                pass

        candidates = [
            soup.select_one("div.nextprev a.ch-next-btn"),
            soup.select_one("div.nextprev a[rel='next']"),
            soup.select_one("div.nav-next a"),
            soup.select_one("a.ch-next-btn"),
            soup.select_one("a.rght"),
            soup.select_one("a[rel='next']")
        ]

        for cand in candidates:
            if cand and cand.get("href"):
                href = cand["href"].strip()
                if href and href != "#" and href != current_url and href.startswith("http"):
                    return href
        return None
