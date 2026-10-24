#!/usr/bin/env python3
"""
Daily Scraper Sentinel & Health Check Script (Resilient Multi-Pass Architecture)
Tests every registered manga/manhua source for:
  1. Global Search functionality (querying terms and returning valid series URLs)
  2. Direct Link Parsing (inspecting series page, resolving chapter list)
  3. Chapter Image Extraction (extracting panel image URLs)

Resilience Features:
  - Realistic desktop browser headers on ClientSession to avoid bot triggers.
  - Multi-query domain-aware fallback queries with jitter delay.
  - Homepage crawl fallback if search query returns 0 hits (prevents false positives on niche catalogs).
  - Two-pass verification: suspect sources are automatically cooled down and re-tested in an isolated, sequential pass.
  - Precise error classification (Cloudflare Turnstile vs Selector Mismatch vs Rate Limit vs Domain Outage).
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import random
import argparse
import asyncio
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple

# Ensure project root is in python path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import aiohttp
from core.search.dispatcher import (
    SearchDispatcher,
    TIER_1_SOURCES,
    TIER_2_MADARA,
    TIER_3_MANGASTREAM,
    TIER_4_AGGREGATOR,
    DEFAULT_HEADERS,
)
import extractors.dispatcher as extractor_dispatcher

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

KNOWN_DOMAINS = {
    "asura": "asuracomic.net",
    "arenascan": "arenascan.com",
    "flamecomics": "flamecomics.xyz",
    "vortexscans": "vortexscans.org",
    "roliascan": "roliascan.com",
    "manhuaplus": "manhuaplus.org",
    "rizzcomics": "rizzfables.com",
    "thunderscans": "en-thunderscans.com",
    "kingofshojo": "kingofshojo.com",
    "topmanhua": "topmanhua.net",
    "manhuatop": "manhuatop.org",
    "mangaread": "www.mangaread.org",
    "mangaeffect": "mangaeffect.com",
    "manhwaden": "manhwaden.com",
    "manhwanex": "manhwanex.com",
    "zinmanga": "www.zinmanga.net",
    "mangadex": "api.mangadex.org",
    "comick": "api.comick.dev",
    "weebcentral": "weebcentral.com",
    "mangapill": "mangapill.com",
    "mangakatana": "mangakatana.com",
    "mangafox": "fanfox.net",
    "mangahub": "mangahub.io",
    "mangahere": "mangahere.cc",
    "mangatown": "mangatown.com",
    "mgeko": "mgeko.cc",
    "mgread": "mangaread.io",
    "toongod": "toongod.cc",
    "hentai20": "hentai20.io",
    "manga18fx": "manga18fx.com",
    "manhwaclub": "manhwaclub.net",
    "allporncomics": "allporncomics.co",
    "comicland": "api.comicland.org",
    "manhwa18": "manhwa18.net",
    "toontop": "toontop.io",
    "mangadass": "mangadass.com",
    "manga18club": "manga18.club",
}


def get_source_domain(source: Dict[str, Any]) -> str:
    """Resolve primary target domain for any source entry."""
    if source.get("domain"):
        return source["domain"]
    key = source.get("key", "").lower()
    return KNOWN_DOMAINS.get(key, "")


def get_all_registered_sources() -> List[Dict[str, Any]]:
    """Aggregate all unique sources across all tiers."""
    all_tiers = [TIER_1_SOURCES, TIER_2_MADARA, TIER_3_MANGASTREAM, TIER_4_AGGREGATOR]
    seen_keys = set()
    sources = []
    for tier in all_tiers:
        for s in tier:
            key = s.get("key")
            if key and key not in seen_keys:
                seen_keys.add(key)
                sources.append(s)
    return sources


def get_search_queries_for_source(source: Dict[str, Any], default_query: str) -> List[str]:
    """Return tailored queries with fallback genres suitable for the source type."""
    stype = (source.get("type") or "").lower()
    key = (source.get("key") or "").lower()
    adult_markers = ("18", "hentai", "porn", "toongod", "manhwa18")
    is_adult = any(m in key or m in stype for m in adult_markers)

    queries = [default_query]
    if is_adult:
        fallbacks = ["secret", "love", "room", "teacher", "step"]
    else:
        fallbacks = ["magic", "secret", "return", "level", "system"]

    for fb in fallbacks:
        if fb not in queries:
            queries.append(fb)
    return queries


async def test_single_source(
    dispatcher: SearchDispatcher,
    source: Dict[str, Any],
    query: str,
    session: aiohttp.ClientSession,
    test_image_extraction: bool = True
) -> Dict[str, Any]:
    """
    Run an end-to-end compliance test on a single source:
    1. Global Search query
    2. Direct series inspection
    3. Chapter image extraction
    """
    key = source.get("key", "unknown")
    name = source.get("name", key)
    stype = source.get("type", "unknown")
    domain = get_source_domain(source)

    result: Dict[str, Any] = {
        "key": key,
        "name": name,
        "type": stype,
        "domain": domain,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "search_status": "SKIPPED",
        "search_error": None,
        "search_hits": 0,
        "sample_series_url": None,
        "direct_parse_status": "SKIPPED",
        "direct_parse_error": None,
        "chapters_found": 0,
        "sample_chapter_url": None,
        "image_extract_status": "SKIPPED",
        "image_extract_error": None,
        "panels_found": 0,
        "overall_status": "UNKNOWN",
        "non_compliance_reason": None,
        "failure_category": None,
    }

    t0 = time.time()

    # --- Phase 1: Global Search Test ---
    queries_to_try = get_search_queries_for_source(source, query)
    series_candidates: List[str] = []

    for idx, q_try in enumerate(queries_to_try):
        if idx > 0:
            # Jitter pacing between queries to avoid anti-bot rate-limit bursts
            await asyncio.sleep(0.5 + random.uniform(0.1, 0.4))
        try:
            cur_hits = await asyncio.wait_for(
                dispatcher._query_single_source(source, q_try, session),
                timeout=25.0
            )
            if cur_hits and isinstance(cur_hits, list):
                valid_hits = [
                    h for h in cur_hits
                    if (h.get("series_url") or h.get("url")) and h.get("title")
                ]
                for vh in valid_hits:
                    u = vh.get("series_url") or vh.get("url")
                    if u and u not in series_candidates:
                        series_candidates.append(u)
                if series_candidates:
                    result["search_status"] = "PASS"
                    result["search_hits"] = len(series_candidates)
                    result["sample_series_url"] = series_candidates[0]
                    break
        except asyncio.TimeoutError:
            result["search_error"] = "Search request timed out after 25s (Network latency or anti-bot hang)"
        except Exception as e:
            result["search_error"] = f"Search exception: {type(e).__name__} - {str(e)}"

    if not series_candidates:
        result["search_status"] = "FAIL"
        if not result["search_error"]:
            result["search_error"] = f"Search returned 0 results for queries {queries_to_try}"

    # Fallback series URL from domain homepage if search returned 0
    if not series_candidates and domain:
        try:
            home_code, home_html, _ = await asyncio.to_thread(extractor_dispatcher.fetch_page, f"https://{domain}")
            lower_html = (home_html or "").lower()
            if home_code in (403, 503) or any(m in lower_html for m in ("cf-turnstile", "challenges.cloudflare.com", "just a moment")):
                result["search_error"] = f"HTTP {home_code}: Site protected by interactive Cloudflare Turnstile challenge"
                result["failure_category"] = "BOT_CHALLENGE"
            elif home_html:
                series_matches = re.findall(
                    rf'href=[\"\'](https?://(?:www\.)?{re.escape(domain)}/(?:manga|series|comic|comics|webtoon|manhwa)/[^/\"\'#?]+/?)[^\"\']*[\"\']',
                    home_html, re.I
                )
                if not series_matches:
                    series_matches = re.findall(
                        r'href=[\"\'](/(?:manga|series|comic|comics|webtoon|manhwa)/[^/\"\'#?]+/?)[^\"\']*[\"\']',
                        home_html, re.I
                    )
                    series_matches = [urllib.parse.urljoin(f"https://{domain}", s) for s in series_matches]
                for sm in series_matches:
                    if sm not in series_candidates:
                        series_candidates.append(sm)
                if series_candidates:
                    result["sample_series_url"] = series_candidates[0]
                    result["search_status"] = "WARNING"
                    result["search_error"] = "Query returned 0 results, but active series extracted from homepage"
        except Exception as e:
            result["search_error"] = f"Domain unreachable (https://{domain}): {e}"
            result["failure_category"] = "DOMAIN_OUTAGE"

    # --- Phase 2: Direct Series Inspection Test ---
    series_data = None
    series_url_to_test = None
    first_attempt_data = None
    if series_candidates:
        for cand_url in series_candidates[:5]:
            try:
                s_data = await asyncio.wait_for(
                    asyncio.to_thread(extractor_dispatcher.inspect_series, cand_url),
                    timeout=25.0
                )
                if not first_attempt_data and s_data:
                    first_attempt_data = (s_data, cand_url)
                if s_data and s_data.get("chapters"):
                    real_ch = [
                        c for c in s_data["chapters"]
                        if c.get("url") and c.get("url").rstrip('/') != cand_url.rstrip('/')
                    ]
                    if real_ch:
                        series_data = s_data
                        series_url_to_test = cand_url
                        result["sample_series_url"] = cand_url
                        break
            except Exception as e:
                if not result.get("direct_parse_error"):
                    result["direct_parse_error"] = str(e)

        if not series_data and first_attempt_data:
            series_data, series_url_to_test = first_attempt_data

        if series_data and isinstance(series_data, dict):
            status_code = series_data.get("status_code", 200)
            chapters = series_data.get("chapters", [])
            err = series_data.get("error")

            real_chapters = [
                c for c in chapters
                if c.get("url") and c.get("url").rstrip('/') != (series_url_to_test or "").rstrip('/')
            ]
            if real_chapters:
                result["direct_parse_status"] = "PASS"
                result["chapters_found"] = len(real_chapters)
                ch_url = None
                for c in real_chapters:
                    u = c.get("url", "")
                    if any(k in u.lower() for k in ("chapter", "ch-", "ch/", "/c-", "/c/")):
                        ch_url = u
                        break
                if not ch_url:
                    ch_url = real_chapters[0].get("url")
                result["sample_chapter_url"] = ch_url
            else:
                result["direct_parse_status"] = "FAIL"
                if status_code in (403, 503):
                    result["direct_parse_error"] = f"HTTP {status_code}: Cloudflare or anti-bot challenge active"
                    result["failure_category"] = "BOT_CHALLENGE"
                elif err:
                    result["direct_parse_error"] = f"Series inspector error: {err}"
                else:
                    result["direct_parse_error"] = f"Series page loaded (HTTP {status_code}) but 0 chapters parsed (CSS selectors broken)"
                    result["failure_category"] = "SELECTOR_MISMATCH"
        else:
            result["direct_parse_status"] = "FAIL"
            result["direct_parse_error"] = result.get("direct_parse_error") or "inspect_series returned empty or invalid response"
    else:
        result["direct_parse_status"] = "SKIPPED"
        result["direct_parse_error"] = "No series URL available to test inspection"

    # --- Phase 3: Chapter Image Extraction Test ---
    sample_chapter_url = result.get("sample_chapter_url")
    if test_image_extraction and sample_chapter_url:
        try:
            chapter_data = await asyncio.wait_for(
                asyncio.to_thread(
                    extractor_dispatcher.analyze_url,
                    sample_chapter_url
                ),
                timeout=35.0
            )

            if chapter_data and isinstance(chapter_data, dict):
                status_code = chapter_data.get("status_code", 0)
                panels = chapter_data.get("pages") or chapter_data.get("panels") or []
                err = chapter_data.get("error")

                if panels and len(panels) > 0:
                    result["image_extract_status"] = "PASS"
                    result["panels_found"] = len(panels)
                else:
                    result["image_extract_status"] = "FAIL"
                    if status_code in (403, 503):
                        result["image_extract_error"] = f"HTTP {status_code}: Anti-bot challenge on chapter page"
                        result["failure_category"] = "BOT_CHALLENGE"
                    elif err:
                        result["image_extract_error"] = f"Chapter analysis error: {err}"
                    else:
                        result["image_extract_error"] = f"Chapter page loaded (HTTP {status_code}) but 0 image panels extracted (Decryption/CDN selector issue)"
                        result["failure_category"] = "SELECTOR_MISMATCH"
            else:
                result["image_extract_status"] = "FAIL"
                result["image_extract_error"] = "analyze_url returned empty or invalid response"
        except asyncio.TimeoutError:
            result["image_extract_status"] = "FAIL"
            result["image_extract_error"] = "Image extraction timed out after 35s (CDN or Cloudflare challenge hang)"
            result["failure_category"] = "TIMEOUT"
        except Exception as e:
            result["image_extract_status"] = "FAIL"
            result["image_extract_error"] = f"Image extraction exception: {type(e).__name__} - {str(e)}"
    else:
        result["image_extract_status"] = "SKIPPED"
        if not sample_chapter_url:
            result["image_extract_error"] = "Skipped: No valid chapter URL available from series inspection"

    # --- Evaluate Overall Status & Non-Compliance ---
    failures = []
    if result["search_status"] == "FAIL" and result["direct_parse_status"] != "PASS":
        failures.append(f"Global Search Failure ({result['search_error']})")
    if result["direct_parse_status"] == "FAIL":
        failures.append(f"Direct Link Parsing Failure ({result['direct_parse_error']})")
    if result["image_extract_status"] == "FAIL":
        failures.append(f"Image Extraction Failure ({result['image_extract_error']})")

    if failures:
        result["overall_status"] = "FAIL"
        result["non_compliance_reason"] = " | ".join(failures)
        if not result["failure_category"]:
            if any("403" in f or "anti-bot" in f.lower() or "challenge" in f.lower() for f in failures):
                result["failure_category"] = "BOT_CHALLENGE"
            elif any("selector" in f.lower() or "0 distinct chapters" in f.lower() for f in failures):
                result["failure_category"] = "SELECTOR_MISMATCH"
            elif any("unreachable" in f.lower() or "connection" in f.lower() for f in failures):
                result["failure_category"] = "DOMAIN_OUTAGE"
            else:
                result["failure_category"] = "SCRAPER_ERROR"
    else:
        result["overall_status"] = "PASS"
        result["non_compliance_reason"] = None
        result["failure_category"] = None

    elapsed = round(time.time() - t0, 2)
    print(f"[{result['overall_status']}] {name} ({key}) - {elapsed}s" + (f" -> {result['non_compliance_reason']}" if failures else ""))

    return result


async def run_test_batch(
    dispatcher: SearchDispatcher,
    sources: List[Dict[str, Any]],
    query: str,
    concurrency: int,
    skip_images: bool = False
) -> List[Dict[str, Any]]:
    """Execute testing across a set of sources with bounded concurrency and authentic browser profile."""
    conn = aiohttp.TCPConnector(ssl=False)
    semaphore = asyncio.Semaphore(concurrency)

    async def sem_worker(src: Dict[str, Any], sess: aiohttp.ClientSession):
        async with semaphore:
            return await test_single_source(
                dispatcher,
                src,
                query,
                sess,
                test_image_extraction=not skip_images
            )

    async with aiohttp.ClientSession(connector=conn, headers=BROWSER_HEADERS) as session:
        tasks = [sem_worker(s, session) for s in sources]
        return await asyncio.gather(*tasks, return_exceptions=False)


async def main_async(args: argparse.Namespace):
    all_sources = get_all_registered_sources()
    if args.sources and args.sources.lower() != "all":
        target_keys = set(k.strip().lower() for k in args.sources.split(","))
        sources_to_test = [s for s in all_sources if s.get("key", "").lower() in target_keys]
        if not sources_to_test:
            print(f"Warning: No sources matched '{args.sources}'. Available keys: {[s.get('key') for s in all_sources]}")
            sources_to_test = all_sources[:3]
    else:
        sources_to_test = all_sources

    print(f"=== Starting Scraper Health Check (Pass 1) ===")
    print(f"Sources to test: {len(sources_to_test)}")
    print(f"Search query: '{args.query}'")
    print(f"Concurrency limit: {args.concurrency}")
    print("=" * 38)

    dispatcher = SearchDispatcher(concurrency_limit=args.concurrency, timeout_seconds=20.0)

    # Pass 1: Standard batch run
    results = await run_test_batch(
        dispatcher,
        sources_to_test,
        args.query,
        concurrency=args.concurrency,
        skip_images=args.skip_images
    )

    # Identify any failed sources from Pass 1
    failed_keys = [r["key"] for r in results if r.get("overall_status") == "FAIL"]

    # --- Resilient Pass 2: Isolated Sequential Verification ---
    # Eliminates false positives caused by concurrent IP rate-limiting or temporary connection resets.
    if failed_keys:
        print("\n" + "=" * 38)
        print(f"⚠️ [Sentinel] {len(failed_keys)} source(s) flagged during Pass 1: {failed_keys}")
        print("⏳ [Sentinel] Cooling down for 6 seconds to clear any transient rate limits / IP throttling...")
        await asyncio.sleep(6.0)
        print("🔄 [Sentinel] Initiating Pass 2: Isolated sequential re-verification of suspect sources...")
        print("=" * 38)

        suspect_sources = [s for s in sources_to_test if s.get("key") in failed_keys]
        retry_dispatcher = SearchDispatcher(concurrency_limit=1, timeout_seconds=25.0)

        retry_results = await run_test_batch(
            retry_dispatcher,
            suspect_sources,
            args.query,
            concurrency=1,
            skip_images=args.skip_images
        )

        retry_map = {r["key"]: r for r in retry_results}

        # Merge results with dual-pass confirmation
        for i, r in enumerate(results):
            k = r.get("key")
            if k in retry_map:
                retried = retry_map[k]
                if retried["overall_status"] == "PASS":
                    print(f"✅ [RECOVERED] {r['name']} ({k}) passed isolated retry! (Pass 1 was transient rate limit/glitch)")
                    retried["dual_pass_status"] = "RECOVERED_ON_RETRY"
                    results[i] = retried
                else:
                    print(f"❌ [CONFIRMED FAILURE] {r['name']} ({k}) failed both Pass 1 and isolated Pass 2!")
                    retried["dual_pass_status"] = "CONFIRMED_BROKEN"
                    results[i] = retried

    passed_count = sum(1 for r in results if r["overall_status"] == "PASS")
    failed_count = sum(1 for r in results if r["overall_status"] == "FAIL")

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "query_used": args.query,
        "concurrency_used": args.concurrency,
        "total_tested": len(results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "results": results,
    }

    out_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=" * 38)
    print(f"Health Check Completed: {passed_count} PASS, {failed_count} FAIL.")
    print(f"Full JSON report saved to: {out_path}")

    # Return exit code 0 so workflow can proceed to issue manager step
    sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Scraper Health Check Sentinel (Resilient)")
    parser.add_argument("--sources", default="all", help="Comma-separated list of source keys or 'all'")
    parser.add_argument("--query", default="hero", help="Search query to test")
    parser.add_argument("--concurrency", type=int, default=2, help="Maximum concurrent requests (default: 2)")
    parser.add_argument("--skip-images", action="store_true", help="Skip chapter image extraction phase")
    parser.add_argument("--output", default=".github/reports/scraper_health.json", help="Path to output JSON report")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
