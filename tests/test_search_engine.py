import os
import unittest
import tempfile
import asyncio
from core.search.clustering import normalize_title, token_sort_ratio, is_same_series, cluster_search_results
from core.search.dispatcher import search_dispatcher
from database.db import (
    init_db,
    get_cached_search,
    set_cached_search,
    add_or_update_series_source,
    get_series_sources,
    get_or_create_series
)

class TestSearchEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_normalize_title(self):
        t1 = "Solo Leveling [Season 2] (Official)"
        self.assertEqual(normalize_title(t1), "solo leveling")

        t2 = "Nano Machine: Return of the Demonic Cult!"
        self.assertEqual(normalize_title(t2), "nano machine return of the demonic cult")

    def test_token_sort_ratio(self):
        s1 = "Solo Leveling"
        s2 = "Leveling Solo"
        self.assertEqual(token_sort_ratio(s1, s2), 1.0)

        s3 = "Nano Machine"
        s4 = "Nano Machine (Official)"
        self.assertGreaterEqual(token_sort_ratio(s3, s4), 0.95)

    def test_is_same_series_with_alt_titles(self):
        # Even if titles look different, alt_titles should bridge them
        t1 = "Solo Leveling"
        alt1 = ["Na Honjaman Level Up", "I Alone Level Up"]
        t2 = "Na Honjaman Level Up"
        self.assertTrue(is_same_series(t1, t2, alt_titles1=alt1))

    def test_cluster_search_results_deduplication(self):
        raw_hits = [
            {
                "title": "Solo Leveling",
                "alt_titles": ["Na Honjaman Level Up"],
                "source_key": "flame",
                "source_name": "Flame Comics",
                "series_url": "https://flamecomics.me/series/solo-leveling",
                "cover_url": "https://flame.com/cover.jpg",
                "latest_chapter": "Chapter 210",
                "latest_chapter_num": 210.0,
                "latency_ms": 280
            },
            {
                "title": "Solo Leveling (Official)",
                "alt_titles": [],
                "source_key": "asura",
                "source_name": "Asura Scans",
                "series_url": "https://asuracomic.net/series/solo-leveling",
                "cover_url": "https://asura.com/cover.jpg",
                "latest_chapter": "Chapter 210",
                "latest_chapter_num": 210.0,
                "latency_ms": 340
            },
            {
                "title": "Nano Machine",
                "alt_titles": [],
                "source_key": "asura",
                "source_name": "Asura Scans",
                "series_url": "https://asuracomic.net/series/nano-machine",
                "cover_url": "https://asura.com/nano.jpg",
                "latest_chapter": "Chapter 218",
                "latest_chapter_num": 218.0,
                "latency_ms": 220
            }
        ]

        clusters = cluster_search_results(raw_hits)
        # Should cluster into 2 series: Solo Leveling (with 2 sources) and Nano Machine (with 1 source)
        self.assertEqual(len(clusters), 2)

        solo_cluster = next((c for c in clusters if "solo" in c["title"].lower()), None)
        self.assertIsNotNone(solo_cluster)
        self.assertEqual(solo_cluster["total_sources"], 2)
        self.assertEqual(len(solo_cluster["sources"]), 2)
        self.assertEqual(solo_cluster["latest_chapter_num"], 210.0)

    def test_search_cache_ttl(self):
        query = "Magic Emperor"
        data = [{"title": "Magic Emperor", "total_sources": 3}]

        # Before setting cache, should be None
        self.assertIsNone(get_cached_search(query, db_path=self.db_path))

        # Set cache
        set_cached_search(query, data, ttl_seconds=60, db_path=self.db_path)

        # Retrieve cache
        cached = get_cached_search(query, db_path=self.db_path)
        self.assertIsNotNone(cached)
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]["title"], "Magic Emperor")

    def test_series_sources_storage(self):
        s_id = get_or_create_series("test-series", "Test Series", db_path=self.db_path)

        # Add Source 1
        add_or_update_series_source(
            series_id=s_id,
            source_key="asura",
            source_name="Asura Scans",
            source_url="https://asuracomic.net/series/test",
            total_chapters=100,
            latest_chapter_num=100.0,
            latency_ms=300,
            db_path=self.db_path
        )

        # Add Source 2
        add_or_update_series_source(
            series_id=s_id,
            source_key="flame",
            source_name="Flame Comics",
            source_url="https://flamecomics.me/series/test",
            total_chapters=105,
            latest_chapter_num=105.0,
            latency_ms=250,
            db_path=self.db_path
        )

        sources = get_series_sources(s_id, db_path=self.db_path)
        self.assertEqual(len(sources), 2)
        # Should be ordered by latest_chapter_num DESC
        self.assertEqual(sources[0]["source_key"], "flame")
        self.assertEqual(sources[0]["latest_chapter_num"], 105.0)

    def test_search_dispatcher_tiers(self):
        fast_sources = search_dispatcher.get_sources_for_tier("fast")
        self.assertGreaterEqual(len(fast_sources), 5)

        all_sources = search_dispatcher.get_sources_for_tier("all")
        self.assertGreater(len(all_sources), len(fast_sources))

    def test_sources_include_asura_rolia_topmanhua(self):
        fast_keys = [s["key"] for s in search_dispatcher.get_sources_for_tier("fast")]
        self.assertIn("asura", fast_keys)
        self.assertIn("arenascan", fast_keys)
        self.assertIn("flamecomics", fast_keys)
        self.assertIn("vortexscans", fast_keys)
        self.assertIn("roliascan", fast_keys)
        self.assertIn("topmanhua", fast_keys)
        self.assertIn("manhuaplus", fast_keys)
        self.assertIn("manhuatop", fast_keys)
        self.assertIn("ravenscans", fast_keys)

        # Check TopManhua domain is topmanhua.net
        topmanhua_src = next(s for s in search_dispatcher.get_sources_for_tier("fast") if s["key"] == "topmanhua")
        self.assertEqual(topmanhua_src.get("domain"), "topmanhua.net")

        # Check Arena Scans domain is arenascan.com
        arenascan_src = next(s for s in search_dispatcher.get_sources_for_tier("fast") if s["key"] == "arenascan")
        self.assertEqual(arenascan_src.get("domain"), "arenascan.com")

    def test_single_source_noise_suppression_when_multi_source_exists(self):
        # When multi-source matches exist, 1-source noise from aggregators or doujinshis should be suppressed
        raw_hits = [
            {
                "title": "Solo Leveling",
                "alt_titles": [],
                "source_key": "asura",
                "source_name": "Asura Scans",
                "series_url": "https://asurascans.com/comics/solo-leveling",
                "latest_chapter_num": 200.0,
            },
            {
                "title": "Solo Leveling",
                "alt_titles": [],
                "source_key": "arenascan",
                "source_name": "Arena Scans",
                "series_url": "https://arenascan.com/manga/solo-leveling",
                "latest_chapter_num": 200.0,
            },
            {
                "title": "Solo Leveling Doujinshi Fan Comic",
                "alt_titles": [],
                "source_key": "mangadex",
                "source_name": "MangaDex",
                "series_url": "https://mangadex.org/title/123",
                "latest_chapter_num": 1.0,
            },
            {
                "title": "Solo Leveling Novel",
                "alt_titles": [],
                "source_key": "mangapill",
                "source_name": "MangaPill",
                "series_url": "https://mangapill.com/manga/456",
                "latest_chapter_num": 1.0,
            }
        ]
        clusters = cluster_search_results(raw_hits, query="solo leveling")
        titles = [c["canonical_title"] for c in clusters]
        self.assertIn("Solo Leveling", titles)
        self.assertNotIn("Solo Leveling Doujinshi Fan Comic", titles)
        self.assertNotIn("Solo Leveling Novel", titles)

    def test_relevance_scoring_and_typo_handling(self):
        from core.search.clustering import compute_relevance_score, pick_best_canonical_title

        # Exact match
        score_exact = compute_relevance_score("solo leveling", "Solo Leveling")
        self.assertEqual(score_exact, 1000.0)

        # Typo match
        score_typo = compute_relevance_score("solo leaveling", "Solo Leveling")
        self.assertGreaterEqual(score_typo, 500.0)

        # Completely unrelated series should have low relevance score (< 140)
        score_unrelated = compute_relevance_score("solo leveling", "The Indomitable Martial King")
        self.assertLess(score_unrelated, 140.0)

        # Canonical title picking
        best_title = pick_best_canonical_title(
            title="Na Honjaman Level-Up",
            alt_titles=["Solo Leveling", "I Alone Level Up"],
            query="solo leveling"
        )
        self.assertEqual(best_title, "Solo Leveling")

    def test_clustering_relevance_filtering_and_sorting(self):
        raw_hits = [
            {
                "title": "The Indomitable Martial King",
                "alt_titles": [],
                "source_key": "mangahere",
                "source_name": "MangaHere",
                "series_url": "https://mangahere.cc/manga/indomitable",
                "latest_chapter": "Chapter 50",
                "latest_chapter_num": 50.0,
                "latency_ms": 200
            },
            {
                "title": "Na Honjaman Level-Up",
                "alt_titles": ["Solo Leveling"],
                "source_key": "asura",
                "source_name": "Asura Scans",
                "series_url": "https://asurascans.com/comics/solo-leveling",
                "latest_chapter": "Chapter 200",
                "latest_chapter_num": 200.0,
                "latency_ms": 150
            },
            {
                "title": "Solo Leveling: Ragnarok",
                "alt_titles": [],
                "source_key": "topmanhua",
                "source_name": "TopManhua",
                "series_url": "https://topmanhua.net/manga/solo-leveling-ragnarok",
                "latest_chapter": "Chapter 60",
                "latest_chapter_num": 60.0,
                "latency_ms": 180
            }
        ]

        # Test with typo query "solo leaveling"
        clusters = cluster_search_results(raw_hits, query="solo leaveling")
        # "The Indomitable Martial King" should be filtered out (< 140 relevance)
        cluster_titles = [c["canonical_title"] for c in clusters]
        self.assertNotIn("The Indomitable Martial King", cluster_titles)

        # Solo Leveling should be #1 with canonical title "Solo Leveling" and 200 chapters
        self.assertEqual(clusters[0]["canonical_title"], "Solo Leveling")
        self.assertEqual(clusters[0]["max_chapter_num"], 200.0)
        self.assertEqual(clusters[0]["latest_chapter"], "Chapter 200")

    def test_fastapi_search_endpoints(self):
        from fastapi.testclient import TestClient
        from app import app
        client = TestClient(app)

        # Empty query validation
        res = client.get("/api/search?q=")
        self.assertEqual(res.status_code, 400)

        # Prepopulate cache
        set_cached_search("mock series", [{"title": "Mock Series", "sources": []}])
        res = client.get("/api/search?q=mock+series")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("cached"))
        self.assertEqual(len(data.get("clusters", [])), 1)

        # SSE endpoint cached stream
        stream_res = client.get("/api/search/stream?q=mock+series")
        self.assertEqual(stream_res.status_code, 200)
        self.assertIn("event: complete", stream_res.text)

    def test_fastapi_series_sources_endpoints(self):
        from fastapi.testclient import TestClient
        from app import app
        client = TestClient(app)

        s_id = get_or_create_series("mock-source-series", "Mock Source Series")

        # Add source via POST
        post_res = client.post(f"/api/series/{s_id}/sources", json={
            "source_key": "mangadex",
            "source_name": "MangaDex",
            "source_url": "https://mangadex.org/title/123",
            "total_chapters": 150,
            "latest_chapter_num": 150.0,
            "quality_tag": "Original WebP",
            "latency_ms": 110
        })
        self.assertEqual(post_res.status_code, 200)

        # Get sources via GET
        get_res = client.get(f"/api/series/{s_id}/sources")
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(len(data.get("sources", [])), 1)
        self.assertEqual(data["sources"][0]["source_key"], "mangadex")

    def test_cloudflare_clearance_cache(self):
        from database.db import save_clearance_cookie, get_clearance_cookie
        # Save and retrieve cookie
        save_clearance_cookie("kunmanga.com", "cf_clearance=test_abc; __cf_bm=123", "TestChrome/124.0", ttl_hours=24, db_path=self.db_path)
        res = get_clearance_cookie("kunmanga.com", db_path=self.db_path)
        self.assertIsNotNone(res)
        self.assertIn("cf_clearance=test_abc", res["cookie_string"])
        self.assertEqual(res["user_agent"], "TestChrome/124.0")

        # Unknown domain returns None
        self.assertIsNone(get_clearance_cookie("nonexistent.xyz", db_path=self.db_path))

    def test_android_webview_resolver_fallback_safe(self):
        from extractors.browser_sidecar import solve_with_android_webview
        # On desktop / CI, should gracefully return None without raising exceptions
        res = solve_with_android_webview("https://kunmanga.com/?s=solo")
        self.assertIsNone(res)

if __name__ == "__main__":
    unittest.main()

