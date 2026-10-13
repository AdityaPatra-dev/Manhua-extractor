from __future__ import annotations

import re
import time
import asyncio
import urllib.parse
from typing import List, Dict, Any, Optional, AsyncIterator, Tuple
from bs4 import BeautifulSoup
import aiohttp

from core.search.clustering import cluster_search_results, normalize_title

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Key curated platforms for search tiers
TIER_1_SOURCES = [
    # Top Scanlators & Custom Engines
    {"key": "asura", "name": "Asura Scans", "type": "asura"},
    {"key": "arenascan", "name": "Arena Scans", "type": "mangastream", "domain": "arenascan.com"},
    {"key": "flamecomics", "name": "Flame Comics", "type": "flamecomics"},
    {"key": "vortexscans", "name": "Vortex Scans", "type": "vortexscans"},
    {"key": "roliascan", "name": "Rolia Scan", "type": "roliascan"},
    {"key": "manhuaplus", "name": "ManhuaPlus", "type": "mangastream", "domain": "manhuaplus.org"},
    {"key": "ravenscans", "name": "Raven Scans", "type": "mangastream", "domain": "ravenscans.com"},
    {"key": "omegascans", "name": "Omega Scans", "type": "mangastream", "domain": "omegascans.org"},
    {"key": "rizzcomics", "name": "Rizz Comics", "type": "mangastream", "domain": "rizzfables.com"},
    {"key": "reaper", "name": "Reaper Scans", "type": "mangastream", "domain": "reapercomics.com"},

    # WP Madara Network
    {"key": "topmanhua", "name": "TopManhua", "type": "madara", "domain": "topmanhua.net"},
    {"key": "manhuatop", "name": "ManhuaTop", "type": "madara", "domain": "manhuatop.org"},
    {"key": "mangaread", "name": "MangaRead", "type": "madara", "domain": "www.mangaread.org"},
    {"key": "mangaeffect", "name": "MangaEffect", "type": "madara", "domain": "mangaeffect.com"},
    {"key": "manhwaden", "name": "ManhwaDen", "type": "madara", "domain": "manhwaden.com"},
    {"key": "manhwanex", "name": "ManhwaNex", "type": "madara", "domain": "manhwanex.com"},

    # Curated High-Speed Aggregators
    {"key": "mangadex", "name": "MangaDex", "type": "api_mangadex"},
    {"key": "comick", "name": "ComicK", "type": "api_comick"},
    {"key": "weebcentral", "name": "WeebCentral", "type": "weebcentral"},
    {"key": "mangapill", "name": "MangaPill", "type": "mangapill"},
    {"key": "mangakatana", "name": "MangaKatana", "type": "mangakatana"},
    {"key": "mangafox", "name": "MangaFox", "type": "mangafox"},
    {"key": "mangahub", "name": "MangaHub", "type": "mangahub"},
    {"key": "mangahere", "name": "MangaHere", "type": "mangahere"},
    {"key": "mangatown", "name": "MangaTown", "type": "mangatown"},
]

TIER_2_MADARA = [
    {"key": "kunmanga", "name": "KunManga", "type": "madara", "domain": "kunmanga.com"},
    {"key": "manhuaus", "name": "ManhuaUS", "type": "madara", "domain": "manhuaus.com"},
    {"key": "mangatx", "name": "MangaTX", "type": "madara", "domain": "mangatx.to"},
    {"key": "zinmanga", "name": "ZinManga", "type": "madara", "domain": "zinmanga.com"},
    {"key": "hiperdex", "name": "Hiperdex", "type": "madara", "domain": "hiperdex.com"},
]

TIER_3_MANGASTREAM = []

TIER_4_AGGREGATOR = [
    {"key": "manganato", "name": "Manganato", "type": "manganato", "domain": "manganato.com"},
]


