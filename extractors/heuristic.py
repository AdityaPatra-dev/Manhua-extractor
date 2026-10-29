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

        # 0a. Check for MangaKatana JS array variables (thzq has all panels, ytaw has preview)
        m_arr = re.search(r'var\s+thzq\s*=\s*(\[.*?\]);', html, re.DOTALL) or re.search(r'var\s+ytaw\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if m_arr:
            urls = re.findall(r"['\"](https?://[^'\"]+)['\"]", m_arr.group(1))
            clean = [self.clean_image_url(u, base_url) for u in urls if u]
            clean = [u for u in clean if u]
            if clean:
                return self.deduplicate_urls(clean)

        # 0b. Check for WeebCentral dynamic /images container
        if "weebcentral.com/chapters/" in url and not url.endswith("/images"):
            images_url = url.rstrip('/') + '/images'
            try:
                import requests
                r_img = requests.get(images_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=10)
                if r_img.status_code == 200:
                    sub_soup = BeautifulSoup(r_img.text, 'html.parser')
                    raw_urls = []
                    for img in sub_soup.find_all('img'):
                        val = img.get("src") or img.get("data-src")
                        clean = self.clean_image_url(val, base_url)
                        if clean:
                            raw_urls.append(clean)
                    if raw_urls:
                        return self.deduplicate_urls(raw_urls)
            except Exception:
                pass

        # 1. Target dedicated reader containers first
        reader_selectors = [
            "#readerarea",
            ".reader-area",
            "div.image-based",
            "div.chapter-content",
            "div.reading-content",
            "div.page-break",
            "div.vung-doc",
            "div.container-chapter-reader",
            ".chapter-images",
            ".comic-images"
        ]

        # 0. Check for client-side packed script reader (MangaFox, MangaHere, DM5 engines)
        if "eval(function(p,a,c,k" in html:
            packed_scripts = re.findall(r'<script[^>]*>(eval\(function\(p,a,c,k.*?)</script>', html, re.DOTALL)
            packed_imgs = []
            for script in packed_scripts:
                pattern = r"}\('(.*)',(\d+),(\d+),'(.*)'\.split\('\|'\)"
                pm = re.search(pattern, script)
                if not pm:
                    continue
                p, a, c, k = pm.group(1), int(pm.group(2)), int(pm.group(3)), pm.group(4).split('|')
                def base36(n):
                    alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
                    if n < len(alphabet): return alphabet[n]
                    return base36(n // len(alphabet)) + alphabet[n % len(alphabet)]
                k_dict = {base36(i): k[i] if i < len(k) and k[i] else base36(i) for i in range(c)}
                unpacked = re.sub(r'\b\w+\b', lambda mo: k_dict.get(mo.group(0), mo.group(0)), p).replace(r'\/', '/').replace(r"\'", "'")
                for im in re.finditer(r'(?:https?:)?//[a-zA-Z0-9_.\-]+?\.[a-zA-Z]{2,6}/[^\s\'\"\\]+?\.(?:jpg|jpeg|png|webp)(?:\?[^\s\'\"\\]*)?', unpacked):
                    u = im.group(0)
                    if u.startswith('//'):
                        u = 'https:' + u
                    clean = self.clean_image_url(u, base_url)
                    if clean:
                        packed_imgs.append(clean)
            if packed_imgs:
                return self.deduplicate_urls(packed_imgs)
        best_container = None
        for sel in reader_selectors:
            el = soup.select_one(sel)
            if el:
                candidate_imgs = [img for img in el.find_all("img") if self._is_potential_panel(img)]
                if len(candidate_imgs) >= 2:
                    best_container = el
                    break

        if not best_container:
            # Fallback to finding container with largest density of valid panel images
            containers = soup.find_all(["div", "article", "main", "section"])
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
                img.get("data-original-src") or
                img.get("data-src") or
                img.get("data-lazy-src") or
                img.get("data-original") or
                img.get("data-url") or
                img.get("data-cdn") or
                img.get("src")
            )
            clean = self.clean_image_url(val, base_url)
            if clean:
                raw_urls.append(clean)

        return self.deduplicate_urls(raw_urls)

    def _is_potential_panel(self, img) -> bool:
        src = (
            img.get("data-original-src") or
            img.get("data-src") or
            img.get("data-lazy-src") or
            img.get("data-original") or
            img.get("data-url") or
            img.get("data-cdn") or
            img.get("src") or
            ""
        ).strip().lower()
        if not src or src.startswith("data:"):
            return False

        # Filter out comments, avatars, widgets, and footers via parent hierarchy
        parent = img.find_parent()
        while parent:
            classes = " ".join(parent.get("class", [])).lower()
            pid = str(parent.get("id", "")).lower()
            if any(bad in classes or bad in pid for bad in [
                "comment", "disqus", "author", "user-profile", "sidebar", "widget", "footer",
                "slider", "carousel", "recommend", "related", "popular", "manga-block"
            ]):
                return False
            parent = parent.find_parent()

        filename = src.split("?")[0].split("/")[-1]
        if any(bad in filename for bad in ["logo", "icon", "banner", "loader", "discord", "patreon", "dflazy"]):
            return False
        if re.search(r'[-_.]avatar[-_.]|^avatar[-_.]', filename):
            return False
        if any(bad in src for bad in [
            "/ads/", "/ad/", "-ads-", "_ads_", "/advertisement/",
            "/themes/", "/wp-content/themes/", "about_", "to_be_continued"
        ]):
            return False

        return True

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        # 1. Check link text cues
        if soup is not None:
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True).lower()
                rel = a.get("rel", "")
                if "next" in text or "›" in text or "»" in text or "next" in rel:
                    href = a["href"].strip()
                    if href and href != "#" and href != current_url and href.startswith("http"):
                        return href

        # 2. Heuristic URL incrementation fallback
        clean = current_url.split('?')[0].rstrip('/')
        trailing_slash = current_url.split('?')[0].endswith('/')

        # Pattern A: explicit chapter/ep/ch keyword with number
        m = re.search(r'((?:[-_/]|^)(?:chapter|episode|ep|ch)[-_.]?)(\d+)', clean, re.I)
        if m:
            prefix = m.group(1)
            num = int(m.group(2))
            res = clean[:m.start()] + f"{prefix}{num + 1}" + clean[m.end():]
            return res + ("/" if trailing_slash else "")

        # Pattern B: trailing hyphen/underscore + number at end of slug (e.g. series-1)
        m = re.search(r'([-_])(\d+)$', clean)
        if m:
            sep = m.group(1)
            num = int(m.group(2))
            res = clean[:m.start()] + f"{sep}{num + 1}"
            return res + ("/" if trailing_slash else "")

        # Pattern C: trailing number in path (/123)
        m = re.search(r'(/)(\d+)$', clean)
        if m:
            sep = m.group(1)
            num = int(m.group(2))
            res = clean[:m.start()] + f"{sep}{num + 1}"
            return res + ("/" if trailing_slash else "")

        return None

