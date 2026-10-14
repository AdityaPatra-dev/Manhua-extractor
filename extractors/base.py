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
        """Parse chapter number from title or URL, supporting decimals (e.g. 10.5, 10-5)."""
        # If title contains explicit chapter/episode numbering, prefer it (avoids internal database IDs in URLs)
        m = None
        if title:
            m = re.search(r'(?:chapter|episode|ep|ch)\s*(\d+(?:[\.-]\d+)?)', title, re.I)
            if not m:
                m = re.search(r'#\s*(\d+(?:[\.-]\d+)?)', title)

        # Look in URL if title did not yield a valid chapter number
        if not m:
            m = re.search(r'chapter[-/](\d+(?:[\.-]\d+)?)', url, re.I)
        if not m:
            m = re.search(r'/c(?:h|hapter)?[-/]?(\d+(?:[\.-]\d+)?)', url, re.I)
        if not m:
            m = re.search(r'(\d+(?:[\.-]\d+)?)', url.split('/')[-1])

        if m:
            raw_num = m.group(1).replace('-', '.')
            try:
                val = float(raw_num)
                # If URL gave an unrealistically huge ID (> 10000) while title exists, fallback to title digits
                if val > 10000 and title:
                    tm = re.search(r'(\d+(?:[\.-]\d+)?)', title)
                    if tm:
                        return float(tm.group(1).replace('-', '.'))
                return val
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
            "dflazy", "loading", "blank", "placeholder", "thumbnail", "win-cross", "cross", "detail-btn", "downlist", "emotion-form"
        ]):
            return None

        # Filter avatar if it appears in filename (e.g. user-avatar.jpg), not if in series directory path
        if re.search(r'[-_.]avatar[-_.]|^avatar[-_.]', filename):
            return None

        # Filter actual ad directory patterns and static web UI themes
        if any(bad in lower for bad in [
            "/ads/", "/ad/", "-ads-", "_ads_", "/advertisement/", "loading.gif", "blank.gif", "dflazy.jpg",
            "/themes/", "/wp-content/themes/", "about_", "to_be_continued", "static.fanfox.net", "static.mangahere"
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
            sel_name = sel.get("name", "")
            if re.search(r'report|issue|error|feedback|modal', f"{classes} {sel_id} {sel_name}", re.I):
                continue
            if re.search(r'chapter|navi|select|reader', f"{classes} {sel_id} {sel_name}", re.I):
                for opt in sel.find_all("option"):
                    val = opt.get("value") or opt.get("data-redirect") or opt.get("data-url")
                    if not val or val in ("#", "0", ""):
                        continue
                    title = opt.get_text(strip=True)
                    if any(bad in title.lower() for bad in ("load images", "image position", "duplicate chapter", "not translated", "wrong chapter", "other error")):
                        continue
                    full_url = urljoin(url, val)
                    if full_url in seen_urls or not full_url.startswith("http"):
                        continue
                    ch_num = self.extract_chapter_number(full_url, title)
                    seen_urls.add(full_url)
                    chapters.append({
                        "chapter_num": ch_num,
                        "title": title or f"Chapter {ch_num:g}",
                        "url": full_url
                    })

        # 2. Check <a> links (common on series pages & reader sidebars)
        selectors = [
            "li.chapter-list-item a",
            "li.chapter-item a",
            "li.wp-manga-chapter a",
            "div.eplister a",
            "#chapterlist a",
            "ul.clstyle a",
            "div.bxcl a",
            "li[data-num] a",
            "ul.row-content-chapter a",
            "div.chapter-list a",
            "#chapter-list a",
            "ul.version-chap a",
            ".chapters a",
            "a[href*='/chapters/']",
            "a[href*='chapter-']",
            "a[href*='/chapter/']",
            "a[href*='/c-']"
        ]
        link_candidates = []
        for selector in selectors:
            found = soup.select(selector)
            if found:
                link_candidates.extend(found)

        # Fallback to broad link search if specific selectors matched nothing
        clean_series_path = re.sub(r'/(?:chapters?|ch|c|ajax)[-_/\d].*$', '', parsed.path, flags=re.I).strip('/')
        if not link_candidates and clean_series_path:
            link_candidates = soup.select(f"a[href^='/{clean_series_path}/'], a[href*='/{clean_series_path}/']")

        for a in link_candidates:
            # Skip links inside unrelated widget / recommendation containers
            parent_classes = " ".join(a.find_parent().get("class", [])) if a.find_parent() else ""
            p_lower = parent_classes.lower()
            if any(bad in p_lower for bad in ("widget", "popular", "related", "footer", "comment")) and not any(ok in p_lower for ok in ("chapter", "reader", "episodes", "volume", "eplister", "clstyle", "chapter-list")):
                continue
            if "sidebar" in p_lower and not any(ok in p_lower for ok in ("chapter", "reader", "episodes", "drawer", "eplister", "clstyle")):
                continue

            href = a.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # Skip comment and reply anchor links, and pagination / reverse sort controls
            if any(bad in href.lower() for bad in ("#respond", "replytocom", "comment-", "#comments", "/page/", "?rev=", "&rev=")):
                continue

            # Skip social share links
            if any(s in href.lower() for s in (
                "facebook.com", "twitter.com", "://x.com", ".x.com/", "/x.com/", "t.me/", "telegram.me/",
                "whatsapp.com", "pinterest.com", "reddit.com", "tumblr.com",
                "linkedin.com", "addtoany", "sharer.php"
            )):
                continue

            # Must look like a chapter URL or contain chapter text
            txt = a.get_text(separator=" ", strip=True)
            txt = re.sub(r'Last Read.*$', '', txt, flags=re.I).strip()
            # Clean trailing relative time like "2 days ago" or view counts
            txt_clean = re.sub(r'\s*\d+\s*(?:sec|second|min|minute|hour|hr|day|week|month|year)s?\s*(?:ago)?.*$', '', txt, flags=re.I).strip()
            txt_clean = re.sub(r'\s*\d+(?:\.\d+)?\s*(?:views?|reads?|comments?|[km])\b.*$', '', txt_clean, flags=re.I).strip()
            # Clean trailing dates like "June 9, 2026" or "August 27, 2025" from chapter title
            txt_clean = re.sub(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}', '', txt_clean, flags=re.I).strip()
            if not txt_clean:
                txt_clean = txt

            has_ch_kw = bool(re.search(r'[-_](?:chapter|ch|c|ep|episode)[-_/\d]|/(?:chapters?|ch|c|ep|episodes?)[-_/\d]|[-_/]\d+/?$', href, re.I) or re.search(r'(?:chapter|episode|ep|ch)\s*\d+', txt, re.I))
            if not has_ch_kw and not a.find_parent(class_=re.compile(r'eplister|chapter[-_]?list|wp-manga-chapter|clstyle|bxcl|chapter-item', re.I)) and not a.find_parent(id=re.compile(r'chapter[-_]?list|eplister|chapters', re.I)):
                continue

            full_url = urljoin(url, href)
            parsed_href = urlparse(full_url)
            # If the link path is identical to the series URL path (e.g. #chapter-list or ?rev=1), skip
            if parsed_href.path.rstrip('/') == parsed.path.rstrip('/'):
                continue

            if full_url in seen_urls or not full_url.startswith("http"):
                # If already seen, check if we can upgrade a generic title like 'Read Now' or 'Start Reading'
                if full_url in seen_urls and re.search(r'(?:chapter|episode|ep|ch)\s*\d+', txt_clean, re.I):
                    for existing in chapters:
                        if existing["url"] == full_url:
                            if any(gen in existing["title"].lower() for gen in ("read now", "start reading", "read newest", "from start", "read")):
                                existing["title"] = txt_clean
                                existing["chapter_num"] = self.extract_chapter_number(full_url, txt_clean)
                            break
                continue
            # Only apply path prefix filter if href does not use a dedicated chapter route (/chapters/, /chapter-, etc.)
            is_in_ch_container = bool(
                a.find_parent(class_=re.compile(r'eplister|chapter[-_]?list|wp-manga-chapter|clstyle|bxcl|row-content-chapter|chapter-item', re.I)) or
                a.find_parent(id=re.compile(r'chapter[-_]?list|eplister|chapters', re.I))
            )
            is_dedicated_ch_route = is_in_ch_container or bool(re.search(r'[-_](?:chapter|ch|c)[-_/\d]|/(?:chapters?|ch|c)[-_/\d]|[-_/]\d+/?$', parsed_href.path, re.I))
            if not is_dedicated_ch_route and clean_series_path and len(clean_series_path.split('/')) > 1 and parsed_href.netloc == parsed.netloc:
                href_path = parsed_href.path.strip('/')
                # If the link belongs to a different series path on the same site, skip it
                if not href_path.startswith(clean_series_path):
                    continue

            # If not in an explicit chapter list container, ensure link belongs to the series
            series_slug = clean_series_path.split('/')[-1] if clean_series_path else ""
            if series_slug and series_slug not in ("manga", "series", "comic", "comics", "full-chapter-list") and not is_in_ch_container:
                slug_clean = re.sub(r'^[0-9A-Z]{20,30}[-_]?', '', series_slug).lower()
                path_parts = parsed_href.path.strip('/').split('/')
                # If path has multiple segments (e.g. /chapter/other-manga/...) and doesn't contain current series slug, skip it
                if len(path_parts) >= 2 and slug_clean not in parsed_href.path.lower() and not parsed_href.path.startswith(("/chapters/", "/chapter-")):
                    continue

            ch_num = self.extract_chapter_number(full_url, txt_clean)
            seen_urls.add(full_url)
            chapters.append({
                "chapter_num": ch_num,
                "title": txt_clean or f"Chapter {ch_num:g}",
                "url": full_url
            })

        # Sort chapters logically in ascending order
        chapters.sort(key=lambda x: x["chapter_num"])
        return chapters