class SearchDispatcher:
    def __init__(self, concurrency_limit: int = 15, timeout_seconds: float = 4.0):
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.timeout = timeout_seconds

    def get_sources_for_tier(self, tier: str = "fast") -> List[Dict[str, Any]]:
        if tier == "fast":
            return TIER_1_SOURCES
        elif tier in ("popular", "top"):
            return TIER_1_SOURCES + TIER_2_MADARA
        elif tier == "all":
            return TIER_1_SOURCES + TIER_2_MADARA + TIER_3_MANGASTREAM + TIER_4_AGGREGATOR
        return TIER_1_SOURCES

    async def fetch_html_with_clearance(
        self,
        url: str,
        domain: str,
        session: aiohttp.ClientSession,
        custom_headers: Optional[Dict[str, str]] = None
    ) -> Tuple[int, str]:
        """Fetch URL with cached clearance cookies and fall back to Android WebView resolver if blocked."""
        headers = (custom_headers or DEFAULT_HEADERS).copy()
        headers["Referer"] = f"https://{domain}/"

        # Check database for cached clearance cookie
        try:
            from database.db import get_clearance_cookie
            cached_cf = get_clearance_cookie(domain)
            if cached_cf:
                headers["Cookie"] = cached_cf["cookie_string"]
                if cached_cf.get("user_agent"):
                    headers["User-Agent"] = cached_cf["user_agent"]
        except Exception:
            pass

        text = ""
        is_challenge = False
        try:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                text = await resp.text()
                is_challenge = resp.status in (403, 503) or any(
                    m in text.lower() for m in ("just a moment", "challenges.cloudflare.com", "cf-turnstile", "__cf_chl_opt")
                )
                if resp.status == 200 and not is_challenge:
                    return resp.status, text
        except Exception:
            is_challenge = True

        # If blocked and on Android, solve using native Android WebView resolver
        if is_challenge:
            try:
                from extractors.browser_sidecar import solve_with_android_webview
                loop = asyncio.get_event_loop()
                android_sol = await loop.run_in_executor(None, solve_with_android_webview, url, 15)
                if android_sol and android_sol.get("success") and android_sol.get("text"):
                    return 200, android_sol["text"]
            except Exception:
                pass

        return 500, text

    # --- Engine Adapter 1: MangaDex REST API ---
    async def search_mangadex(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://api.mangadex.org/manga?title={urllib.parse.quote(query)}&limit=8&includes[]=cover_art"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                latency = int((time.time() - t0) * 1000)
                results = []
                for item in data.get("data", []):
                    attr = item.get("attributes", {})
                    title_dict = attr.get("title", {})
                    primary_title = title_dict.get("en") or next(iter(title_dict.values()), "Unknown")
                    
                    alt_titles = []
                    for alt in attr.get("altTitles", []):
                        alt_titles.extend(list(alt.values()))

                    # Find cover
                    cover_filename = None
                    for rel in item.get("relationships", []):
                        if rel.get("type") == "cover_art":
                            cover_filename = rel.get("attributes", {}).get("fileName")
                            break
                    cover_url = f"https://uploads.mangadex.org/covers/{item['id']}/{cover_filename}.256.jpg" if cover_filename else ""

                    last_ch = attr.get("lastChapter") or "1"
                    try:
                        last_ch_num = float(last_ch)
                    except ValueError:
                        last_ch_num = 1.0

                    results.append({
                        "title": primary_title,
                        "alt_titles": alt_titles[:5],
                        "source_key": "mangadex",
                        "source_name": "MangaDex",
                        "source_logo": "/docs/logos/mangadex.png",
                        "series_url": f"https://mangadex.org/title/{item['id']}",
                        "cover_url": cover_url,
                        "latest_chapter": f"Chapter {last_ch}",
                        "latest_chapter_num": last_ch_num,
                        "quality_tag": "Lossless PNG",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 2: ComicK REST API ---
    async def search_comick(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://api.comick.dev/v1.0/search?q={urllib.parse.quote(query)}&t=false"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                latency = int((time.time() - t0) * 1000)
                results = []
                for item in data if isinstance(data, list) else data.get("comics", []):
                    title = item.get("title") or "Unknown"
                    hid = item.get("hid") or item.get("slug")
                    cover_url = f"https://meo.comick.pictures/{item.get('b2key')}" if item.get("b2key") else ""
                    last_ch = item.get("last_chapter") or "1"
                    try:
                        last_ch_num = float(last_ch)
                    except ValueError:
                        last_ch_num = 1.0

                    alt_titles = item.get("md_titles", [])
                    if isinstance(alt_titles, list):
                        alt_list = [t.get("title") for t in alt_titles if isinstance(t, dict) and t.get("title")]
                    else:
                        alt_list = []

                    results.append({
                        "title": title,
                        "alt_titles": alt_list[:5],
                        "source_key": "comick",
                        "source_name": "ComicK",
                        "source_logo": "/docs/logos/comick.png",
                        "series_url": f"https://comick.io/comic/{hid}",
                        "cover_url": cover_url,
                        "latest_chapter": f"Chapter {last_ch}",
                        "latest_chapter_num": last_ch_num,
                        "quality_tag": "1080p WebP",
                        "latency_ms": latency
                    })
                return results[:6]
        except Exception:
            return []

    # --- Engine Adapter 3: Manganato ---
    async def search_manganato(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        query_slug = re.sub(r"[^a-zA-Z0-9]+", "_", query.strip().lower()).strip("_")
        url = f"https://manganato.com/search/story/{query_slug}"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select(".search-story-item, .story_item")
                results = []
                for it in items[:6]:
                    title_el = it.select_one(".item-title, h3 a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    series_url = title_el.get("href") or ""
                    
                    img_el = it.select_one("img")
                    cover_url = (img_el.get("src") or "") if img_el else ""

                    ch_el = it.select_one(".item-chapter, a.chapter-name")
                    ch_title = ch_el.get_text(strip=True) if ch_el else "Chapter 1"
                    ch_num_match = re.search(r"chapter\s*([\d\.]+)", ch_title, re.IGNORECASE)
                    ch_num = float(ch_num_match.group(1)) if ch_num_match else 1.0

                    results.append({
                        "title": title,
                        "alt_titles": [],
                        "source_key": "manganato",
                        "source_name": "Manganato",
                        "source_logo": "/docs/logos/manganato.png",
                        "series_url": series_url,
                        "cover_url": cover_url,
                        "latest_chapter": ch_title,
                        "latest_chapter_num": ch_num,
                        "quality_tag": "720p JPG",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 4: WordPress Madara ---
    async def search_madara(self, source_info: Dict[str, Any], query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        domain = source_info["domain"]
        url = f"https://{domain}/?s={urllib.parse.quote(query)}&post_type=wp-manga"
        try:
            status, html = await self.fetch_html_with_clearance(url, domain, session)
            if status != 200 or not html:
                return []
            latency = int((time.time() - t0) * 1000)
            soup = BeautifulSoup(html, "html.parser")
            items = soup.select(".c-tabs-item__content, .row.c-tabs-item__content")
            results = []
            for it in items[:6]:
                title_el = it.select_one(".post-title a, h3 a, h4 a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                series_url = title_el.get("href") or ""
                
                img_el = it.select_one(".tab-thumb img, img")
                cover_url = ""
                if img_el:
                    cover_url = img_el.get("data-src") or img_el.get("src") or ""

                ch_el = it.select_one(".font-meta.chapter a, .chapter-item a")
                ch_title = ch_el.get_text(strip=True) if ch_el else "Chapter 1"
                ch_num_match = re.search(r"chapter\s*([\d\.]+)", ch_title, re.IGNORECASE) or re.search(r"([\d\.]+)", ch_title)
                ch_num = float(ch_num_match.group(1)) if ch_num_match else 1.0

                results.append({
                    "title": title,
                    "alt_titles": [],
                    "source_key": source_info["key"],
                    "source_name": source_info["name"],
                    "source_logo": f"/docs/logos/{source_info['key']}.png",
                    "series_url": series_url,
                    "cover_url": cover_url,
                    "latest_chapter": ch_title,
                    "latest_chapter_num": ch_num,
                    "quality_tag": "1080p WebP",
                    "latency_ms": latency
                })
            return results
        except Exception:
            return []

    # --- Engine Adapter 5: MangaStream / Themesia ---
    async def search_mangastream(self, source_info: Dict[str, Any], query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        domain = source_info["domain"]
        url = f"https://{domain}/?s={urllib.parse.quote(query)}"
        try:
            status, html = await self.fetch_html_with_clearance(url, domain, session)
            if status != 200 or not html:
                return []
            latency = int((time.time() - t0) * 1000)
            soup = BeautifulSoup(html, "html.parser")
            results = []
            seen_series = set()
            for it in items[:12]:
                link_el = it.select_one("a[title], a[href*='/manga/'], a[href*='/series/']")
                if not link_el:
                    continue
                raw_href = link_el.get("href") or ""
                series_url = re.sub(r'/chapter[-/].*$', '', raw_href, flags=re.I)
                if not series_url or series_url in seen_series:
                    continue
                seen_series.add(series_url)

                t_el = it.select_one(".tt, h2, h3, h4, .post-title, .title")
                title = (t_el.get_text(strip=True) if t_el else None) or link_el.get("title") or link_el.get_text(strip=True)
                if not title or len(title.strip()) == 0:
                    title = series_url.rstrip("/").split("/")[-1].replace("-", " ").title()

                img_el = it.select_one("img")
                cover_url = ""
                if img_el:
                    cover_url = img_el.get("data-src") or img_el.get("src") or ""

                ep_el = it.select_one(".epxs, .chapter-badge, a[href*='chapter']")
                ch_title = ep_el.get_text(strip=True) if ep_el else "Available"
                ch_num_match = re.search(r"chapter\s*([\d\.]+)", ch_title, re.I) or re.search(r"([\d\.]+)", ch_title)
                ch_num = float(ch_num_match.group(1)) if ch_num_match else 1.0

                results.append({
                    "title": title.strip(),
                    "alt_titles": [],
                    "source_key": source_info["key"],
                    "source_name": source_info["name"],
                    "source_logo": f"/docs/logos/{source_info['key']}.png",
                    "series_url": series_url,
                    "cover_url": cover_url,
                    "latest_chapter": ch_title,
                    "latest_chapter_num": ch_num,
                    "quality_tag": "1080p WebP",
                    "latency_ms": latency
                })
                if len(results) >= 8:
                    break
            return results
        except Exception:
            return []

    # --- Engine Adapter 6: WeebCentral ---
    async def search_weebcentral(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://weebcentral.com/search/data?text={urllib.parse.quote(query)}"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for art in soup.find_all("article", class_=lambda c: c and "bg-base-300" in c)[:8]:
                    sec = art.find_all("section")
                    if len(sec) > 1:
                        t_el = sec[1].select_one("a[href*='/series/']")
                        if not t_el:
                            continue
                        title = t_el.get_text(strip=True)
                        series_url = t_el.get("href") or ""
                        img = art.select_one("img")
                        cover_url = (img.get("src") or "") if img else ""
                        results.append({
                            "title": title,
                            "alt_titles": [],
                            "source_key": "weebcentral",
                            "source_name": "WeebCentral",
                            "source_logo": "/docs/logos/weebcentral.png",
                            "series_url": series_url,
                            "cover_url": cover_url,
                            "latest_chapter": "Latest",
                            "latest_chapter_num": 1.0,
                            "quality_tag": "1080p WebP",
                            "latency_ms": latency
                        })
                return results
        except Exception:
            return []

    # --- Engine Adapter 7: MangaPill ---
    async def search_mangapill(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://mangapill.com/search?q={urllib.parse.quote(query)}"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for it in soup.select("div.flex.flex-col.justify-end a")[:8]:
                    t_el = it.select_one("div.font-black")
                    if not t_el:
                        continue
                    title = t_el.get_text(strip=True)
                    href = it.get("href") or ""
                    parent_box = it.parent.parent
                    img = parent_box.select_one("img") if parent_box else None
                    cover_url = (img.get("data-src") or img.get("src") or "") if img else ""

                    alt_el = it.select_one("div.text-secondary")
                    alt_titles = [alt_el.get_text(strip=True)] if alt_el and alt_el.get_text(strip=True) else []

                    results.append({
                        "title": title,
                        "alt_titles": alt_titles,
                        "source_key": "mangapill",
                        "source_name": "MangaPill",
                        "source_logo": "/docs/logos/mangapill.png",
                        "series_url": f"https://mangapill.com{href}" if href.startswith("/") else href,
                        "cover_url": cover_url,
                        "latest_chapter": "HQ Scans",
                        "latest_chapter_num": 1.0,
                        "quality_tag": "Lossless WebP",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 8: MangaKatana ---
    async def search_mangakatana(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://mangakatana.com/?search={urllib.parse.quote(query)}&search_by=book_name"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for item in soup.select("#book_list .item")[:8]:
                    t_el = item.select_one(".title a")
                    if not t_el:
                        continue
                    title = t_el.get_text(strip=True)
                    href = t_el.get("href") or ""
                    img = item.select_one("img")
                    cover_url = (img.get("src") or "") if img else ""
                    ch_el = item.select_one(".chapter a")
                    ch_str = ch_el.get_text(strip=True) if ch_el else "Ch. 1"
                    ch_num_match = re.search(r"chapter\s*([\d\.]+)", ch_str, re.IGNORECASE) or re.search(r"([\d\.]+)", ch_str)
                    ch_num = float(ch_num_match.group(1)) if ch_num_match else 1.0

                    results.append({
                        "title": title,
                        "alt_titles": [],
                        "source_key": "mangakatana",
                        "source_name": "MangaKatana",
                        "source_logo": "/docs/logos/mangakatana.png",
                        "series_url": href,
                        "cover_url": cover_url,
                        "latest_chapter": ch_str,
                        "latest_chapter_num": ch_num,
                        "quality_tag": "Direct Scans",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 9: MangaHere ---
    async def search_mangahere(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://www.mangahere.cc/search?title={urllib.parse.quote(query)}"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for item in soup.select(".manga-list-4-list li")[:8]:
                    t_el = item.select_one(".manga-list-4-item-title a")
                    if not t_el:
                        continue
                    title = t_el.get_text(strip=True)
                    href = t_el.get("href") or ""
                    if href and not href.startswith("http"):
                        href = f"https://www.mangahere.cc{href}"
                    img = item.select_one("img")
                    cover_url = (img.get("src") or "") if img else ""
                    ch_el = item.select_one(".manga-list-4-item-subtitle a")
                    ch_str = ch_el.get_text(strip=True) if ch_el else "Latest"
                    ch_num_match = re.search(r"([\d\.]+)", ch_str)
                    ch_num = float(ch_num_match.group(1)) if ch_num_match else 1.0

                    results.append({
                        "title": title,
                        "alt_titles": [],
                        "source_key": "mangahere",
                        "source_name": "MangaHere",
                        "source_logo": "/docs/logos/mangahere.png",
                        "series_url": href,
                        "cover_url": cover_url,
                        "latest_chapter": ch_str,
                        "latest_chapter_num": ch_num,
                        "quality_tag": "HQ WebP",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 10: MangaTown ---
    async def search_mangatown(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://www.mangatown.com/search?name={urllib.parse.quote(query)}"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for li in soup.select(".manga_pic_list li")[:8]:
                    t_el = li.select_one(".title a")
                    if not t_el:
                        continue
                    title = t_el.get_text(strip=True)
                    href = t_el.get("href") or ""
                    if href and not href.startswith("http"):
                        href = f"https://www.mangatown.com{href}"
                    img = li.select_one("img")
                    cover_url = (img.get("src") or "") if img else ""
                    ch_el = li.select_one(".view")
                    ch_str = ch_el.get_text(strip=True) if ch_el else "Available"
                    ch_num_match = re.search(r"([\d\.]+)", ch_str)
                    ch_num = float(ch_num_match.group(1)) if ch_num_match else 1.0

                    results.append({
                        "title": title,
                        "alt_titles": [],
                        "source_key": "mangatown",
                        "source_name": "MangaTown",
                        "source_logo": "/docs/logos/mangatown.png",
                        "series_url": href,
                        "cover_url": cover_url,
                        "latest_chapter": ch_str,
                        "latest_chapter_num": ch_num,
                        "quality_tag": "Standard",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 11: Asura Scans REST API ---
    async def search_asura(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://api.asurascans.com/api/series?search={urllib.parse.quote(query)}"
        headers = {
            **DEFAULT_HEADERS,
            "Origin": "https://asurascans.com",
            "Referer": "https://asurascans.com/",
        }
        try:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                latency = int((time.time() - t0) * 1000)
                items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                results = []
                for item in items[:8]:
                    title = item.get("title") or "Unknown"
                    slug = item.get("slug") or ""
                    public_url = item.get("public_url") or ""
                    series_url = f"https://asurascans.com{public_url}" if public_url else f"https://asurascans.com/series/{slug}"
                    cover_url = item.get("cover") or item.get("banner") or ""

                    # Accurate chapter tracking
                    ch_num = 1.0
                    ch_count = item.get("chapter_count")
                    latest_chapters = item.get("latest_chapters") or []
                    if latest_chapters and isinstance(latest_chapters, list) and "number" in latest_chapters[0]:
                        try:
                            ch_num = float(latest_chapters[0]["number"])
                        except (ValueError, TypeError):
                            ch_num = 1.0
                    elif ch_count:
                        try:
                            ch_num = float(ch_count)
                        except (ValueError, TypeError):
                            ch_num = 1.0

                    alt_titles = item.get("alt_titles") or []
                    if not isinstance(alt_titles, list):
                        alt_titles = []

                    results.append({
                        "title": title,
                        "alt_titles": [a for a in alt_titles if a and isinstance(a, str)][:5],
                        "source_key": "asura",
                        "source_name": "Asura Scans",
                        "source_logo": "/docs/logos/asura.png",
                        "series_url": series_url,
                        "cover_url": cover_url,
                        "latest_chapter": f"Chapter {int(ch_num) if ch_num.is_integer() else ch_num:g}",
                        "latest_chapter_num": ch_num,
                        "quality_tag": "Original Scan",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 12: Rolia Scan ---
    async def search_roliascan(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://roliascan.com/?s={urllib.parse.quote(query)}"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                cards = soup.select("a[href*='/manga/']")
                seen_urls = set()
                for a in cards:
                    href = a.get("href") or ""
                    if not href or href in seen_urls or "/manga/" not in href:
                        continue
                    seen_urls.add(href)

                    img = a.select_one("img")
                    title = ""
                    if img and img.get("alt"):
                        title = img.get("alt").strip()

                    parent_card = a.parent.parent if a.parent else None
                    if not title and parent_card:
                        h3 = parent_card.select_one("h3")
                        if h3:
                            title = h3.get_text(strip=True)

                    if not title:
                        title = href.rstrip("/").split("/")[-1].replace("-", " ").title()

                    cover_url = ""
                    if img:
                        cover_url = img.get("data-src") or img.get("src") or ""

                    results.append({
                        "title": title,
                        "alt_titles": [],
                        "source_key": "roliascan",
                        "source_name": "Rolia Scan",
                        "source_logo": "/docs/logos/roliascan.png",
                        "series_url": href,
                        "cover_url": cover_url,
                        "latest_chapter": "Available",
                        "latest_chapter_num": 0.0,
                        "quality_tag": "HQ WebP",
                        "latency_ms": latency
                    })
                    if len(results) >= 8:
                        break
                return results
        except Exception:
            return []

    # --- Engine Adapter 13: Flame Comics API ---
    async def search_flamecomics(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = "https://flamecomics.xyz/api/series"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                latency = int((time.time() - t0) * 1000)
                norm_q = normalize_title(query)
                q_words = norm_q.split()
                results = []
                for s in data:
                    label = s.get("label") or ""
                    norm_label = normalize_title(label)
                    # Check if query matches series label
                    if norm_q in norm_label or (len(q_words) >= 2 and all(w in norm_label.split() for w in q_words)) or (len(q_words) == 1 and q_words[0] in norm_label.split()):
                        sid = s.get("id")
                        ch_str = str(s.get("chapter_count") or "1")
                        try:
                            ch_num = float(ch_str)
                        except (ValueError, TypeError):
                            ch_num = 1.0
                        img = s.get("image") or ""
                        cover_url = f"https://cdn.flamecomics.xyz/uploads/images/series/{sid}/{img}" if img else ""
                        results.append({
                            "title": label,
                            "alt_titles": [],
                            "source_key": "flamecomics",
                            "source_name": "Flame Comics",
                            "source_logo": "/docs/logos/flamecomics.png",
                            "series_url": f"https://flamecomics.xyz/series/{sid}",
                            "cover_url": cover_url,
                            "latest_chapter": f"Chapter {int(ch_num) if ch_num.is_integer() else ch_num:g}",
                            "latest_chapter_num": ch_num,
                            "quality_tag": "Flame HQ",
                            "latency_ms": latency
                        })
                return results[:6]
        except Exception:
            return []

    # --- Engine Adapter 14: Vortex Scans (Astro Catalog) ---
    async def search_vortexscans(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = "https://vortexscans.org/series"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                norm_q = normalize_title(query)
                q_words = norm_q.split()
                results = []
                seen_slugs = set()
                for a in soup.select("a[href*='/series/']"):
                    href = a.get("href") or ""
                    if "/chapter-" in href:
                        continue
                    slug = href.strip("/").split("/")[-1]
                    if not slug or slug in seen_slugs:
                        continue

                    img = a.select_one("img")
                    title = (img.get("alt") if img else None) or a.get_text(strip=True) or slug.replace("-", " ").title()
                    norm_title = normalize_title(title)

                    # Match query
                    if norm_q in norm_title or (len(q_words) >= 2 and all(w in norm_title.split() for w in q_words)) or (len(q_words) == 1 and q_words[0] in norm_title.split()):
                        seen_slugs.add(slug)
                        cover_url = (img.get("src") or img.get("data-fallback-src") or "") if img else ""

                        # Find chapter
                        parent = a.parent
                        ch_el = parent.select_one("a[href*='chapter-']") if parent else None
                        ch_span = ch_el.select_one("span") if ch_el else None
                        ch_title = ch_span.get_text(strip=True) if ch_span else (ch_el.get_text(strip=True) if ch_el else "Available")
                        ch_match = re.search(r"chapter[-/\s]*([\d\.]+)", (ch_el.get("href") if ch_el else "") + " " + ch_title, re.I)
                        ch_num = float(ch_match.group(1)) if ch_match else 1.0

                        full_url = f"https://vortexscans.org{href}" if href.startswith("/") else href
                        results.append({
                            "title": title.strip(),
                            "alt_titles": [],
                            "source_key": "vortexscans",
                            "source_name": "Vortex Scans",
                            "source_logo": "/docs/logos/vortexscans.png",
                            "series_url": full_url,
                            "cover_url": cover_url,
                            "latest_chapter": ch_title,
                            "latest_chapter_num": ch_num,
                            "quality_tag": "Vortex HQ",
                            "latency_ms": latency
                        })
                return results[:6]
        except Exception:
            return []

    # --- Engine Adapter 15: MangaFox ---
    async def search_mangafox(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://fanfox.net/search?title={urllib.parse.quote(query)}"
        headers = {**DEFAULT_HEADERS, "Cookie": "isAdult=1"}
        try:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for it in soup.select(".manga-list-4-list li")[:8]:
                    t_el = it.select_one(".manga-list-4-item-title a")
                    if not t_el:
                        continue
                    title = t_el.get_text(strip=True)
                    href = t_el.get("href") or ""
                    if href and not href.startswith("http"):
                        href = f"https://fanfox.net{href}"
                    img = it.select_one("img")
                    cover_url = img.get("src") or "" if img else ""
                    results.append({
                        "title": title,
                        "alt_titles": [],
                        "source_key": "mangafox",
                        "source_name": "MangaFox",
                        "source_logo": "/docs/logos/mangafox.png",
                        "series_url": href,
                        "cover_url": cover_url,
                        "latest_chapter": "Available",
                        "latest_chapter_num": 1.0,
                        "quality_tag": "Standard",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Engine Adapter 16: MangaHub ---
    async def search_mangahub(self, query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        t0 = time.time()
        url = f"https://mangahub.io/search?q={urllib.parse.quote(query)}"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, ssl=False, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for m in soup.select(".media-manga")[:8]:
                    t_el = m.select_one(".media-heading a")
                    if not t_el:
                        continue
                    title = t_el.get_text(strip=True)
                    href = t_el.get("href") or ""
                    img = m.select_one("img")
                    cover_url = img.get("src") or "" if img else ""
                    results.append({
                        "title": title,
                        "alt_titles": [],
                        "source_key": "mangahub",
                        "source_name": "MangaHub",
                        "source_logo": "/docs/logos/mangahub.png",
                        "series_url": href,
                        "cover_url": cover_url,
                        "latest_chapter": "Available",
                        "latest_chapter_num": 1.0,
                        "quality_tag": "Standard",
                        "latency_ms": latency
                    })
                return results
        except Exception:
            return []

    # --- Dispatcher Worker for Single Source ---
    async def _query_single_source(self, source: Dict[str, Any], query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        async with self.semaphore:
            stype = source.get("type")
            if stype == "asura":
                return await self.search_asura(query, session)
            elif stype == "roliascan":
                return await self.search_roliascan(query, session)
            elif stype == "flamecomics":
                return await self.search_flamecomics(query, session)
            elif stype == "vortexscans":
                return await self.search_vortexscans(query, session)
            elif stype == "api_mangadex":
                return await self.search_mangadex(query, session)
            elif stype == "weebcentral":
                return await self.search_weebcentral(query, session)
            elif stype == "mangapill":
                return await self.search_mangapill(query, session)
            elif stype == "mangakatana":
                return await self.search_mangakatana(query, session)
            elif stype == "mangafox":
                return await self.search_mangafox(query, session)
            elif stype == "mangahub":
                return await self.search_mangahub(query, session)
            elif stype == "mangahere":
                return await self.search_mangahere(query, session)
            elif stype == "mangatown":
                return await self.search_mangatown(query, session)
            elif stype == "api_comick":
                return await self.search_comick(query, session)
            elif stype == "manganato":
                return await self.search_manganato(query, session)
            elif stype == "madara":
                return await self.search_madara(source, query, session)
            elif stype in ("mangastream", "astro", "nextjs"):
                return await self.search_mangastream(source, query, session)
            return []

    # --- Unified Search across all sources in tier ---
    async def search_all(self, query: str, tier: str = "fast") -> List[Dict[str, Any]]:
        sources = self.get_sources_for_tier(tier)
        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            tasks = [self._query_single_source(s, query, session) for s in sources]
            results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        all_hits = []
        for r in results_nested:
            if isinstance(r, list):
                all_hits.extend(r)

        return cluster_search_results(all_hits, query=query)

    # --- Real-Time SSE Search Generator ---
    async def search_stream(self, query: str, tier: str = "fast") -> AsyncIterator[Dict[str, Any]]:
        sources = self.get_sources_for_tier(tier)
        total_sources = len(sources)
        yield {
            "event": "init",
            "data": {
                "total_sources": total_sources,
                "query": query,
                "tier": tier
            }
        }

        all_hits: List[Dict[str, Any]] = []
        completed = 0

        conn = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            # Launch tasks as completed
            coros = [self._query_single_source(s, query, session) for s in sources]
            for future in asyncio.as_completed(coros):
                try:
                    hits = await future
                    completed += 1
                    if hits:
                        all_hits.extend(hits)
                        # Re-cluster and stream the latest state
                        clustered = cluster_search_results(all_hits, query=query)
                        yield {
                            "event": "update",
                            "data": {
                                "completed": completed,
                                "total": total_sources,
                                "new_hits_count": len(hits),
                                "total_clusters": len(clustered),
                                "clusters": clustered
                            }
                        }
                    else:
                        yield {
                            "event": "progress",
                            "data": {
                                "completed": completed,
                                "total": total_sources
                            }
                        }
                except Exception:
                    completed += 1

        final_clusters = cluster_search_results(all_hits, query=query)
        yield {
            "event": "complete",
            "data": {
                "total_sources": total_sources,
                "total_clusters": len(final_clusters),
                "clusters": final_clusters
            }
        }


# Global search dispatcher instance
search_dispatcher = SearchDispatcher()

