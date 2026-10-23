import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from .base import BaseExtractor

class MadaraExtractor(BaseExtractor):
    engine_id: str = "madara"
    name: str = "WordPress Madara"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        """Check for WordPress Madara theme signatures."""
        if soup.find(class_="wp-manga-chapter-img"):
            return True
        if soup.find(class_="reading-content"):
            return True
        if soup.find(class_="single-chapter-select"):
            return True
        if soup.find(class_="page-break"):
            return True
        if "wp-manga" in html.lower() or "madara" in html.lower():
            return True
        return False

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)

        # Madara breadcrumb often points to main series
        breadcrumb = soup.select("div.c-breadcrumb ol.breadcrumb li a, div.breadcrumbs a")
        categories = {"home", "manga", "manhua", "manhwa", "webtoon", "comics", "comic", "series"}
        for b in reversed(breadcrumb):
            txt = b.get_text(strip=True)
            if txt and txt.lower() not in categories and not re.search(r'chapter\s*\d+', txt, re.I):
                info["title"] = txt
                break

        # Better slug detection from Madara URL
        m = re.search(r'/(?:manga|manhua|manhwa|webtoon|series|comic)/([^/]+)/', url, re.I)
        if m:
            info["slug"] = m.group(1)

        return info

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Target all Madara reader containers
        images = []
        reading_container = soup.find(class_="reading-content")
        if reading_container:
            images = reading_container.find_all("img")

        if not images:
            # Check page-break containers
            page_breaks = soup.find_all(class_="page-break")
            for pb in page_breaks:
                images.extend(pb.find_all("img"))

        if not images:
            # Direct class search
            images = soup.find_all("img", class_=lambda x: x and "wp-manga-chapter-img" in x)

        if not images:
            # Fallback within entry content
            entry = soup.find(class_="entry-content-wrap")
            if entry:
                images = entry.find_all("img")

        attr_priority = [
            "data-src",
            "data-lazy-src",
            "data-original",
            "data-full-url",
            "data-cdn",
            "data-wpfc-original-src",
            "src"
        ]

        raw_urls = []
        for img in images:
            img_url = None
            for attr in attr_priority:
                val = img.get(attr)
                if val and isinstance(val, str) and not val.strip().startswith("data:image"):
                    clean = self.clean_image_url(val, base_url)
                    if clean:
                        img_url = clean
                        break
            if img_url:
                raw_urls.append(img_url)

        return self.deduplicate_urls(raw_urls)

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        has_ajax_holder = bool(soup.select_one("#manga-chapters-holder, .manga-chapters-data, div[data-id]"))

        # Check manga_id in script or DOM attributes
        manga_id = None
        id_match = re.search(r'["\']manga[_-]?id["\']\s*[:=]\s*["\']?(\d+)["\']?', html, re.I)
        if not id_match:
            id_match = re.search(r'manga[_-]?id[\"\'\s:=]+(\d+)', html, re.I)
        if id_match:
            manga_id = id_match.group(1)
        if not manga_id:
            for el in soup.select('[data-id], #manga-chapters-holder, .manga-chapters-data'):
                val = el.get("data-id") or el.get("data-post") or el.get("data-manga")
                if val and val.isdigit():
                    manga_id = val
                    break

        # Check script for manga.base_url or canonical link
        m_base = re.search(r'["\']base_url["\']:\s*["\']([^"\']+)["\']', html)
        if m_base:
            base_series_url = m_base.group(1).replace(r'\/', '/').replace('\\/', '/')
        else:
            canonical = soup.select_one("link[rel='canonical']")
            if canonical and canonical.get("href"):
                base_series_url = canonical["href"].rstrip('/') + '/'
            else:
                base_series_url = re.sub(r'/(?:chapter|ch|c|ajax)[-_/\d].*$', '/', url, flags=re.I)
        if not base_series_url.endswith('/'):
            base_series_url += '/'

        def _fetch_madara_ajax(endpoint: str, data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
            try:
                import requests
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Referer": base_series_url,
                    "X-Requested-With": "XMLHttpRequest"
                }
                try:
                    from database.db import get_clearance_cookie
                    domain = urlparse(base_series_url).netloc
                    cached = get_clearance_cookie(domain)
                    if cached:
                        headers["Cookie"] = cached["cookie_string"]
                        if cached.get("user_agent"):
                            headers["User-Agent"] = cached["user_agent"]
                except Exception:
                    pass

                resp = requests.post(endpoint, data=data, headers=headers, timeout=12)
                if resp.status_code == 200 and resp.text:
                    ajax_soup = BeautifulSoup(resp.text, "html.parser")
                    ajax_chapters = super(MadaraExtractor, self).extract_chapter_list(ajax_soup, base_series_url, resp.text)
                    if ajax_chapters:
                        return ajax_chapters
            except Exception:
                pass
            return []

        # 1. Try admin-ajax.php if manga_id is present
        if manga_id:
            admin_ajax_endpoint = urljoin(base_series_url, "/wp-admin/admin-ajax.php")
            admin_chapters = _fetch_madara_ajax(admin_ajax_endpoint, {"action": "manga_get_chapters", "manga": manga_id})
            if admin_chapters:
                return admin_chapters

        # 2. Try direct /ajax/chapters/ endpoint if dynamic container is present
        if has_ajax_holder:
            ajax_endpoint = base_series_url.rstrip('/') + "/ajax/chapters/"
            ajax_chapters = _fetch_madara_ajax(ajax_endpoint)
            if ajax_chapters:
                return ajax_chapters

        # 3. Extract from initial DOM
        chapters = super().extract_chapter_list(soup, url, html)
        if chapters:
            return chapters

        # 4. Fallback to /ajax/chapters/ or admin-ajax if no chapters in DOM
        ajax_endpoint = base_series_url.rstrip('/') + "/ajax/chapters/"
        ajax_chapters = _fetch_madara_ajax(ajax_endpoint)
        if ajax_chapters:
            return ajax_chapters

        if manga_id:
            admin_ajax_endpoint = urljoin(base_series_url, "/wp-admin/admin-ajax.php")
            admin_chapters = _fetch_madara_ajax(admin_ajax_endpoint, {"action": "manga_get_chapters", "manga": manga_id})
            if admin_chapters:
                return admin_chapters

        return chapters

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        # Madara next button
        candidates = [
            soup.select_one("div.nav-next a.next_page"),
            soup.select_one("a.next_page"),
            soup.select_one("a.btn.next_post"),
            soup.select_one("div.nav-links div.nav-next a"),
            soup.select_one("div.nav-next a"),
            soup.select_one("a[rel='next']")
        ]

        for cand in candidates:
            if cand and cand.get("href"):
                href = cand["href"].strip()
                if href and href != "#" and href != current_url and href.startswith("http"):
                    return href

        # Check dropdown select
        select = soup.select_one("select.single-chapter-select, select.selectpicker, select#single-pager")
        if select:
            options = select.find_all("option")
            for i, opt in enumerate(options):
                val = opt.get("value") or opt.get("data-redirect")
                if val and val in current_url:
                    # In Madara, chapters are often listed in descending order (newest first).
                    # Check next or previous index
                    if i > 0:
                        prev_val = options[i - 1].get("value") or options[i - 1].get("data-redirect")
                        if prev_val and prev_val.startswith("http") and prev_val != current_url:
                            # Let's verify if i-1 represents chapter+1
                            return prev_val
                    if i + 1 < len(options):
                        next_val = options[i + 1].get("value") or options[i + 1].get("data-redirect")
                        if next_val and next_val.startswith("http") and next_val != current_url:
                            return next_val

        return None
