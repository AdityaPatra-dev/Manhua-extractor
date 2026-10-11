import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

class BaseExtractor(ABC):
    engine_id: str = "base"
    name: str = "Base Extractor"

    @abstractmethod
    def can_handle(self, soup: BeautifulSoup, url: str, html: str) -> bool:
        """Return True if this extractor can handle the given website/page."""
        pass

    @abstractmethod
    def extract_pages(self, soup: BeautifulSoup, url: str, html: str) -> List[str]:
        """Extract ordered list of panel image URLs."""
        pass

    @abstractmethod
    def extract_next_chapter(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """Extract next chapter URL if present on page."""
        pass

    def extract_series_info(self, soup: BeautifulSoup, url: str, html: str) -> Dict[str, Any]:
        """Extract series metadata (title, slug, cover_url). Default implementation uses heuristics."""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        raw_parts = [p for p in path.split('/') if p]

        category_prefixes = {'read', 'series', 'manga', 'manhua', 'manhwa', 'comic', 'comics', 'webtoon', 'webtoons', 'book', 'title'}
        candidates = []
        for p in raw_parts:
            clean_p = re.sub(r'\.html?$', '', p, flags=re.I)
            clean_p = re.sub(r'[-_]?(?:ch(?:apter)?|ep(?:isode)?)[-_.]?\d+.*$', '', clean_p, flags=re.I)
            if clean_p and not re.match(r'^\d+$', clean_p) and clean_p.lower() not in category_prefixes:
                candidates.append(clean_p)

        slug = candidates[-1] if candidates else "unknown-series"

        # Heuristic title from <title> or h1
        title = None
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
            title = re.sub(r'chapter\s*[\d\.\-]+.*', '', title, flags=re.I).strip(' -:|—')
            title = re.sub(r'^read\s+', '', title, flags=re.I).strip()
            title = re.sub(r'\s+[-—|]\s+.*$', '', title, flags=re.I).strip()
        if not title:
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()
                title = re.sub(r'chapter\s*[\d\.\-]+.*', '', title, flags=re.I).strip(' -:|—')
                title = re.sub(r'^read\s+', '', title, flags=re.I).strip()
                title = re.sub(r'\s+[-—|]\s+.*$', '', title, flags=re.I).strip()
        if not title:
            title = slug.replace('-', ' ').title()

        if (slug == "unknown-series" or re.search(r'^(?:ch(?:apter)?|ep(?:isode)?)[-_.]?\d+|^\d+(?:\.\d+)?$', slug, re.I)) and title and title.lower() != "unknown series":
            slug = re.sub(r'[^a-zA-Z0-9_-]', '-', title.lower()).strip('-')

        cover_url = None
        # 1. Meta image tags
        for meta_attr, prop_val in [
            ("property", "og:image"),
            ("name", "twitter:image"),
            ("itemprop", "image"),
            ("name", "thumbnail")
        ]:
            meta_tag = soup.find('meta', attrs={meta_attr: prop_val})
            if meta_tag and meta_tag.get('content') and meta_tag['content'].strip().startswith('http'):
                cand = meta_tag['content'].strip()
                if not any(bad in cand.lower() for bad in ["logo", "avatar", "icon", "banner", "discord"]):
                    cover_url = cand
                    break

        # 2. Prominent DOM cover selectors if meta tag is missing or generic
        if not cover_url:
            dom_cover_selectors = [
                "div.summary_image img",
                "div.thumb img",
                "div.series-thumb img",
                "div.manga-poster img",
                "div.poster img",
                "img.wp-post-image",
                "div.comic-info img",
                "div.anime-cover img",
                "div.series-cover img",
                "div.book-info img",
                ".seriestucon img",
                ".imgdesc img",
                "div.img-desc img",
                "div.detail-info img",
                "img[itemprop='image']"
            ]
            for sel in dom_cover_selectors:
                c_elem = soup.select_one(sel)
                if c_elem:
                    src = c_elem.get("data-src") or c_elem.get("data-lazy-src") or c_elem.get("src")
                    if src and isinstance(src, str) and src.strip().startswith("http"):
                        cand = src.strip()
                        if not any(bad in cand.lower() for bad in ["logo", "avatar", "icon", "banner", "placeholder"]):
                            cover_url = cand
                            break

        return {
            "title": title or slug.replace('-', ' ').title(),
            "slug": slug,
            "cover_url": cover_url
        }

    def extract_chapter_number(self, url: str, title: Optional[str] = None) -> float:
        """Parse chapter number from URL or title, supporting decimals (e.g. 10.5, 10-5)."""
        # Look in URL first
        m = re.search(r'chapter[-/](\d+(?:[\.-]\d+)?)', url, re.I)
        if not m:
            m = re.search(r'/c(?:h|hapter)?[-/]?(\d+(?:[\.-]\d+)?)', url, re.I)
        if not m and title:
            m = re.search(r'chapter\s*(\d+(?:[\.-]\d+)?)', title, re.I)
        if not m:
            m = re.search(r'(\d+(?:[\.-]\d+)?)', url.split('/')[-1])

        if m:
            raw_num = m.group(1).replace('-', '.')
            try:
                return float(raw_num)
            except ValueError:
                pass
        return 1.0

    @staticmethod
    def clean_image_url(url: str, base_url: str) -> Optional[str]:
        """Normalize URL and filter out banners, logos, and placeholders."""
        if not url:
            return None
        url = url.strip()
        if not url or url.startswith("data:image"):
            return None
        if url.startswith("//"):
            url = f"https:{url}"
        elif url.startswith("/"):
            url = urljoin(base_url, url)

        lower = url.lower()
        filename = lower.split("?")[0].split("/")[-1]

        # Filter branding icons, loaders, and placeholders from filename
        if any(bad in filename for bad in [
            "logo", "icon", "banner", "loader", "discord", "patreon",
            "dflazy", "loading", "blank", "placeholder"
        ]):
            return None

        # Filter avatar if it appears in filename (e.g. user-avatar.jpg), not if in series directory path
        if re.search(r'[-_.]avatar[-_.]|^avatar[-_.]', filename):
            return None

        # Filter actual ad directory patterns (avoiding 'uploads' or 'downloads')
        if any(bad in lower for bad in [
            "/ads/", "/ad/", "-ads-", "_ads_", "/advertisement/", "loading.gif", "blank.gif", "dflazy.jpg"
        ]):
            return None

        if not lower.startswith("http"):
            return None
        return url

    @staticmethod
    def deduplicate_urls(urls: List[str]) -> List[str]:
        """Deduplicate image URLs while strictly preserving natural order."""
        seen = set()
        clean = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                clean.append(u)
        return clean

    def extract_chapter_list(self, soup: BeautifulSoup, url: str, html: str) -> List[Dict[str, Any]]:
        """
        Extract complete catalog of chapters from series or reader page.
        Returns list of dicts: [{"chapter_num": float, "title": str, "url": str}]
        """
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        chapters: List[Dict[str, Any]] = []
        seen_urls = set()

        # 1. Check <select> elements (common on reader pages)
        for sel in soup.find_all("select"):
            classes = " ".join(sel.get("class", []))
            sel_id = sel.get("id", "")
            if re.search(r'chapter|navi|select|reader', f"{classes} {sel_id}", re.I):
                for opt in sel.find_all("option"):
                    val = opt.get("value") or opt.get("data-redirect") or opt.get("data-url")
                    if not val or val in ("#", "0", ""):
                        continue
                    full_url = urljoin(url, val)
                    if full_url in seen_urls or not full_url.startswith("http"):
                        continue
                    title = opt.get_text(strip=True)
                    ch_num = self.extract_chapter_number(full_url, title)
                    seen_urls.add(full_url)
                    chapters.append({
                        "chapter_num": ch_num,
                        "title": title or f"Chapter {ch_num:g}",
                        "url": full_url
                    })

        # 2. Check <a> links (common on series pages & reader sidebars)
        selectors = [
            "li.wp-manga-chapter a",
            "div.eplister a",
            "#chapterlist a",
            "ul.row-content-chapter a",
            "div.chapter-list a",
            "ul.version-chap a",
            "a[href*='/chapter-']",
            "a[href*='/chapter/']",
            "a[href*='/c-']"
        ]
        link_candidates = []
        for selector in selectors:
            found = soup.select(selector)
            if found:
                link_candidates.extend(found)

        # Fallback to broad link search if specific selectors matched nothing
        clean_series_path = re.sub(r'/(?:chapter|ch|c|ajax)[-_/\d].*$', '', parsed.path, flags=re.I).strip('/')

        for a in link_candidates:
            # Skip links inside unrelated widget / recommendation containers
            parent_classes = " ".join(a.find_parent().get("class", [])) if a.find_parent() else ""
            p_lower = parent_classes.lower()
            if any(bad in p_lower for bad in ("widget", "popular", "related", "footer", "comment")) and not any(ok in p_lower for ok in ("chapter", "reader", "episodes", "volume")):
                continue
            if "sidebar" in p_lower and not any(ok in p_lower for ok in ("chapter", "reader", "episodes", "drawer")):
                continue

            href = a.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue
            # Must look like a chapter URL or contain chapter text
            txt = a.get_text(strip=True)
            if not (re.search(r'/(?:chapter|ch|c)[-_/\d]', href, re.I) or re.search(r'chapter\s*\d+', txt, re.I)):
                continue

            full_url = urljoin(url, href)
            if full_url in seen_urls or not full_url.startswith("http"):
                continue

            parsed_href = urlparse(full_url)
            if clean_series_path and len(clean_series_path.split('/')) > 1 and parsed_href.netloc == parsed.netloc:
                href_path = parsed_href.path.strip('/')
                # If the link belongs to a different series path on the same site, skip it
                if not href_path.startswith(clean_series_path):
                    continue

            ch_num = self.extract_chapter_number(full_url, txt)
            seen_urls.add(full_url)
            chapters.append({
                "chapter_num": ch_num,
                "title": txt or f"Chapter {ch_num:g}",
                "url": full_url
            })

        # Sort chapters logically in ascending order
        chapters.sort(key=lambda x: x["chapter_num"])
        return chapters


