import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import app
from database.db import (
    init_db,
    get_or_create_series,
    add_or_update_chapter,
    update_reading_progress,
    is_series_updatable,
    _calc_release_schedule,
    set_series_auto_update,
    get_series_by_id,
    get_all_series,
    STATIC_DOMAINS,
    STATIC_ENGINES,
)
from core.updater import check_and_enqueue_series_update, run_library_update


class TestLibraryUpdateFilter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_filter.db")
        init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_static_manga_domains_and_engines_excluded(self):
        """Test that static manga and doujinshi websites are recognized and skipped."""
        test_cases = [
            ({"source_url": "https://hitomi.la/doujinshi/test-123.html", "engine": "hitomi"}, False),
            ({"source_url": "https://hentaifox.com/g/9999/", "engine": "hentaifox"}, False),
            ({"source_url": "https://3hentai.net/d/12345", "engine": "threehentai"}, False),
            ({"source_url": "https://nhentai.net/g/8888/", "engine": "nhentaito"}, False),
            ({"source_url": "https://nhentai.xxx/g/8888/", "engine": "nhentaicom"}, False),
            ({"source_url": "https://hentai.name/g/7777/", "engine": "hentainame"}, False),
            ({"source_url": "https://comicland.org/manga/one-shot/", "engine": "comicland"}, False),
            ({"source_url": "https://e-hentai.org/g/123/456/", "engine": "auto"}, False),
            ({"source_url": "https://exhentai.org/g/123/456/", "engine": "auto"}, False),
            ({"source_url": "https://pururin.io/gallery/100/title", "engine": "auto"}, False),
            ({"source_url": "https://tsumino.com/entry/100", "engine": "auto"}, False),
        ]

        for series_dict, expected_updatable in test_cases:
            series_dict["status"] = "Ongoing"
            series_dict["auto_update"] = 1
            updatable, reason = is_series_updatable(series_dict)
            self.assertEqual(updatable, expected_updatable, f"Failed for {series_dict}")
            self.assertTrue("Static manga" in reason, f"Expected static manga in reason, got {reason}")

    def test_completed_series_excluded(self):
        """Completed or ended series should be skipped from auto-checks."""
        series_ongoing = {"source_url": "https://asuracomic.net/manga/solo-leveling", "engine": "asurascans", "status": "Ongoing", "auto_update": 1}
        self.assertTrue(is_series_updatable(series_ongoing)[0])

        for status in ["Completed", "Finished", "Cancelled", "Ended"]:
            series_completed = {"source_url": "https://asuracomic.net/manga/solo-leveling", "engine": "asurascans", "status": status, "auto_update": 1}
            updatable, reason = is_series_updatable(series_completed)
            self.assertFalse(updatable)
            self.assertEqual(reason, "Series status is Completed")

    def test_manual_toggle_auto_update(self):
        """User toggling auto-update off disables update checking."""
        series_id = get_or_create_series(
            slug="ongoing-test",
            title="Ongoing Test",
            source_url="https://asuracomic.net/manga/ongoing-test",
            engine="asurascans",
            db_path=self.db_path
        )
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertTrue(series["updatable"])

        # Toggle off
        set_series_auto_update(series_id, 0, db_path=self.db_path)
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertFalse(series["updatable"])
        self.assertEqual(series["updatable_reason"], "Auto-update disabled")

        # Toggle back on
        set_series_auto_update(series_id, 1, db_path=self.db_path)
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertTrue(series["updatable"])

    def test_calc_release_schedule(self):
        """Test release cadence calculations based on a 7-day chapter release cycle."""
        now = datetime.now(timezone.utc)

        # No previous download -> fallback to weekly cadence
        desc, short, exp_date = _calc_release_schedule(None)
        self.assertEqual(desc, "Weekly release (~7 days)")
        self.assertEqual(short, "Weekly")

        # Downloaded 2 days ago -> expected in ~5 days
        dl_2d = (now - timedelta(days=2)).isoformat()
        desc, short, exp_date = _calc_release_schedule(dl_2d)
        self.assertIn("in 5d", desc)
        self.assertEqual(short, "In 5d")

        # Downloaded 6 days ago -> expected tomorrow
        dl_6d = (now - timedelta(days=6)).isoformat()
        desc, short, exp_date = _calc_release_schedule(dl_6d)
        self.assertIn("Expected tomorrow", desc)
        self.assertEqual(short, "Tomorrow")

        # Downloaded 7 days ago -> due today / soon
        dl_7d = (now - timedelta(days=7)).isoformat()
        desc, short, exp_date = _calc_release_schedule(dl_7d)
        self.assertIn("Expected now", desc)
        self.assertEqual(short, "Due now")

        # Downloaded 10 days ago -> due soon (weekly)
        dl_10d = (now - timedelta(days=10)).isoformat()
        desc, short, exp_date = _calc_release_schedule(dl_10d)
        self.assertIn("Due soon", desc)
        self.assertEqual(short, "Due soon")

    def test_has_unread_red_dot_flag(self):
        """Test that has_unread is True when any downloaded chapter is unread, and False when read to the latest."""
        series_id = get_or_create_series(
            slug="unread-test",
            title="Unread Test Series",
            source_url="https://example.com/manga/unread-test",
            db_path=self.db_path
        )

        # No downloaded chapters yet -> has_unread is False
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertFalse(series["has_unread"])
        self.assertEqual(series["unread_count"], 0)

        # Chapter 1 downloaded, unread by default (read_status = 0)
        ch1_id = add_or_update_chapter(
            series_id=series_id,
            chapter_num=1.0,
            status="completed",
            db_path=self.db_path
        )
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertTrue(series["has_unread"])
        self.assertEqual(series["unread_count"], 1)

        # User finishes Chapter 1 (read_status = 2)
        update_reading_progress(ch1_id, read_status=2, last_read_page=20, db_path=self.db_path)
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertFalse(series["has_unread"])
        self.assertEqual(series["unread_count"], 0)

        # Chapter 2 gets downloaded (status="completed", default read_status=0)
        ch2_id = add_or_update_chapter(
            series_id=series_id,
            chapter_num=2.0,
            status="completed",
            db_path=self.db_path
        )
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertTrue(series["has_unread"])
        self.assertEqual(series["unread_count"], 1)

        # User finishes Chapter 2
        update_reading_progress(ch2_id, read_status=2, last_read_page=30, db_path=self.db_path)
        series = get_series_by_id(series_id, db_path=self.db_path)
        self.assertFalse(series["has_unread"])
        self.assertEqual(series["unread_count"], 0)

    @patch("core.updater.dispatcher.inspect_series")
    async def test_updater_skips_static_and_checks_concurrently(self, mock_inspect):
        """Test that check_and_enqueue_series_update skips static websites and checks updatable titles."""
        mock_inspect.return_value = {
            "success": True,
            "series_title": "Fast Check Title",
            "chapters": []
        }

        mock_queue = MagicMock()

        # 1. Static series check
        with patch("core.updater.get_series_by_id", return_value={
            "id": 101,
            "title": "Hitomi Gallery",
            "source_url": "https://hitomi.la/doujinshi/art-123.html",
            "engine": "hitomi",
            "status": "Ongoing",
            "auto_update": 1
        }):
            res_static = await check_and_enqueue_series_update(101, mock_queue)
            self.assertTrue(res_static["skipped"])
            self.assertIn("Static manga", res_static["reason"])
            mock_inspect.assert_not_called()

        # 2. Updatable series check
        with patch("core.updater.get_series_by_id", return_value={
            "id": 102,
            "title": "Ongoing Manhua",
            "source_url": "https://asuracomic.net/manga/manhua-1",
            "engine": "asurascans",
            "status": "Ongoing",
            "auto_update": 1
        }), patch("core.updater.get_chapters_for_series", return_value=[]):
            res_updatable = await check_and_enqueue_series_update(102, mock_queue)
            self.assertFalse(res_updatable.get("skipped", False))
            self.assertTrue(res_updatable["success"])
            mock_inspect.assert_called_once()

    def test_api_toggle_update_and_toggle_read(self):
        """Test API endpoints for toggling auto-update and toggling read status."""
        with patch("database.db.DEFAULT_DB_PATH", self.db_path):
            series_id = get_or_create_series(
                slug="api-test",
                title="API Test Series",
                source_url="https://example.com/manga/api-test",
                engine="auto"
            )
            ch_id = add_or_update_chapter(
                series_id=series_id,
                chapter_num=1.0,
                status="completed"
            )

            # Toggle update via API
            resp = self.client.post(f"/api/series/{series_id}/toggle-update", json={"auto_update": 0})
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["success"])
            self.assertEqual(resp.json()["auto_update"], 0)

            # Toggle chapter read via API
            resp = self.client.post(f"/api/chapter/{ch_id}/toggle-read", json={"read_status": 2})
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()["success"])
            self.assertEqual(resp.json()["read_status"], 2)


if __name__ == "__main__":
    unittest.main()
