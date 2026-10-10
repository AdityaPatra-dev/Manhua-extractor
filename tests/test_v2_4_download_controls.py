import asyncio
import unittest
from fastapi.testclient import TestClient
from app import app, download_progress
from core.downloader import download_panels_stream

class TestV24DownloadControls(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        download_progress["is_running"] = False
        download_progress["is_paused"] = False
        download_progress["is_cancelled"] = False

    def tearDown(self):
        download_progress["is_running"] = False
        download_progress["is_paused"] = False
        download_progress["is_cancelled"] = False

    def test_pause_resume_stop_when_idle(self):
        resp_p = self.client.post("/api/download/pause")
        self.assertEqual(resp_p.status_code, 400)
        self.assertFalse(resp_p.json()["success"])

        resp_r = self.client.post("/api/download/resume")
        self.assertEqual(resp_r.status_code, 400)
        self.assertFalse(resp_r.json()["success"])

        resp_s = self.client.post("/api/download/stop")
        self.assertEqual(resp_s.status_code, 400)
        self.assertFalse(resp_s.json()["success"])

    def test_pause_resume_stop_when_running(self):
        download_progress["is_running"] = True
        
        # Test Pause
        resp_p = self.client.post("/api/download/pause")
        self.assertEqual(resp_p.status_code, 200)
        self.assertTrue(resp_p.json()["success"])
        self.assertTrue(download_progress["is_paused"])
        self.assertEqual(download_progress["status"], "paused")

        # Test Resume
        resp_r = self.client.post("/api/download/resume")
        self.assertEqual(resp_r.status_code, 200)
        self.assertTrue(resp_r.json()["success"])
        self.assertFalse(download_progress["is_paused"])
        self.assertEqual(download_progress["status"], "downloading")

        # Test Stop
        resp_s = self.client.post("/api/download/stop")
        self.assertEqual(resp_s.status_code, 200)
        self.assertTrue(resp_s.json()["success"])
        self.assertTrue(download_progress["is_cancelled"])
        self.assertFalse(download_progress["is_paused"])
        self.assertEqual(download_progress["status"], "stopping")

    def test_downloader_stream_cancellation(self):
        urls = [
            "https://example.com/panel1.jpg",
            "https://example.com/panel2.jpg",
            "https://example.com/panel3.jpg"
        ]

        async def run_test():
            # Cancelled from the start
            res = await download_panels_stream(
                image_urls=urls,
                referer="https://example.com",
                is_cancelled_callback=lambda: True
            )
            self.assertEqual(res, [])

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()

