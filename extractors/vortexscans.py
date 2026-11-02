import re
import json
import html as html_lib
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from .base import BaseExtractor


class VortexScansExtractor(BaseExtractor):
    """
    Dedicated Extractor for Vortex Scans (vortexscans.org / vortextoon.com / vortexcomics.org).
    Features:
    - Normalizes legacy/mirrored domains (vortexcomics.org, vortextoon.com, vortexscans.io, vortexscans.com) to vortexscans.org.
    - Accurately extracts series metadata (title, cover, synopsis) and full chapter lists.
    - Detects paywalled/coin-locked chapters and avoids downloading random preview/cover images.
    - Extracts genuine comic panels from storage.vortexscans.org / Astro / Next / Iken reader payloads.
    - Strictly filters out promotional banners, thumbnails, cover previews, logos, and avatar images.
    """
    engine_id: str = "vortexscans"
    name: str = "Vortex Scans"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        lower_url = url.lower()
        if any(d in lower_url for d in (
            "vortexscans.org", "vortexscans.com", "vortexscans.io",
            "vortextoon.com", "vortexcomics.org"
        )):
            return True
        if "storage.vortexscans.org" in html or "vortexscans" in lower_url:
            return True
        return False

    def _normalize_url(self, url: str) -> str:
        for d in ("vortexcomics.org", "vortextoon.com", "vortexscans.io", "vortexscans.com"):
            if d in url:
                url = url.replace(d, "vortexscans.org")
        return url

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)

        # Title
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            raw_t = h1.get_text(strip=True)
            info["title"] = re.sub(r'\s*[-—|]\s*Vortex\s*Scans.*$', '', raw_t, flags=re.I).strip()
        else:
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                raw_t = og_title["content"].strip()
                info["title"] = re.sub(r'\s*[-—|]\s*Vortex\s*Scans.*$', '', raw_t, flags=re.I).strip()

        # Cover image
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            info["cover_url"] = og_img["content"]
        else:
            # Check featured/cover image in header
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if "/featured/" in src or "/series/" in src or "/covers/" in src:
                    info["cover_url"] = src
                    break

        # Synopsis
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            info["synopsis"] = og_desc["content"].strip()
        else:
            p_desc = soup.select_one(".line-clamp-3, .line-clamp-4, p.text-sm, .synopsis, .description")
            if p_desc:
                info["synopsis"] = p_desc.get_text(strip=True)

        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        chapters = []
        norm_url = self._normalize_url(url)
        base_url = "https://vortexscans.org"

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
            is_locked = False
            for s in a.find_all("svg"):
                if "M12 1.5" in str(s) or "lock" in str(s).lower():
                    is_locked = True
                    break
            if "locked" in a.get("class", []) or "lock" in str(a.get("class", [])):
                is_locked = True

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
        # If locked, there are 0 free comic panels; returning anything would result in downloading 1-2 random covers/avatars
        text_content = soup.get_text() if soup else html
        if "Cost to Unlock" in text_content or "Sign in to unlock this" in text_content:
            return []

        panels = []
        base_url = "https://vortexscans.org"

        # 2. Extract genuine comic panels from DOM
        if soup:
            for img in soup.find_all("img"):
                src = (
                    img.get("src") or
                    img.get("data-src") or
                    img.get("data-lazy-src") or
                    img.get("data-original") or
                    ""
                ).strip()
                if not src or src.startswith("data:"):
                    continue

                lower_src = src.lower()
                # Strictly filter out thumbnails, covers, settings, avatars, and promo banners
                if any(b in lower_src for b in [
                    "/featured/", "/settings/", "/logo", "/brand", "kakaoentcdn.com",
                    "pstatic.net", "icon", "avatar", "discord", "patreon", "banner",
                    "donation", "promo"
                ]):
                    continue

                # Ensure it is a valid panel from storage.vortexscans.org or upload/series or reader containers
                if (
                    "storage.vortexscans.org" in lower_src or
                    "storage.vortextoon.com" in lower_src or
                    "/upload/series/" in lower_src or
                    "/chapters/" in lower_src or
                    img.find_parent(class_=re.compile(r'reader|reading|chapter|comic-images|page', re.I))
                ):
                    panels.append(src)

        # 3. Fallback: Parse Astro props / Next.js / JSON script payloads
        if not panels and html:
            # Astro island props
            m_astro = re.search(r'<astro-island[^>]+props=\"([^\"]+)\"', html)
            if m_astro:
                try:
                    decoded = html_lib.unescape(m_astro.group(1))
                    data = json.loads(decoded)
                    def recurse_find_urls(obj):
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if k in ("url", "src", "path") and isinstance(v, str) and v.startswith("http"):
                                    panels.append(v)
                                elif isinstance(v, list) and len(v) > 1 and isinstance(v[1], str) and v[1].startswith("http"):
                                    panels.append(v[1])
                                else:
                                    recurse_find_urls(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                recurse_find_urls(item)
                    recurse_find_urls(data)
                except Exception:
                    pass

        # 4. Fallback regex in HTML for storage.vortexscans.org panel links
        if not panels and html:
            matches = re.findall(
                r'https?://(?:storage\.)?vortexscans\.org/(?:public/)?upload/series/[^/\"\'\s<>]+/[^/\"\'\s<>]+/[^/\"\'\s<>]+\.(?:webp|jpg|jpeg|png)',
                html, re.I
            )
            for m in matches:
                if "/featured/" not in m and "/settings/" not in m and m not in panels:
                    panels.append(m)

        # Filter and clean
        clean = []
        for u in panels:
            c = self.clean_image_url(u, base_url)
            if not c:
                continue
            lower_c = c.lower()
            if any(b in lower_c for b in ["/featured/", "/settings/", "/logo", "avatar", "discord", "banner"]):
                continue
            clean.append(c)

        result = self.deduplicate_urls(clean)

        # Safeguard: If only 1-2 images matched and they are suspiciously named cover/logo, return []
        if len(result) <= 2:
            all_suspicious = True
            for u in result:
                fname = u.split("?")[0].split("/")[-1].lower()
                if not any(bad in fname for bad in ["cover", "thumb", "logo", "header", "footer", "card"]):
                    all_suspicious = False
                    break
            if all_suspicious:
                return []

        return result

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        base_url = "https://vortexscans.org"
        if soup is not None:
            for a in soup.find_all("a", href=True):
                txt = a.get_text(strip=True).lower()
                if "next" in txt and "/chapter" in a["href"]:
                    return urljoin(base_url, a["href"])

        # Fallback URL increment
        m = re.search(r'((?:[-_/]|^)(?:chapter|ep|ch)[-_.]?)(\d+)', current_url, re.I)
        if m:
            prefix = m.group(1)
            num = int(m.group(2))
            clean = current_url.split('?')[0].rstrip('/')
            return clean[:m.start()] + f"{prefix}{num + 1}" + clean[m.end():]

        return None

