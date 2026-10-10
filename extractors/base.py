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
        parts = [p for p in path.split('/') if p and not re.search(r'chapter|ch-|\.html$', p, re.I)]
        slug = parts[-1] if parts else "unknown-series"

        # Heuristic title from <title> or h1
        title = None
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text(strip=True)
            # Remove chapter mentions from title
            title = re.sub(r'(?i)chapter\s*[\d\.\-]+.*', '', title).strip(' -:|')
        if not title:
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()
                title = re.sub(r'(?i)chapter\s*[\d\.\-]+.*', '', title).strip(' -:|')
        if not title:
            title = slug.replace('-', ' ').title()

        cover_url = None
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            cover_url = og_image['content'].strip()

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
        # Filter obvious advertisement / icon assets
        forbidden = [
            "logo", "avatar", "banner", "loader", "icon", "discord",
            "patreon", "dflazy.jpg", "loading.gif", "blank.gif", "placeholder",
            "footer", "ads", "advertisement"
        ]
        if any(bad in lower for bad in forbidden):
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

