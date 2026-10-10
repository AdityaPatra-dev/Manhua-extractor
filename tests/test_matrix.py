import os
import sys
import unittest

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import init_db, get_all_site_diagnostics
from extractors.dispatcher import dispatcher

TEST_TARGET_SITES = [
    # ManhuaPlus (Liliana / MangaStream)
    {
        "name": "ManhuaPlus",
        "url": "https://manhuaplus.org/manga/apotheosis/chapter-1301",
        "expected_engine": "mangastream"
    },
    # Toonily (WordPress Madara)
    {
        "name": "Toonily (Madara)",
        "url": "https://toonily.com/webtoon/bastard/chapter-1/",
        "expected_engine": "madara"
    },
    # Modern SSR / Astro (Asura Scans)
    {
        "name": "Asura Scans (Astro v7)",
        "url": "https://asurascans.com/comics/pick-up-a-grimoire-become-a-mage-bd5bdaf8/chapter/1",
        "expected_engine": "modern_ssr"
    }
]

def run_compatibility_benchmark():
    print("=" * 65)
    print("   UNIVERSAL MANHUA EXTRACTOR: SITE COMPATIBILITY BENCHMARK   ")
    print("=" * 65)

    init_db()
    passed = 0
    total = len(TEST_TARGET_SITES)

    for item in TEST_TARGET_SITES:
        name = item["name"]
        url = item["url"]
        expected = item["expected_engine"]

        print(f"\n[*] Testing: {name} ({url})")
        try:
            res = dispatcher.analyze_url(url)
            if res.get("success") and res.get("panel_count", 0) > 0:
                print(f" [✅] PASS | Engine: {res.get('engine_name')} | Panels: {res.get('panel_count')} | Title: {res.get('series_title')}")
                passed += 1
            else:
                print(f" [❌] FAIL | Error: {res.get('error', 'Zero panels isolated')}")
        except Exception as e:
            print(f" [❌] EXCEPTION | {e}")

    print("\n" + "=" * 65)
    print(f"Benchmark Complete: {passed}/{total} sites passed ({(passed/total)*100:.1f}%)")
    print("=" * 65)

if __name__ == "__main__":
    run_compatibility_benchmark()
