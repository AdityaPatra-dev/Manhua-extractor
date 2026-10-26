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
            title = re.sub(r'(?:[-—|:]\s*)?(?:chapter|episode|ep|ch|vol|volume|#)\s*[\d\.\-]+.*', '', title, flags=re.I).strip(' -:|—')
            title = re.sub(r'\s+[\d\.\-]+(?:\s*raw|\s*end)?$', '', title, flags=re.I).strip(' -:|—')
            title = re.sub(r'^read\s+', '', title, flags=re.I).strip()
            title = re.sub(r'\s+[-—|]\s+.*$', '', title, flags=re.I).strip()
        if not title:
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()
                title = re.sub(r'(?:[-—|:]\s*)?(?:chapter|episode|ep|ch|vol|volume|#)\s*[\d\.\-]+.*', '', title, flags=re.I).strip(' -:|—')
                title = re.sub(r'\s+[\d\.\-]+(?:\s*raw|\s*end)?$', '', title, flags=re.I).strip(' -:|—')
                title = re.sub(r'^read\s+', '', title, flags=re.I).strip()
                title = re.sub(r'\s+[-—|]\s+.*$', '', title, flags=re.I).strip()
        if not title:
            title = slug.replace('-', ' ').title()
            title = re.sub(r'(?:[-—|:]\s*)?(?:chapter|episode|ep|ch|vol|volume|#)\s*[\d\.\-]+.*', '', title, flags=re.I).strip(' -:|—')
            title = re.sub(r'\s+[\d\.\-]+(?:\s*raw|\s*end)?$', '', title, flags=re.I).strip(' -:|—')

        # Strip chapter numbering suffix from slug (e.g. island-of-stars-and-chains-1 -> island-of-stars-and-chains)
        slug = re.sub(r'[-_](?:chapter|episode|ch|ep|vol|volume)?[-_.]?\d+(?:\.\d+)?$', '', slug, flags=re.I)
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
                elements = soup.select(sel)
                for c_elem in elements:
                    # Ignore images in sidebars, widgets, related mangas, or footers
                    parent_str = " ".join([
                        str(p.get("class", [])) + " " + str(p.get("id", ""))
                        for p in c_elem.parents if hasattr(p, "get")
                    ]).lower()
                    if any(bad in parent_str for bad in ["sidebar", "widget", "related", "recommend", "recent", "popular", "footer", "author", "user", "comment"]):
                        continue

                    # If the image has an alt/title, check that it doesn't clearly name a different series
                    alt_val = (c_elem.get("alt") or c_elem.get("title") or "").strip().lower()
                    if title and alt_val and len(alt_val) > 3:
                        t_clean = re.sub(r'[^a-z0-9]+', ' ', title.lower()).strip()
                        # If alt has words but 0 overlap with series title, skip
                        t_words = set(t_clean.split()) - {"the", "a", "an", "and", "of", "in", "to"}
                        alt_words = set(re.sub(r'[^a-z0-9]+', ' ', alt_val).split()) - {"the", "a", "an", "and", "of", "in", "to"}
                        if t_words and alt_words and not (t_words & alt_words):
                            continue

                    src = c_elem.get("data-src") or c_elem.get("data-lazy-src") or c_elem.get("src")
                    if src and isinstance(src, str) and src.strip().startswith("http"):
                        cand = src.strip()
                        if not any(bad in cand.lower() for bad in ["logo", "avatar", "icon", "banner", "placeholder", "discord"]):
                            cover_url = cand
                            break
                if cover_url:
                    break

        if title:
            if "_" in title and " " not in title:
                title = title.replace('_', ' ').strip()
        else:
            title = slug.replace('_', ' ').replace('-', ' ').title()

        return {
            "title": title,
            "slug": slug,
            "cover_url": cover_url
        }

    def extract_chapter_number(self, url: str, title: Optional[str] = None) -> float:
        """Parse chapter number from title or URL, supporting decimals (e.g. 10.5, 10-5)."""
        # If title contains explicit chapter/episode numbering, prefer it (avoids internal database IDs in URLs)
        m = None
        if title:
            # Strip trailing dates and reader pagination first so page numbers (e.g. "- Page 1", "Sep 01,2021") are not picked up as chapters
            clean_title = re.sub(r'[-—|:]\s*(?:read\b.*|online\b.*|page\s*\d+.*)', '', title, flags=re.I).strip()
            clean_title = re.sub(r'\bpage\s*\d+\b.*', '', clean_title, flags=re.I).strip()
            clean_title = re.sub(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\.?\s*\d{1,2},?\s*\d{2,4}', '', clean_title, flags=re.I).strip()
            clean_title = re.sub(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', '', clean_title).strip()
            clean_title = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', '', clean_title).strip()

            # Word-boundary check for chapter/episode/ch/c (avoid matching 'ep' in 'Sep')
            m = re.search(r'\b(?:chapter|episode|ep|ch)\.?\s*[:#-]?\s*(\d+(?:[\.-]\d+)?)', clean_title, re.I)
            if not m:
                m = re.search(r'\b(?:c)\.?\s*[:#-]?\s*(\d+(?:[\.-]\d+)?)', clean_title, re.I)
            if not m:
                m = re.search(r'#\s*(\d+(?:[\.-]\d+)?)', clean_title)
            if not m:
                # Whole title is just a number or starts/ends with clear chapter number
                m = re.search(r'^(?:chapter|episode|ep|ch)?\s*(\d+(?:[\.-]\d+)?)$', clean_title.strip(), re.I)
            if not m:
                m = re.search(r'[-_:\s](\d+(?:[\.-]\d+)?)\s*$', clean_title.strip())

        # Look in URL if title did not yield a valid chapter number
        clean_url = (url or "").split('?')[0].rstrip('/')
        path_last = clean_url.split('/')[-1] if clean_url else ""

        if not m:
            m = re.search(r'\b(?:chapter|episode|ep|ch)[-_/](\d+(?:[\.-]\d+)?)', clean_url, re.I)
        if not m:
            m = re.search(r'[-_/]c(?:h|hapter)?[-/.]?(\d+(?:[\.-]\d+)?)', clean_url, re.I)
        if not m:
            m = re.search(r'[-_](\d+(?:[\.-]\d+)?)$', path_last)
        if not m:
            m = re.search(r'/(\d+(?:[\.-]\d+)?)$', clean_url)
        if not m:
            # Guard against extracting numbers from series slugs (e.g. 66666 from "the-dark-magician...-66666-years")
            if not any(w in path_last.lower() for w in ("manga", "manhua", "manhwa", "transmigrates", "years", "comic", "series")):
                m = re.search(r'(\d+(?:[\.-]\d+)?)', path_last)

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
            "dflazy", "loading", "blank", "placeholder", "thumbnail", "win-cross", "cross", "detail-btn", "downlist", "emotion-form",
            "wetried_only", "avatar", "favicon"
        ]):
            return None

        # Filter Next.js tiny UI thumbnails/icons
        if re.search(r'[?&]w=(?:16|32|48|64|96|128)\b', lower):
            return None

        # Filter avatar if it appears in filename (e.g. user-avatar.jpg), not if in series directory path
        if re.search(r'[-_.]avatar[-_.]|^avatar[-_.]', filename):
            return None

        # Filter actual ad directory patterns and static web UI themes
        if any(bad in lower for bad in [
            "/ads/", "/ad/", "-ads-", "_ads_", "/advertisement/", "loading.gif", "blank.gif", "dflazy.jpg",
            "/themes/", "/wp-content/themes/", "about_", "to_be_continued", "static.fanfox.net", "static.mangahere",
            "/avatars/", "/users/avatars/"
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
            if re.search(r'order|sort|filter|direction|report|issue|error|feedback|modal', f"{classes} {sel_id} {sel_name}", re.I):
                continue
            if re.search(r'chapter|navi|select|reader', f"{classes} {sel_id} {sel_name}", re.I):
                for opt in sel.find_all("option"):
                    val = opt.get("value") or opt.get("data-redirect") or opt.get("data-url")
                    if not val or val.lower() in ("#", "0", "", "desc", "asc", "all", "order", "sort"):
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
            "ul.chapter-list li a",
            "ul.chapter-list a",
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

        def _extract_series_slug(path: str) -> str:
            m = re.search(r'/(?:manga|series|comic|comics|webtoon|read|reader)(?:/[a-z]{2}(?:-[a-z]{2})?)?(?:/\d+)?/([^/]+)', path, re.I)
            if m:
                s = m.group(1).lower()
                s = re.sub(r'-(?:chapter|ch|c)[-_/\d].*$', '', s, flags=re.I)
                if s not in ("manga", "series", "comic", "comics", "webtoon", "read", "reader", "ajax", "page", "chapter", "chapters", "en", "es", "fr", "raw") and not re.match(r'^\d+(?:-\d+)?$', s):
                    return s
            parts = [p.lower() for p in path.strip('/').split('/') if p]
            filtered = [p for p in parts if p not in ("manga", "series", "comic", "comics", "webtoon", "read", "reader", "ajax", "page", "chapter", "chapters", "en", "es", "fr", "raw") and not re.match(r'^\d+(?:-\d+)?$', p)]
            if filtered:
                return re.sub(r'-(?:chapter|ch|c)[-_/\d].*$', '', filtered[0], flags=re.I)
            return ""

        target_slug = _extract_series_slug(parsed.path) or (clean_series_path.split('/')[-1] if clean_series_path else "")
        target_slug = target_slug.lower()

        for a in link_candidates:
            # Skip links inside unrelated widget / recommendation / sidebar containers
            parent_classes = " ".join(a.find_parent().get("class", [])) if a.find_parent() else ""
            p_lower = parent_classes.lower()
            if any(bad in p_lower for bad in ("widget", "popular", "related", "footer", "comment")) and not any(ok in p_lower for ok in ("chapter", "reader", "episodes", "volume", "eplister", "clstyle", "chapter-list")):
                continue
            if "sidebar" in p_lower and not any(ok in p_lower for ok in ("chapter", "reader", "episodes", "drawer", "eplister", "clstyle")):
                continue

            anc_str = " ".join(" ".join(p.get("class", [])) + " " + p.get("id", "") for p in a.parents if hasattr(p, "get")).lower()
            if any(bad in anc_str for bad in ("sidebar-pp", "content-sidebar", "sidebar-panel", "popular", "related", "recommend")) and not any(ok in anc_str for ok in ("listing-chapters_content", "chapterlist", "chapter-list", "manga-chapters-holder", "bxcl", "clstyle", "eplister")):
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

            # Prioritize dedicated chapter name element to prevent date concatenation (e.g. Chapter 109 18 Oct 2026)
            name_el = a.select_one(".chapter-name, .chap-name, .chapternum, .name, .chapter-title, .title")
            if name_el:
                txt = name_el.get_text(separator=" ", strip=True)
            else:
                txt = a.get_text(separator=" ", strip=True)

            txt = re.sub(r'Last Read.*$', '', txt, flags=re.I).strip()
            # Clean trailing relative time like "2 days ago" or view counts
            txt_clean = re.sub(r'\s*\d+\s*(?:sec|second|min|minute|hour|hr|day|week|month|year)s?\s*(?:ago)?.*$', '', txt, flags=re.I).strip()
            txt_clean = re.sub(r'\s*\d+(?:\.\d+)?\s*(?:views?|reads?|comments?|[km])\b.*$', '', txt_clean, flags=re.I).strip()
            # Clean trailing dates like "June 9, 2026", "Sep 01,2021", or ISO dates from chapter title
            txt_clean = re.sub(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\b\.?\s*\d{1,2},?\s*\d{2,4}', '', txt_clean, flags=re.I).strip()
            txt_clean = re.sub(r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b', '', txt_clean).strip()
            txt_clean = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b', '', txt_clean).strip()
            if not txt_clean:
                txt_clean = txt

            # Filter out non-chapter auxiliary links (e.g. comment threads, subscriptions)
            if any(junk in txt.lower() for junk in ("follow-up comments", "notify me", "new replies", "leave a comment", "cancel reply")):
                continue

            has_ch_kw = bool(re.search(r'[-_](?:chapter|ch|c|ep|episode)[-_/\d]|/(?:chapters?|ch|c|ep|episodes?)[-_/\d]|[-_/]\d+/?$', href, re.I) or re.search(r'\b(?:chapter|episode|ep|ch|c)\.?\s*[:#-]?\s*\d+', txt, re.I))
            if not has_ch_kw and not a.find_parent(class_=re.compile(r'eplister|chapter[-_]?list|wp-manga-chapter|clstyle|bxcl|chapter-item', re.I)) and not a.find_parent(id=re.compile(r'chapter[-_]?list|eplister|chapters', re.I)):
                continue

            full_url = urljoin(url, href)
            parsed_href = urlparse(full_url)
            # If the link path is identical to the series URL path (e.g. #chapter-list or ?rev=1), skip
            if parsed_href.path.rstrip('/') == parsed.path.rstrip('/'):
                continue

            # Guard against candidate links belonging to a different manga series
            cand_slug = _extract_series_slug(parsed_href.path)
            if "full-chapter-list" in parsed.path.lower() or "ajax/chapters" in parsed.path.lower():
                cand_slug = target_slug
            if target_slug and cand_slug and target_slug not in ("manga", "series", "comic", "comics", "webtoon", "full-chapter-list"):
                clean_target = re.sub(r'-(?:raw|all|full|scan|scans|eng|english|chapter|chapters|\d+)$', '', target_slug)
                clean_cand = re.sub(r'-(?:raw|all|full|scan|scans|eng|english|chapter|chapters|\d+)$', '', cand_slug)
                if clean_cand != clean_target and clean_target not in cand_slug and cand_slug not in clean_target:
                    continue

            if target_slug and len(target_slug) > 3 and target_slug not in ("manga", "series", "comic", "comics", "webtoon"):
                clean_target = re.sub(r'-(?:raw|all|full|scan|scans|eng|english|chapter|chapters|\d+)$', '', target_slug)
                href_path = parsed_href.path.lower()
                m_direct = re.search(r'/([^/]+)-(?:chapter|ch|c)[-_/]\d+', href_path)
                if m_direct:
                    direct_slug = m_direct.group(1)
                    clean_direct = re.sub(r'-(?:raw|all|full|scan|scans|eng|english|\d+)$', '', direct_slug)
                    if clean_direct != clean_target and clean_target not in direct_slug and direct_slug not in clean_target:
                        continue

            if full_url in seen_urls or not full_url.startswith("http"):
                # If already seen, check if we can upgrade a generic title like 'Read Now' or 'Start Reading'
                if full_url in seen_urls and re.search(r'\b(?:chapter|episode|ep|ch|c)\.?\s*[:#-]?\s*\d+', txt_clean, re.I):
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


