import re
import json
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from extractors.base import BaseExtractor


class Manhwa18Extractor(BaseExtractor):
    """
    Dedicated Extractor for Manhwa18 (manhwa18.net).
    Manhwa18 uses Laravel with Inertia.js frontend rendering state into <div id="app" data-page="...">.
    """

    def __init__(self):
        super().__init__()
        self.engine_id = "manhwa18"
        self.name = "Manhwa18"

    def can_handle(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> bool:
        domain = urlparse(url).netloc.lower()
        return "manhwa18.net" in domain

    def _extract_page_data(self, soup: BeautifulSoup, html: Optional[str]) -> Optional[Dict[str, Any]]:
        app_el = soup.find("div", attrs={"data-page": True})
        if app_el and app_el.get("data-page"):
            try:
                return json.loads(app_el["data-page"])
            except Exception:
                pass
        if html:
            m = re.search(r'data-page="([^"]+)"', html)
            if m:
                try:
                    import html as html_lib
                    decoded = html_lib.unescape(m.group(1))
                    return json.loads(decoded)
                except Exception:
                    pass
        return None

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> Dict[str, Any]:
        data = self._extract_page_data(soup, html)
        if data and isinstance(data.get("props"), dict):
            props = data["props"]
            manga = props.get("manga") or {}
            if manga:
                title = manga.get("name") or "Manhwa18 Series"
                slug = manga.get("slug") or "series"
                cover = manga.get("cover_url")
                synopsis = manga.get("pilot") or ""
                if synopsis and "<" in synopsis:
                    syn_soup = BeautifulSoup(synopsis, "html.parser")
                    synopsis = syn_soup.get_text(strip=True)
                return {
                    "title": title,
                    "slug": slug,
                    "cover_url": cover,
                    "synopsis": synopsis
                }
            # If on chapter page
            if "mangaName" in props:
                return {
                    "title": props.get("mangaName"),
                    "slug": props.get("mangaSlug") or "series",
                    "cover_url": props.get("mangaCover"),
                    "synopsis": ""
                }

        # Fallback to standard DOM
        title = ""
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        elif soup.title:
            title = soup.title.get_text(strip=True)
        return {
            "title": title or "Manhwa18 Series",
            "slug": "manhwa18-series",
            "cover_url": None,
            "synopsis": ""
        }

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> List[Dict[str, Any]]:
        data = self._extract_page_data(soup, html)
        if data and isinstance(data.get("props"), dict):
            props = data["props"]
            manga = props.get("manga") or {}
            slug = manga.get("slug") or props.get("mangaSlug")
            raw_chaps = props.get("chapters") or manga.get("chapters") or props.get("listChapters") or []
            chapters = []
            for ch in raw_chaps:
                ch_name = ch.get("name") or "Chapter"
                ch_slug = ch.get("slug")
                ch_num = ch.get("order")
                if ch_num is None:
                    ch_num = self.extract_chapter_number(ch_slug or "", ch_name)
                else:
                    try:
                        ch_num = float(ch_num)
                    except Exception:
                        ch_num = 0.0
                if ch_slug and slug:
                    ch_url = f"https://manhwa18.net/manga/{slug}/{ch_slug}"
                elif ch.get("url"):
                    ch_url = ch["url"]
                else:
                    continue
                chapters.append({
                    "chapter_num": ch_num,
                    "title": ch_name,
                    "url": ch_url
                })
            if chapters:
                chapters.sort(key=lambda x: x["chapter_num"])
                return chapters

        # Fallback to links in DOM
        chapters = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r'/manga/[^/]+/chapter-\d+', href):
                ch_title = a.get_text(strip=True) or "Chapter"
                chapters.append({
                    "chapter_num": self.extract_chapter_number(href, ch_title),
                    "title": ch_title,
                    "url": href if href.startswith("http") else f"https://manhwa18.net{href}"
                })
        chapters.sort(key=lambda x: x["chapter_num"])
        return chapters

    def extract_pages(self, soup: BeautifulSoup, url: str, html: Optional[str] = None) -> List[str]:
        data = self._extract_page_data(soup, html)
        if data and isinstance(data.get("props"), dict):
            props = data["props"]
            # 1. chapterImages array of objects: [{'src': '...'}]
            ch_imgs = props.get("chapterImages", [])
            raw_urls = []
            for item in ch_imgs:
                if isinstance(item, dict) and "src" in item:
                    raw_urls.append(item["src"])
                elif isinstance(item, str):
                    raw_urls.append(item)

            # 2. chapterContent HTML: '<img src="..." />'
            if not raw_urls and props.get("chapterContent"):
                c_soup = BeautifulSoup(props["chapterContent"], "html.parser")
                for img in c_soup.find_all("img"):
                    src = img.get("src")
                    if src:
                        raw_urls.append(src)

            if raw_urls:
                clean_urls = [self.clean_image_url(u, "https://manhwa18.net/") for u in raw_urls if u]
                return self.deduplicate_urls([u for u in clean_urls if u])

        # Fallback to DOM images
        images = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            clean = self.clean_image_url(src, "https://manhwa18.net/")
            if clean and "chapter" in clean.lower() or "manhwa18" in clean.lower():
                images.append(clean)
        return self.deduplicate_urls(images)

    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        data = self._extract_page_data(soup, None)
        if data and isinstance(data.get("props"), dict):
            next_url = data["props"].get("nextChapterUrl")
            if next_url:
                return next_url if next_url.startswith("http") else f"https://manhwa18.net{next_url}"
        m = re.search(r'/chapter-(\d+)', current_url)
        if m:
            next_num = int(m.group(1)) + 1
            return re.sub(r'/chapter-\d+', f'/chapter-{next_num}', current_url)
        return None

