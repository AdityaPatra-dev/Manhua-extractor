import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app import app, download_queue_manager, DownloadRequest
from database.db import init_db, get_or_create_series, add_or_update_chapter


class TestUpdateAndSharedQueue(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        download_queue_manager.queue.clear()
        download_queue_manager.history.clear()
        download_queue_manager.active_job = None
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_v2_5.db")
        init_db(self.db_path)

    def tearDown(self):
        download_queue_manager.queue.clear()
        download_queue_manager.history.clear()
        download_queue_manager.active_job = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("app.download_queue_manager.ensure_worker")
    @patch("core.updater.dispatcher.inspect_series")
    def test_single_series_check_update_finds_and_queues_new_chapters(self, mock_inspect, mock_worker):
        # Setup: Series in DB with chapters 1 and 2 completed
        series_id = get_or_create_series(
            slug="solo-leveling",
            title="Solo Leveling",
            source_url="https://example.com/manga/solo-leveling/",
            db_path=self.db_path
        )
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=1.0,
            source_url="https://example.com/manga/solo-leveling/ch-1",
            status="completed",
            db_path=self.db_path
        )
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=2.0,
            source_url="https://example.com/manga/solo-leveling/ch-2",
            status="completed",
            db_path=self.db_path
        )

        # Mock inspect_series returning chapters 1, 2, 3, 4
        mock_inspect.return_value = {
            "success": True,
            "series_title": "Solo Leveling",
            "series_cover": "https://example.com/cover.jpg",
            "chapters": [
                {"title": "Chapter 1", "chapter_num": 1.0, "url": "https://example.com/manga/solo-leveling/ch-1"},
                {"title": "Chapter 2", "chapter_num": 2.0, "url": "https://example.com/manga/solo-leveling/ch-2"},
                {"title": "Chapter 3", "chapter_num": 3.0, "url": "https://example.com/manga/solo-leveling/ch-3"},
                {"title": "Chapter 4", "chapter_num": 4.0, "url": "https://example.com/manga/solo-leveling/ch-4"},
            ]
        }

        with patch("database.db.DEFAULT_DB_PATH", self.db_path), \
             patch("core.updater.get_series_by_id", lambda sid: {"id": sid, "title": "Solo Leveling", "source_url": "https://example.com/manga/solo-leveling/", "cover_url": "https://example.com/cover.jpg"}), \
             patch("core.updater.get_chapters_for_series", lambda sid: [
                 {"chapter_num": 1.0, "status": "completed", "source_url": "https://example.com/manga/solo-leveling/ch-1"},
                 {"chapter_num": 2.0, "status": "completed", "source_url": "https://example.com/manga/solo-leveling/ch-2"}
             ]):
            resp = self.client.post(f"/api/library/{series_id}/check-update")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            self.assertTrue(data["success"])
            self.assertTrue(data["queued"])
            self.assertEqual(data["series_title"], "Solo Leveling")
            self.assertEqual(data["new_chapters"], [3.0, 4.0])

            # Verify chapters were enqueued into download_queue_manager
            state = download_queue_manager.get_state()
            active_or_queued = state["queue"] + ([state["active_job"]] if state["active_job"] else [])
            self.assertTrue(len(active_or_queued) > 0)
            queued_job = active_or_queued[0]
            self.assertEqual(queued_job["series_title"], "Solo Leveling")
            self.assertEqual(queued_job["total_chapters"], 2)

    @patch("app.download_queue_manager.ensure_worker")
    @patch("core.updater.dispatcher.inspect_series")
    def test_single_series_check_update_already_up_to_date(self, mock_inspect, mock_worker):
        # Mock inspect_series returning only chapter 1
        mock_inspect.return_value = {
            "success": True,
            "series_title": "Omniscient Reader",
            "chapters": [
                {"title": "Chapter 1", "chapter_num": 1.0, "url": "https://example.com/manga/orv/ch-1"}
            ]
        }

        with patch("core.updater.get_series_by_id", lambda sid: {"id": sid, "title": "Omniscient Reader", "source_url": "https://example.com/manga/orv/"}), \
             patch("core.updater.get_chapters_for_series", lambda sid: [
                 {"chapter_num": 1.0, "status": "completed", "source_url": "https://example.com/manga/orv/ch-1"}
             ]):
            resp = self.client.post("/api/library/999/check-update")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            self.assertTrue(data["success"])
            self.assertFalse(data["queued"])
            self.assertEqual(data["new_chapters"], [])
            self.assertIn("already up to date", data["message"].lower())

    @patch("app.download_queue_manager.ensure_worker")
    def test_queue_deduplication(self, mock_worker):
        req1 = DownloadRequest(
            url="https://example.com/series/ch1",
            series_title="Series Alpha",
            chapter_urls=["https://example.com/series/ch1", "https://example.com/series/ch2"]
        )
        job1 = download_queue_manager.enqueue(req1)
        self.assertEqual(len(download_queue_manager.queue), 1)

        # Enqueue the exact same request again
        req2 = DownloadRequest(
            url="https://example.com/series/ch1",
            series_title="Series Alpha",
            chapter_urls=["https://example.com/series/ch1", "https://example.com/series/ch2"]
        )
        job2 = download_queue_manager.enqueue(req2)

        # Deduplication must return existing job and NOT append a duplicate to queue
        self.assertEqual(job1["id"], job2["id"])
        self.assertEqual(len(download_queue_manager.queue), 1)

    @patch("app.download_queue_manager.ensure_worker")
    def test_multi_manhua_shared_queue_ordering(self, mock_worker):
        # Enqueue 5 chapters of Manhua A
        req_a = DownloadRequest(
            url="https://example.com/manhua_a/ch1",
            series_title="Manhua A",
            chapter_urls=[f"https://example.com/manhua_a/ch{i}" for i in range(1, 6)],
            format="pdf"
        )
        job_a = download_queue_manager.enqueue(req_a)

        # Enqueue 3 chapters of Manhua B
        req_b = DownloadRequest(
            url="https://example.com/manhua_b/ch1",
            series_title="Manhua B",
            chapter_urls=[f"https://example.com/manhua_b/ch{i}" for i in range(1, 4)],
            format="cbz"
        )
        job_b = download_queue_manager.enqueue(req_b)

        # Check queue state
        state = download_queue_manager.get_state()
        all_jobs = ([state["active_job"]] if state["active_job"] else []) + state["queue"]

        self.assertEqual(len(all_jobs), 2)
        self.assertEqual(all_jobs[0]["series_title"], "Manhua A")
        self.assertEqual(all_jobs[0]["total_chapters"], 5)

        self.assertEqual(all_jobs[1]["series_title"], "Manhua B")
        self.assertEqual(all_jobs[1]["total_chapters"], 3)
        self.assertEqual(all_jobs[1]["status"], "queued")

    @patch("core.updater.run_library_update", new_callable=AsyncMock)
    def test_global_library_update_endpoint_never_400s(self, mock_run):
        mock_run.return_value = {"total_series": 5, "updated_series_count": 2, "total_new_chapters": 10}
        resp = self.client.post("/api/library/update")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("queue", data["message"].lower())


if __name__ == "__main__":
    unittest.main()
