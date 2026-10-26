import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import json

from database.db import (
    init_db,
    get_or_create_series,
    add_or_update_chapter,
    get_all_series,
    get_chapters_for_series,
    get_series_by_id
)
from core.backup_engine import (
    calculate_chapter_disk_size,
    estimate_backup_batches,
    create_backup_batch_file,
    inspect_backup_archive,
    restore_backup_archive
)

class TestBackupAndSyncEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_library.db")
        self.downloads_dir = os.path.join(self.temp_dir, "downloads")
        os.makedirs(self.downloads_dir, exist_ok=True)
        init_db(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_mock_chapter_file(self, series_name: str, filename: str, size_bytes: int = 1024) -> str:
        s_dir = os.path.join(self.downloads_dir, series_name)
        os.makedirs(s_dir, exist_ok=True)
        fp = os.path.join(s_dir, filename)
        with open(fp, "wb") as f:
            f.write(b"X" * size_bytes)
        return fp

    def test_calculate_chapter_disk_size_file_and_folder(self):
        # 1. Single file test
        fp = self._create_mock_chapter_file("Solo_Leveling", "ch1.cbz", 5000)
        self.assertEqual(calculate_chapter_disk_size(fp), 5000)

        # 2. Directory/folder chapter test
        ch_folder = os.path.join(self.downloads_dir, "Solo_Leveling", "Ch_Raw_Folder")
        os.makedirs(ch_folder, exist_ok=True)
        with open(os.path.join(ch_folder, "p1.jpg"), "wb") as f:
            f.write(b"A" * 2000)
        with open(os.path.join(ch_folder, "p2.jpg"), "wb") as f:
            f.write(b"B" * 3000)
        self.assertEqual(calculate_chapter_disk_size(ch_folder), 5000)

    def test_estimate_backup_batches_bin_packing(self):
        # Create series and 3 chapters of 600 KB each
        s_id = get_or_create_series("test-series", "Test Series", db_path=self.db_path)
        f1 = self._create_mock_chapter_file("Test_Series", "ch1.cbz", 600 * 1024)
        f2 = self._create_mock_chapter_file("Test_Series", "ch2.cbz", 600 * 1024)
        f3 = self._create_mock_chapter_file("Test_Series", "ch3.cbz", 600 * 1024)

        add_or_update_chapter(s_id, 1.0, file_path=f1, file_size=600 * 1024, status="completed", db_path=self.db_path)
        add_or_update_chapter(s_id, 2.0, file_path=f2, file_size=600 * 1024, status="completed", db_path=self.db_path)
        add_or_update_chapter(s_id, 3.0, file_path=f3, file_size=600 * 1024, status="completed", db_path=self.db_path)

        # Target batch size 1500 KB (1.5 MB) -> should produce 2 batches (1200 KB + 600 KB)
        est = estimate_backup_batches(db_path=self.db_path, target_batch_bytes=1500 * 1024)
        self.assertEqual(est["total_chapters"], 3)
        self.assertEqual(est["batch_count"], 2)
        self.assertEqual(len(est["batches"]), 2)
        self.assertEqual(est["batches"][0]["chapter_count"], 2)
        self.assertEqual(est["batches"][1]["chapter_count"], 1)

    def test_export_and_inspect_archive(self):
        s_id = get_or_create_series("ultra-alter", "Ultra Alter", author="Author A", db_path=self.db_path)
        f1 = self._create_mock_chapter_file("Ultra_Alter", "ch1.pdf", 4000)
        cov = self._create_mock_chapter_file("Ultra_Alter", "cover.jpg", 1200)

        from database.db import update_series_cover
        update_series_cover(s_id, cov, db_path=self.db_path)
        add_or_update_chapter(s_id, 1.0, title="Chapter 1", file_path=f1, file_size=4000, status="completed", db_path=self.db_path)

        est = estimate_backup_batches(db_path=self.db_path)
        batch_items = est["batches"][0]["items"]

        out_zip = os.path.join(self.temp_dir, "backup_part1.zip")
        res = create_backup_batch_file(
            batch_index=1,
            total_batches=1,
            batch_items=batch_items,
            output_zip_path=out_zip,
            include_files=True
        )
        self.assertTrue(res["success"])
        self.assertTrue(os.path.exists(out_zip))

        # Inspect archive
        inspection = inspect_backup_archive(out_zip)
        self.assertTrue(inspection["success"])
        self.assertEqual(inspection["manifest"]["batch"]["batch_label"], "Complete Library")
        self.assertEqual(len(inspection["manifest"]["series"]), 1)
        self.assertEqual(inspection["manifest"]["series"][0]["title"], "Ultra Alter")

    def test_zip_slip_vulnerability_defense(self):
        # Create a malicious zip with traversal path
        malicious_zip = os.path.join(self.temp_dir, "malicious.zip")
        with zipfile.ZipFile(malicious_zip, 'w') as zf:
            zf.writestr("manifest.json", json.dumps({"format_version": "1.0"}))
            zf.writestr("../../etc/passwd", "root:x:0:0:")

        inspection = inspect_backup_archive(malicious_zip)
        self.assertFalse(inspection["success"])
        self.assertIn("Security violation", inspection["error"])

    def test_multi_zip_sequential_sync_and_path_remapping(self):
        # --- Simulate Phone A (Source) ---
        s_id = get_or_create_series("ultra-alter", "Ultra Alter", author="JIXKSEE", db_path=self.db_path)
        f1 = self._create_mock_chapter_file("Ultra_Alter", "ch1.pdf", 2000)
        f2 = self._create_mock_chapter_file("Ultra_Alter", "ch2.pdf", 2500)
        f3 = self._create_mock_chapter_file("Ultra_Alter", "ch3.pdf", 3000)

        add_or_update_chapter(s_id, 1.0, title="Chapter 1", file_path=f1, file_size=2000, status="completed", db_path=self.db_path)
        add_or_update_chapter(s_id, 2.0, title="Chapter 2", file_path=f2, file_size=2500, status="completed", db_path=self.db_path)
        add_or_update_chapter(s_id, 3.0, title="Chapter 3", file_path=f3, file_size=3000, status="completed", db_path=self.db_path)

        # Batch 1: Chapter 1 & 2
        est1 = estimate_backup_batches(db_path=self.db_path, target_batch_bytes=5000)
        self.assertEqual(est1["batch_count"], 2)

        zip_part1 = os.path.join(self.temp_dir, "phoneA_part1.zip")
        zip_part2 = os.path.join(self.temp_dir, "phoneA_part2.zip")

        create_backup_batch_file(1, 2, est1["batches"][0]["items"], zip_part1)
        create_backup_batch_file(2, 2, est1["batches"][1]["items"], zip_part2)

        # --- Simulate Phone B (Empty Target with different storage root) ---
        phone_b_dir = os.path.join(self.temp_dir, "phone_b_storage")
        phone_b_db = os.path.join(phone_b_dir, "library.db")
        phone_b_downloads = os.path.join(phone_b_dir, "downloads")
        os.makedirs(phone_b_downloads, exist_ok=True)
        init_db(phone_b_db)

        # Step 1: Phone B restores Part 1
        res1 = restore_backup_archive(zip_part1, downloads_dir=phone_b_downloads, db_path=phone_b_db)
        self.assertTrue(res1["success"])

        # Verify Phone B has exactly 1 series card and chapters from Part 1
        b_series = get_all_series(db_path=phone_b_db)
        self.assertEqual(len(b_series), 1)
        self.assertEqual(b_series[0]["title"], "Ultra Alter")
        b_s_id = b_series[0]["id"]
        chaps_step1 = get_chapters_for_series(b_s_id, db_path=phone_b_db)
        self.assertEqual(len(chaps_step1), 2)

        # Verify dynamic path remapping (points to Phone B downloads directory!)
        self.assertTrue(chaps_step1[0]["file_path"].startswith(phone_b_downloads))
        self.assertTrue(os.path.exists(chaps_step1[0]["file_path"]))

        # Step 2: Phone B restores Part 2
        res2 = restore_backup_archive(zip_part2, downloads_dir=phone_b_downloads, db_path=phone_b_db)
        self.assertTrue(res2["success"])

        # Critical Assertion: STILL only 1 series card (No duplicate cards created!)
        b_series_after = get_all_series(db_path=phone_b_db)
        self.assertEqual(len(b_series_after), 1)
        self.assertEqual(b_series_after[0]["id"], b_s_id)

        # Critical Assertion: All 3 chapters consolidated seamlessly!
        chaps_step2 = get_chapters_for_series(b_s_id, db_path=phone_b_db)
        self.assertEqual(len(chaps_step2), 3)

        # Check all 3 files exist on Phone B's disk
        for c in chaps_step2:
            self.assertTrue(os.path.exists(c["file_path"]))
            self.assertTrue(c["file_path"].startswith(phone_b_downloads))

    def test_export_and_restore_with_folders_and_notes(self):
        from database.db import create_folder, get_all_folders_with_items, get_folder_by_name
        # 1. Setup Source Library with Folders and Notes
        s1 = get_or_create_series("nano-machine", "Nano Machine", synopsis="A martial artist gets injected with nanobots.", db_path=self.db_path)
        s2 = get_or_create_series("legend-of-the-northern-blade", "Northern Blade", author="Hae-Min", db_path=self.db_path)
        f1 = self._create_mock_chapter_file("Nano_Machine", "ch1.cbz", 2048)
        add_or_update_chapter(s1, 1.0, title="Chapter 1", file_path=f1, file_size=2048, status="completed", db_path=self.db_path)

        folder_id = create_folder(
            name="Murim Top Tier",
            description="Best martial arts cultivation manhwa",
            color="#ec4899",
            series_ids=[s1, s2],
            db_path=self.db_path
        )

        # 2. Export Backup
        est = estimate_backup_batches(db_path=self.db_path)
        self.assertGreaterEqual(est["batch_count"], 1)

        out_zip = os.path.join(self.temp_dir, "v11_folder_backup.zip")
        create_backup_batch_file(
            batch_index=1,
            total_batches=1,
            batch_items=est["batches"][0]["items"],
            output_zip_path=out_zip,
            db_path=self.db_path
        )

        # 3. Inspect Archive Manifest
        inspection = inspect_backup_archive(out_zip)
        self.assertTrue(inspection["success"])
        manifest = inspection["manifest"]
        self.assertEqual(manifest.get("format_version"), "1.1")
        self.assertIn("folders", manifest)
        self.assertEqual(len(manifest["folders"]), 1)
        self.assertEqual(manifest["folders"][0]["name"], "Murim Top Tier")
        self.assertEqual(manifest["folders"][0]["description"], "Best martial arts cultivation manhwa")
        self.assertEqual(manifest["folders"][0]["color"], "#ec4899")
        self.assertIn("nano-machine", manifest["folders"][0]["series_slugs"])

        # 4. Restore into fresh Phone B target
        phone_b_dir = os.path.join(self.temp_dir, "phone_b_folder_storage")
        phone_b_db = os.path.join(phone_b_dir, "library.db")
        phone_b_downloads = os.path.join(phone_b_dir, "downloads")
        os.makedirs(phone_b_downloads, exist_ok=True)
        init_db(phone_b_db)

        res = restore_backup_archive(out_zip, downloads_dir=phone_b_downloads, db_path=phone_b_db)
        self.assertTrue(res["success"])
        self.assertEqual(res.get("folders_synced"), 1)

        # Verify Folder created in Phone B
        b_folders = get_all_folders_with_items(db_path=phone_b_db)
        self.assertEqual(len(b_folders), 1)
        self.assertEqual(b_folders[0]["name"], "Murim Top Tier")
        self.assertEqual(b_folders[0]["description"], "Best martial arts cultivation manhwa")
        self.assertEqual(b_folders[0]["color"], "#ec4899")
        self.assertIn(b_folders[0]["series_ids"][0], [1, 2])

        # 5. Idempotent Second Restore: Ensure no duplicates created!
        res_repeat = restore_backup_archive(out_zip, downloads_dir=phone_b_downloads, db_path=phone_b_db)
        self.assertTrue(res_repeat["success"])
        b_folders_after = get_all_folders_with_items(db_path=phone_b_db)
        self.assertEqual(len(b_folders_after), 1) # Still exactly 1 folder!

    def test_restore_legacy_v10_archive_compatibility(self):
        """Ensure an archive without 'folders' (created in older app versions) imports cleanly without crashing."""
        import io
        zip_buf = io.BytesIO()
        legacy_manifest = {
            "format_version": "1.0",
            "app_version": "1.0.0",
            "batch": {"is_batched": False, "batch_index": 1, "total_batches": 1, "batch_label": "Legacy"},
            "stats": {"series_count": 1, "chapter_count": 1, "uncompressed_bytes": 50},
            "series": [
                {
                    "title": "Legacy Classic Manga",
                    "slug": "legacy-classic-manga",
                    "author": "Old Author",
                    "status": "Completed",
                    "chapters": [
                        {
                            "chapter_num": 1.0,
                            "title": "Chapter 1",
                            "relative_path": "files/Legacy_Classic_Manga/ch1.cbz",
                            "file_format": "cbz",
                            "file_size": 50,
                            "panel_count": 10,
                            "read_status": 0,
                            "last_read_page": 0
                        }
                    ]
                }
            ]
        }
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            zf.writestr("manifest.json", json.dumps(legacy_manifest))
            zf.writestr("files/Legacy_Classic_Manga/ch1.cbz", b"A" * 50)

        legacy_zip = os.path.join(self.temp_dir, "legacy_v10.zip")
        with open(legacy_zip, "wb") as f:
            f.write(zip_buf.getvalue())

        dest_dir = os.path.join(self.temp_dir, "legacy_restore_downloads")
        os.makedirs(dest_dir, exist_ok=True)
        res = restore_backup_archive(legacy_zip, downloads_dir=dest_dir, db_path=self.db_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["chapters_imported"], 1)
        self.assertEqual(res["series_synced"], 1)
        self.assertEqual(res.get("folders_synced"), 0)


class TestBackupApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app import app
        cls.client = TestClient(app)

    def setUp(self):
        import app
        app.backup_state["is_running"] = False
        app.backup_state["status"] = "idle"

    def test_estimate_endpoint(self):
        response = self.client.get("/api/backup/estimate?batch_size_mb=1450")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("total_series", data)
        self.assertIn("total_chapters", data)
        self.assertIn("total_size_bytes", data)
        self.assertIn("batches_1_5gb", data)
        self.assertIn("batches", data)

    @patch("threading.Thread")
    def test_export_and_status_endpoints(self, mock_thread):
        # Trigger export
        payload = {
            "mode": "single",
            "batch_size_mb": 1450,
            "include_files": True
        }
        response = self.client.post("/api/backup/export", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("job_id", data)
        self.assertIn("batch_files", data)

        # Check status endpoint
        status_res = self.client.get("/api/backup/status")
        self.assertEqual(status_res.status_code, 200)
        s_data = status_res.json()
        self.assertTrue(s_data["success"])
        self.assertIn("status", s_data)
        self.assertIn("percent", s_data)

    def test_download_security_and_missing_file(self):
        # 1. Non-existent file -> 404
        res_404 = self.client.get("/api/backup/download/nonexistent_backup_9999.zip")
        self.assertEqual(res_404.status_code, 404)

        # 2. Path traversal attempt -> blocked with 400 or 404
        res_trav = self.client.get("/api/backup/download/%2E%2E%2Fetc%2Fpasswd")
        self.assertIn(res_trav.status_code, [400, 404])

        # 3. Non-zip extension -> 400
        res_ext = self.client.get("/api/backup/download/test.exe")
        self.assertEqual(res_ext.status_code, 400)

    def test_import_validation_and_rejection(self):
        # 1. Upload non-zip file -> 400
        files = {"file": ("malicious.txt", b"not a zip file", "text/plain")}
        res = self.client.post("/api/backup/import", files=files)
        self.assertEqual(res.status_code, 400)
        self.assertIn("must be a valid .zip", res.json()["error"])

        # 2. Upload corrupted zip -> 400
        corrupt_zip = {"file": ("corrupt.zip", b"PK\x03\x04corrupteddata", "application/zip")}
        res2 = self.client.post("/api/backup/import", files=corrupt_zip)
        self.assertEqual(res2.status_code, 400)
        self.assertIn("Invalid backup archive", res2.json()["error"])

    def test_import_valid_archive(self):
        import io
        from core.backup_engine import sanitize_filename

        # Construct a genuine minimal in-memory backup zip
        zip_buf = io.BytesIO()
        manifest = {
            "format_version": "1.0",
            "app_version": "1.0.4",
            "batch": {
                "is_batched": False,
                "batch_index": 1,
                "total_batches": 1,
                "batch_label": "Complete Library"
            },
            "stats": {
                "series_count": 1,
                "chapter_count": 1,
                "uncompressed_bytes": 100
            },
            "series": [
                {
                    "title": "API Test Series",
                    "slug": "api-test-series",
                    "author": "Tester",
                    "status": "Ongoing",
                    "chapters": [
                        {
                            "chapter_num": 1.0,
                            "chapter_slug": "chapter-1",
                            "title": "Chapter 1",
                            "relative_path": "files/API_Test_Series/ch1.cbz",
                            "file_format": "cbz",
                            "file_size": 100,
                            "panel_count": 5,
                            "read_status": 1,
                            "last_read_page": 3
                        }
                    ]
                }
            ]
        }
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("files/API_Test_Series/ch1.cbz", b"Z" * 100)

        zip_buf.seek(0)
        files = {"file": ("api_test_backup.zip", zip_buf.getvalue(), "application/zip")}
        res = self.client.post("/api/backup/import", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["chapters_imported"], 1)
        self.assertEqual(data["series_synced"], 1)

    def test_list_and_clear_cache(self):
        from app import BACKUPS_DIR
        test_file = os.path.join(BACKUPS_DIR, "test_cache_part1.zip")
        with open(test_file, "wb") as f:
            f.write(b"PK\x03\x04cachetest")

        list_res = self.client.get("/api/backup/list")
        self.assertEqual(list_res.status_code, 200)
        filenames = [f["filename"] for f in list_res.json()["files"]]
        self.assertIn("test_cache_part1.zip", filenames)

        clear_res = self.client.post("/api/backup/clear")
        self.assertEqual(clear_res.status_code, 200)
        self.assertGreaterEqual(clear_res.json()["purged_count"], 1)
        self.assertFalse(os.path.exists(test_file))


if __name__ == "__main__":
    unittest.main()

