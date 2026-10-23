#!/usr/bin/env python3
"""
Daily Scraper Sentinel & Health Check Script
Tests every registered manga/manhua source for:
  1. Global Search functionality (querying terms and returning valid series URLs)
  2. Direct Link Parsing (inspecting series page, resolving chapter list)
  3. Chapter Image Extraction (extracting panel image URLs)

Outputs a comprehensive JSON report used by the issue manager.
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
import asyncio
from typing import List, Dict, Any, Optional

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


async def test_single_source(
    dispatcher: SearchDispatcher,
    source: Dict[str, Any],
    query: str,
    session: aiohttp.ClientSession,
    test_image_extraction: bool = True
) -> Dict[str, Any]:
    """
    Run an end-to-end compliance test on a single source:
    1. Search query
    2. Direct series inspection
    3. Chapter image extraction
    """
    key = source.get("key", "unknown")
    name = source.get("name", key)
    stype = source.get("type", "unknown")
    domain = source.get("domain", "")

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
    }

    t0 = time.time()

    # --- Phase 1: Global Search Test ---
    hits = []
    queries_to_try = [query]
    for alt_q in ("magic", "secret", "apartment", "return"):
        if alt_q != query:
            queries_to_try.append(alt_q)

    series_candidates = []
    for q_try in queries_to_try:
        try:
            cur_hits = await asyncio.wait_for(
                dispatcher._query_single_source(source, q_try, session),
                timeout=25.0
            )
            if cur_hits and isinstance(cur_hits, list):
                valid_hits = [h for h in cur_hits if (h.get("series_url") or h.get("url")) and h.get("title")]
                if valid_hits:
                    cand_list = []
                    for vh in valid_hits:
                        u = vh.get("series_url") or vh.get("url")
                        if u and u not in cand_list:
                            cand_list.append(u)
                    if cand_list:
                        test_cand = cand_list[0]
                        s_chk = await asyncio.to_thread(extractor_dispatcher.inspect_series, test_cand)
                        if s_chk and any(c.get("url") and c.get("url").rstrip('/') != test_cand.rstrip('/') for c in s_chk.get("chapters", [])):
                            hits = cur_hits
                            query = q_try
                            series_candidates = cand_list
                            break
                        elif not series_candidates:
                            hits = cur_hits
                            series_candidates = cand_list
        except asyncio.TimeoutError:
            result["search_error"] = "Search request timed out after 25s (Network latency or anti-bot hang)"
        except Exception as e:
            result["search_error"] = f"Search exception: {type(e).__name__} - {str(e)}"

    if series_candidates:
        result["search_status"] = "PASS"
        result["search_hits"] = len(series_candidates)
        result["sample_series_url"] = series_candidates[0]
    else:
        result["search_status"] = "FAIL"
        if not result["search_error"]:
            result["search_error"] = f"Search returned 0 results for queries {queries_to_try} (Selector changed, site structure updated, or blocked)"

    # Fallback series URL if search failed but domain is specified
    if not series_candidates and domain:
        # Try fetching domain homepage to extract an active series link
        try:
            home_code, home_html, home_soup = await asyncio.to_thread(extractor_dispatcher.fetch_page, f"https://{domain}")
            if home_html:
                series_matches = re.findall(rf'href=[\"\'](https?://(?:www\.)?{re.escape(domain)}/(?:manga|series|comic|comics|webtoon)/[^/\"\'#?]+/?)[^\"\']*[\"\']', home_html, re.I)
                if not series_matches:
                    series_matches = re.findall(r'href=[\"\'](/(?:manga|series|comic|comics|webtoon)/[^/\"\'#?]+/?)[^\"\']*[\"\']', home_html, re.I)
                    if series_matches:
                        series_matches = [urllib.parse.urljoin(f"https://{domain}", s) for s in series_matches]
                for sm in series_matches:
                    if sm not in series_candidates:
                        series_candidates.append(sm)
                if series_candidates:
                    result["sample_series_url"] = series_candidates[0]
        except Exception:
            pass

    # --- Phase 2: Direct Series Inspection Test ---
    series_data = None
    series_url_to_test = None
    if series_candidates:
        for cand_url in series_candidates[:3]:
            try:
                s_data = await asyncio.wait_for(
                    asyncio.to_thread(extractor_dispatcher.inspect_series, cand_url),
                    timeout=25.0
                )
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
                if not series_data and s_data:
                    series_data = s_data
                    series_url_to_test = cand_url
            except Exception as e:
                if not result.get("direct_parse_error"):
                    result["direct_parse_error"] = str(e)

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
                result["direct_parse_error"] = f"Series page loaded (HTTP {status_code}) but 0 distinct chapters were parsed"
                if status_code in (403, 503):
                    result["direct_parse_error"] = f"HTTP {status_code}: Cloudflare or anti-bot challenge active"
                elif err:
                    result["direct_parse_error"] = f"Series inspector error: {err}"
                else:
                    result["direct_parse_error"] = f"Series page loaded (HTTP {status_code}) but 0 chapters were parsed (CSS selectors broken)"
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
                    elif err:
                        result["image_extract_error"] = f"Chapter analysis error: {err}"
                    else:
                        result["image_extract_error"] = f"Chapter page loaded (HTTP {status_code}) but 0 image panels were extracted"
            else:
                result["image_extract_status"] = "FAIL"
                result["image_extract_error"] = "analyze_url returned empty or invalid response"
        except asyncio.TimeoutError:
            result["image_extract_status"] = "FAIL"
            result["image_extract_error"] = "Image extraction timed out after 35s (CDN or Cloudflare challenge hang)"
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
    else:
        result["overall_status"] = "PASS"
        result["non_compliance_reason"] = None

    elapsed = round(time.time() - t0, 2)
    print(f"[{result['overall_status']}] {name} ({key}) - {elapsed}s" + (f" -> {result['non_compliance_reason']}" if failures else ""))

    return result


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

    print(f"=== Starting Scraper Health Check ===")
    print(f"Sources to test: {len(sources_to_test)}")
    print(f"Search query: '{args.query}'")
    print(f"Concurrency limit: {args.concurrency}")
    print("=" * 38)

    dispatcher = SearchDispatcher(concurrency_limit=args.concurrency, timeout_seconds=20.0)
    conn = aiohttp.TCPConnector(ssl=False)
    
    semaphore = asyncio.Semaphore(args.concurrency)

    async def sem_task(src: Dict[str, Any], sess: aiohttp.ClientSession):
        async with semaphore:
            return await test_single_source(
                dispatcher,
                src,
                args.query,
                sess,
                test_image_extraction=not args.skip_images
            )

    results = []
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = [sem_task(s, session) for s in sources_to_test]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    passed_count = sum(1 for r in results if r["overall_status"] == "PASS")
    failed_count = sum(1 for r in results if r["overall_status"] == "FAIL")

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "query_used": args.query,
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
    parser = argparse.ArgumentParser(description="Scraper Health Check Sentinel")
    parser.add_argument("--sources", default="all", help="Comma-separated list of source keys or 'all'")
    parser.add_argument("--query", default="hero", help="Search query to test")
    parser.add_argument("--concurrency", type=int, default=4, help="Maximum concurrent requests")
    parser.add_argument("--skip-images", action="store_true", help="Skip chapter image extraction phase")
    parser.add_argument("--output", default=".github/reports/scraper_health.json", help="Path to output JSON report")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
