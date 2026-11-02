import re
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from .base import BaseExtractor


class HiveScansExtractor(BaseExtractor):
    """
    Dedicated Extractor for Hive Scans / Void Scans (hivetoons.org / void-scans.com).
    Features:
    - Normalizes legacy/mirrored domains (void-scans.com, voidscans.com, hivescans.com, hivetoon.com) to hivetoons.org.
    - Accurately extracts series metadata and full chapter lists.
    - Detects locked/paywalled (coin-protected) chapters and avoids downloading random preview/cover images.
    - Filters out promotional banners, thumbnails, and avatar images.
    """
    engine_id: str = "hivescans"
    name: str = "Hive Scans (Void Scans)"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower_url = url.lower()
        if any(d in lower_url for d in (
            "hivetoons.org", "hivetoons.com", "hivetoon.com",
            "hivescans.com", "void-scans.com", "voidscans.com"
        )):
            return True
        if "__VCOMICS_RENDER_NOW__" in html or "storage.hivetoon.com" in html:
            return True
        return False

    def _normalize_url(self, url: str) -> str:
        for d in ("void-scans.com", "voidscans.com", "hivescans.com", "hivetoon.com", "hivetoons.com"):
            if d in url:
                url = url.replace(d, "hivetoons.org")
        return url

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)

        # Title
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            info["title"] = h1.get_text(strip=True)

        # Cover image
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            info["cover_url"] = og_img["content"]
        else:
            # Check featured/cover image in header
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if "/featured/" in src or "/series/" in src:
                    info["cover_url"] = src
                    break

        # Synopsis
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            info["synopsis"] = og_desc["content"].strip()
        else:
            p_desc = soup.select_one(".line-clamp-3, .line-clamp-4, p.text-sm")
            if p_desc:
                info["synopsis"] = p_desc.get_text(strip=True)

        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        chapters = []
        norm_url = self._normalize_url(url)
        base_url = "https://hivetoons.org"

        # Match links to chapters: /series/<slug>/chapter-<num>
        seen_urls = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or "/chapter" not in href:
                continue

            full_url = urljoin(base_url, href).split("#")[0].split("?")[0]
            if full_url in seen_urls:
                continue

            # Check if this chapter is paywalled / coin-locked
            # Paywalled chapters contain an SVG with lock path or icon inside the link element
            is_locked = False
            for s in a.find_all("svg"):
                if "M12 1.5" in str(s) or "lock" in str(s).lower():
                    is_locked = True
                    break

            ch_num = self.extract_chapter_number(full_url)
            txt = a.get_text(" ", strip=True)
            clean_title = re.sub(r'\s+', ' ', txt).strip()
            if not clean_title or len(clean_title) > 80:
                clean_title = f"Chapter {ch_num:g}"

            if is_locked:
                clean_title = f"{clean_title} [Locked - Coins Required]"

            seen_urls.add(full_url)
            chapters.append({
                "chapter_num": ch_num,
                "title": clean_title,
                "url": full_url,
                "is_locked": is_locked
            })

        if chapters:
            chapters.sort(key=lambda x: x["chapter_num"])
            return chapters

        return super().extract_chapter_list(soup, norm_url, html)

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        # 1. Detect if chapter is paywalled / coin-locked
        # If locked, there are 0 real panels; returning anything would result in downloading 1-2 random covers/avatars
        text_content = soup.get_text() if soup else html
        if "Cost to Unlock" in text_content or "Sign in to unlock this" in text_content:
            return []

        # 2. Extract genuine comic panels
        panels = []
        if soup:
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if not src or not src.startswith("http"):
                    continue

                lower_src = src.lower()
                # Strictly filter out thumbnails, covers, settings, avatars, and promo banners
                if any(b in lower_src for b in [
                    "/featured/", "/settings/", "/logo", "kakaoentcdn.com",
                    "pstatic.net", "icon", "avatar", "discord", "patreon"
                ]):
                    continue

                # Ensure it is a valid panel from storage.hivetoon.com or upload/series
                if "storage.hivetoon.com" in lower_src or "/upload/series/" in lower_src:
                    panels.append(src)

        # 3. Fallback regex in HTML for storage.hivetoon.com panel links
        if not panels and html:
            matches = re.findall(
                r'https?://storage\.hivetoon\.com/public/upload/series/[^/\"\'\s<>]+/[^/\"\'\s<>]+/[^/\"\'\s<>]+\.(?:webp|jpg|jpeg|png)',
                html, re.I
            )
            for m in matches:
                if "/featured/" not in m and "/settings/" not in m and m not in panels:
                    panels.append(m)

        # Guarantee no logo or banner is mistaken for a panel
        clean = [self.clean_image_url(u, "https://hivetoons.org") for u in panels]
        clean = [u for u in clean if u and "/featured/" not in u and "/settings/" not in u]
        return self.deduplicate_urls(clean)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        base_url = "https://hivetoons.org"
        for a in soup.find_all("a", href=True):
            txt = a.get_text(strip=True).lower()
            if "next" in txt and "/chapter" in a["href"]:
                return urljoin(base_url, a["href"])
        return None
