import re
import json
import html as html_lib
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from .base import BaseExtractor

class ModernSSRExtractor(BaseExtractor):
    engine_id: str = "modern_ssr"
    name: str = "Modern SSR / Astro / Next.js (Asura / Flame)"

    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        if "asurascans.com" in url or "asuracomic" in url or "asuratoons" in url:
            return True
        if "webdexscans.com" in url:
            return True
        if soup.find("astro-island") or "data-astro-cid" in html:
            return True
        if soup.find("script", id="__NEXT_DATA__") or "self.__next_f" in html or "/_next/static" in html:
            return True
        return False

    def _extract_astro_props(self, html: str) -> Optional[Dict[str, Any]]:
        """Extract and parse Astro island props JSON."""
        m = re.search(r'<astro-island[^>]+props=\"([^\"]+)\"', html)
        if m:
            try:
                decoded = html_lib.unescape(m.group(1))
                return json.loads(decoded)
            except Exception:
                pass
        return None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        info = super().extract_series_info(soup, url, html)
        props = self._extract_astro_props(html)
        if props:
            # Astro uses nested arrays like [0, 'Series Name']
            name_val = props.get("seriesName")
            if isinstance(name_val, list) and len(name_val) > 1:
                info["title"] = str(name_val[1])
            elif isinstance(name_val, str):
                info["title"] = name_val

            slug_val = props.get("seriesSlug")
            if isinstance(slug_val, list) and len(slug_val) > 1:
                info["slug"] = str(slug_val[1])
            elif isinstance(slug_val, str):
                info["slug"] = slug_val

            cover_val = props.get("seriesCover")
            if isinstance(cover_val, list) and len(cover_val) > 1:
                info["cover_url"] = str(cover_val[1])
            elif isinstance(cover_val, str):
                info["cover_url"] = cover_val

        # Next.js __NEXT_DATA__ series info
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                page_props = data.get("props", {}).get("pageProps", {})
                manga = page_props.get("initialManga") or page_props.get("manga") or {}
                if isinstance(manga, dict):
                    if manga.get("name"):
                        info["title"] = manga["name"]
                    if manga.get("slug"):
                        info["slug"] = manga["slug"]
                    m_cover = manga.get("cover") or manga.get("coverCensored") or manga.get("thumbnail")
                    if m_cover and isinstance(m_cover, str) and m_cover.startswith("http"):
                        info["cover_url"] = m_cover
            except Exception:
                pass

        return info

    def extract_chapter_list(self, soup: BeautifulSoup, url: str = "", html: str = "") -> List[Dict[str, Any]]:
        # 1. Check Next.js __NEXT_DATA__
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                page_props = data.get("props", {}).get("pageProps", {})
                manga = page_props.get("initialManga") or page_props.get("manga") or {}
                raw_chapters = None
                if isinstance(manga, dict):
                    raw_chapters = manga.get("chapters")
                if not raw_chapters:
                    raw_chapters = page_props.get("chapters") or page_props.get("initialChapters")

                if isinstance(raw_chapters, list) and raw_chapters:
                    chapters: List[Dict[str, Any]] = []
                    for ch in raw_chapters:
                        if not isinstance(ch, dict):
                            continue
                        ch_url = ch.get("url") or ch.get("slug")
                        if not ch_url:
                            continue
                        if not ch_url.startswith("http"):
                            ch_url = urljoin(url, ch_url)
                        ch_name = ch.get("name") or ch.get("title") or ""
                        ch_num_val = ch.get("number") or ch.get("chapter")
                        if ch_num_val is not None:
                            try:
                                ch_num = float(ch_num_val)
                            except Exception:
                                ch_num = self.extract_chapter_number(ch_url, ch_name)
                        else:
                            ch_num = self.extract_chapter_number(ch_url, ch_name)
                        if not ch_name:
                            ch_name = f"Chapter {ch_num:g}"
                        chapters.append({
                            "chapter_num": ch_num,
                            "title": ch_name,
                            "url": ch_url
                        })
                    if chapters:
                        chapters.sort(key=lambda x: x["chapter_num"])
                        return chapters
            except Exception:
                pass

        return super().extract_chapter_list(soup, url, html)

    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # 1. Asura Scans Astro island payload
        props = self._extract_astro_props(html)
        if props and "pages" in props:
            pages_data = props["pages"]
            urls = []

            def recurse_find_urls(obj):
                if isinstance(obj, dict):
                    if "url" in obj:
                        u = obj["url"]
                        if isinstance(u, list) and len(u) > 1:
                            urls.append(u[1])
                        elif isinstance(u, str):
                            urls.append(u)
                    for val in obj.values():
                        recurse_find_urls(val)
                elif isinstance(obj, list):
                    for item in obj:
                        recurse_find_urls(item)

            recurse_find_urls(pages_data)
            clean_urls = [self.clean_image_url(u, base_url) for u in urls if u]
            clean_urls = [u for u in clean_urls if u]
            if clean_urls:
                return self.deduplicate_urls(clean_urls)

        # 2. Next.js __NEXT_DATA__
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                page_props = data.get("props", {}).get("pageProps", {})
                urls = []

                def recurse_next_urls(obj):
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if k in ("images", "pages", "chapterImages") and isinstance(v, list):
                                for item in v:
                                    if isinstance(item, str):
                                        urls.append(item)
                                    elif isinstance(item, dict) and "url" in item:
                                        urls.append(item["url"])
                            else:
                                recurse_next_urls(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            recurse_next_urls(item)

                recurse_next_urls(page_props)
                clean_urls = [self.clean_image_url(u, base_url) for u in urls if u]
                clean_urls = [u for u in clean_urls if u]
                if clean_urls:
                    return self.deduplicate_urls(clean_urls)
            except Exception:
                pass

        # 3. Next.js App Router (self.__next_f chunks / JSON payloads)
        if "self.__next_f" in html or "/_next/static" in html or "webdexscans.com" in url:
            app_router_urls = re.findall(
                r'https?://[a-zA-Z0-9.\-_]+/(?:chapters|uploads|manga|comics)/[a-zA-Z0-9_\-\./]+?\.(?:webp|jpg|jpeg|png)',
                html,
                re.I
            )
            if app_router_urls:
                clean_urls = [self.clean_image_url(u, base_url) for u in app_router_urls]
                clean_urls = [u for u in clean_urls if u]
                if clean_urls:
                    return self.deduplicate_urls(clean_urls)

        # 4. Direct DOM images inside chapter viewer
        images = soup.find_all("img", attrs={"data-page-index": True})
        if not images:
            images = soup.select("div[data-page] img")
        if not images:
            images = soup.find_all("img", src=re.compile(r'/chapters?/|asura-images', re.I))
        if not images:
            images = soup.select(".chapter-content img, .reader-area img, .reading-content img, div[id*='reader'] img, div[class*='reader'] img, div[class*='chapter'] img, main img")
        if not images:
            images = soup.find_all("img", src=re.compile(r'/(?:chapters?|uploads|series|comics|manga)/', re.I))

        raw_urls = []
        for img in images:
            val = img.get("src") or img.get("data-src")
            clean = self.clean_image_url(val, base_url)
            if clean:
                raw_urls.append(clean)

        return self.deduplicate_urls(raw_urls)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        # 1. Check Astro nextChapter
        parsed = urlparse(current_url)
        m = re.search(r'/(comics|series)/([^/]+)/chapter([-_/])(\d+)', current_url, re.I)
        if m:
            prefix = m.group(1)
            series_slug = m.group(2)
            sep = m.group(3)
            current_num = int(m.group(4))
            next_num = current_num + 1
            return f"{parsed.scheme}://{parsed.netloc}/{prefix}/{series_slug}/chapter{sep}{next_num}"

        # 2. Check next button in DOM
        cand = soup.select_one("a[rel='next'], a:contains('Next')")
        if cand and cand.get("href"):
            href = cand["href"].strip()
            if href.startswith("http") and href != current_url:
                return href

        return None

