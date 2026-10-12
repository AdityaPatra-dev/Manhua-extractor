import re
import time
import asyncio
import urllib.parse
from typing import List, Dict, Any, Optional, AsyncIterator
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
    {"key": "mangadex", "name": "MangaDex", "type": "api_mangadex"},
    {"key": "comick", "name": "ComicK", "type": "api_comick"},
    {"key": "asura", "name": "Asura Scans", "type": "astro", "domain": "asuracomic.net"},
    {"key": "flame", "name": "Flame Comics", "type": "nextjs", "domain": "flamecomics.me"},
    {"key": "manganato", "name": "Manganato", "type": "manganato", "domain": "manganato.com"},
    {"key": "toonily", "name": "Toonily", "type": "madara", "domain": "toonily.com"},
]

TIER_2_MADARA = [
    {"key": "kunmanga", "name": "KunManga", "type": "madara", "domain": "kunmanga.com"},
    {"key": "mangatx", "name": "MangaTX", "type": "madara", "domain": "mangatx.to"},
    {"key": "topmanhua", "name": "TopManhua", "type": "madara", "domain": "topmanhua.com"},
    {"key": "manhuaus", "name": "ManhuaUS", "type": "madara", "domain": "manhuaus.com"},
    {"key": "westmanga", "name": "WestManga", "type": "madara", "domain": "westmanga.info"},
    {"key": "zinmanga", "name": "ZinManga", "type": "madara", "domain": "zinmanga.com"},
    {"key": "hiperdex", "name": "Hiperdex", "type": "madara", "domain": "hiperdex.com"},
]

TIER_3_MANGASTREAM = [
    {"key": "manhuaplus", "name": "ManhuaPlus", "type": "mangastream", "domain": "manhuaplus.org"},
    {"key": "reaper", "name": "Reaper Scans", "type": "mangastream", "domain": "reaperscans.com"},
    {"key": "drake", "name": "Drake Scans", "type": "mangastream", "domain": "drakescans.com"},
    {"key": "surya", "name": "Surya Scans", "type": "mangastream", "domain": "suryascans.com"},
    {"key": "omega", "name": "Omega Scans", "type": "mangastream", "domain": "omegascans.org"},
]

TIER_4_AGGREGATOR = [
    {"key": "mangapill", "name": "MangaPill", "type": "mangapill", "domain": "mangapill.com"},
    {"key": "mangafox", "name": "MangaFox", "type": "mangafox", "domain": "fanfox.net"},
    {"key": "mangafreak", "name": "MangaFreak", "type": "mangafreak", "domain": "mangafreak.net"},
]


class SearchDispatcher:
    def __init__(self, concurrency_limit: int = 12, timeout_seconds: float = 4.0):
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.timeout = timeout_seconds

    def get_sources_for_tier(self, tier: str = "fast") -> List[Dict[str, Any]]:
        if tier == "fast":
            return TIER_1_SOURCES
        elif tier == "popular":
            return TIER_1_SOURCES + TIER_2_MADARA
        elif tier == "all":
            return TIER_1_SOURCES + TIER_2_MADARA + TIER_3_MANGASTREAM + TIER_4_AGGREGATOR
        return TIER_1_SOURCES

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
        url = f"https://api.comick.fun/v1.0/search?q={urllib.parse.quote(query)}&t=false"
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
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
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select(".c-tabs-item__content, .row.c-tabs-item__content")
                results = []
                for it in items[:5]:
                    title_el = it.select_one(".post-title a, h3 a")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    series_url = title_el.get("href") or ""
                    
                    img_el = it.select_one(".tab-thumb img")
                    cover_url = ""
                    if img_el:
                        cover_url = img_el.get("data-src") or img_el.get("src") or ""

                    ch_el = it.select_one(".font-meta.chapter a, .chapter-item a")
                    ch_title = ch_el.get_text(strip=True) if ch_el else "Chapter 1"
                    ch_num_match = re.search(r"chapter\s*([\d\.]+)", ch_title, re.IGNORECASE)
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
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                latency = int((time.time() - t0) * 1000)
                soup = BeautifulSoup(html, "html.parser")
                items = soup.select(".bsx, .film_list-wrap .flw-item")
                results = []
                for it in items[:5]:
                    link_el = it.select_one("a[title], a[href*='/manga/'], a[href*='/series/']")
                    if not link_el:
                        continue
                    title = link_el.get("title") or link_el.get_text(strip=True)
                    series_url = link_el.get("href") or ""
                    
                    img_el = it.select_one("img")
                    cover_url = ""
                    if img_el:
                        cover_url = img_el.get("data-src") or img_el.get("src") or ""

                    ep_el = it.select_one(".epxs, .chapter-badge")
                    ch_title = ep_el.get_text(strip=True) if ep_el else "Chapter 1"
                    ch_num_match = re.search(r"([\d\.]+)", ch_title)
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

    # --- Dispatcher Worker for Single Source ---
    async def _query_single_source(self, source: Dict[str, Any], query: str, session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
        async with self.semaphore:
            stype = source.get("type")
            if stype == "api_mangadex":
                return await self.search_mangadex(query, session)
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
        async with aiohttp.ClientSession() as session:
            tasks = [self._query_single_source(s, query, session) for s in sources]
            results_nested = await asyncio.gather(*tasks, return_exceptions=True)

        all_hits = []
        for r in results_nested:
            if isinstance(r, list):
                all_hits.extend(r)

        return cluster_search_results(all_hits)

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

        async with aiohttp.ClientSession() as session:
            # Launch tasks as completed
            coros = [self._query_single_source(s, query, session) for s in sources]
            for future in asyncio.as_completed(coros):
                try:
                    hits = await future
                    completed += 1
                    if hits:
                        all_hits.extend(hits)
                        # Re-cluster and stream the latest state
                        clustered = cluster_search_results(all_hits)
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

        final_clusters = cluster_search_results(all_hits)
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

