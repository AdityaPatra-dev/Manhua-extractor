import os
import sqlite3
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from database.db import (
    init_db,
    get_all_series,
    get_series_by_id,
    get_or_create_series,
    add_or_update_chapter,
    update_reading_progress,
    is_series_updatable,
    _calc_release_schedule
)
from core.updater import run_library_update, check_and_enqueue_series_update


class TestLegacyUpgradeMigration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "legacy_user.db")
        self.downloads_dir = os.path.join(self.temp_dir, "downloads")
        os.makedirs(self.downloads_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_v1_0_legacy_database(self):
        """Simulate an old v1.0 / v1.1 database schema before auto_update, downloaded_at, and read_status."""
        conn = sqlite3.connect(self.db_path)
        with conn:
            # Old series table without auto_update, sort_order, tags, genres, etc.
            conn.execute("""
                CREATE TABLE series (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    alt_titles TEXT,
                    author TEXT,
                    artist TEXT,
                    status TEXT DEFAULT 'Ongoing',
                    synopsis TEXT,
                    cover_url TEXT,
                    cover_path TEXT,
                    source_url TEXT,
                    engine TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Old chapters table without read_status, last_read_page, downloaded_at
            conn.execute("""
                CREATE TABLE chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_id INTEGER NOT NULL,
                    chapter_num REAL NOT NULL,
                    chapter_slug TEXT,
                    title TEXT,
                    source_url TEXT,
                    panel_count INTEGER DEFAULT 20,
                    file_path TEXT,
                    file_format TEXT,
                    file_size INTEGER DEFAULT 1024,
                    status TEXT DEFAULT 'completed',
                    FOREIGN KEY (series_id) REFERENCES series(id),
                    UNIQUE (series_id, chapter_num)
                )
            """)

            conn.execute("""
                CREATE TABLE settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # 1. Insert an existing ongoing manhua with 3 downloaded chapters
            conn.execute("""
                INSERT INTO series (id, slug, title, status, source_url, engine)
                VALUES (1, 'nano-machine', 'Nano Machine', 'Ongoing', 'https://asuracomic.net/manga/nano-machine', 'asurascans')
            """)

            # Create dummy downloaded files with an mtime 4 days ago
            four_days_ago = (datetime.now(timezone.utc) - timedelta(days=4)).timestamp()

            for c_num in [1.0, 2.0, 3.0]:
                fp = os.path.join(self.downloads_dir, f"nano_ch_{int(c_num)}.pdf")
                with open(fp, "w") as f:
                    f.write("dummy pdf content")
                os.utime(fp, (four_days_ago, four_days_ago))

                conn.execute("""
                    INSERT INTO chapters (series_id, chapter_num, title, file_path, file_format, status)
                    VALUES (1, ?, ?, ?, 'pdf', 'completed')
                """, (c_num, f"Chapter {int(c_num)}", fp))

            # 2. Insert an existing completed static manga (Hitomi)
            conn.execute("""
                INSERT INTO series (id, slug, title, status, source_url, engine)
                VALUES (2, 'hitomi-gallery', 'Hitomi Gallery One-Shot', 'Ongoing', 'https://hitomi.la/doujinshi/12345.html', 'hitomi')
            """)
            fp_static = os.path.join(self.downloads_dir, "hitomi_oneshot.pdf")
            with open(fp_static, "w") as f:
                f.write("dummy hitomi")
            conn.execute("""
                INSERT INTO chapters (series_id, chapter_num, title, file_path, file_format, status)
                VALUES (2, 1.0, 'One Shot', ?, 'pdf', 'completed')
            """, (fp_static,))

            # 3. Insert an existing finished manga
            conn.execute("""
                INSERT INTO series (id, slug, title, status, source_url, engine)
                VALUES (3, 'solo-leveling', 'Solo Leveling', 'Completed', 'https://asuracomic.net/manga/solo-leveling', 'asurascans')
            """)
            conn.execute("""
                INSERT INTO chapters (series_id, chapter_num, title, file_path, file_format, status)
                VALUES (3, 1.0, 'Chapter 1', NULL, 'pdf', 'completed')
            """)

            # 4. Insert an old legacy series where series source_url and engine were MISSING/AUTO, but chapter came from Hitomi
            conn.execute("""
                INSERT INTO series (id, slug, title, status, source_url, engine)
                VALUES (4, 'old-doujinshi-work', 'Old Doujinshi Work', 'Ongoing', NULL, 'auto')
            """)
            conn.execute("""
                INSERT INTO chapters (series_id, chapter_num, title, source_url, status)
                VALUES (4, 1.0, 'One Shot', 'https://hitomi.la/reader/99999.html', 'completed')
            """)

            # 5. Insert an old legacy series with slug 'hentaifox-777' without engine
            conn.execute("""
                INSERT INTO series (id, slug, title, status, source_url, engine)
                VALUES (5, 'hentaifox-777', 'HentaiFox Work', 'Ongoing', NULL, 'auto')
            """)

        conn.close()

    async def test_upgrade_from_legacy_version_excludes_all_old_static_manga_data(self):
        """Test that updating an older version database runs flawlessly and completely excludes all old static manga data."""
        self.create_v1_0_legacy_database()

        # Execute init_db which runs all schema migrations and legacy data migration
        init_db(self.db_path)

        # 1. Verify schema was upgraded without losing any data
        series = get_all_series(self.db_path)
        self.assertEqual(len(series), 5)

        # 2. Verify Nano Machine (Ongoing Manhua) -> ONLY ONE UP-TO-DATE AND UPDATABLE
        nano = next(s for s in series if s["id"] == 1)
        self.assertTrue(nano["updatable"])
        self.assertEqual(nano["auto_update"], 1)
        self.assertEqual(nano["downloaded_chapters"], 3)
        self.assertFalse(nano["has_unread"])
        self.assertIn("in 3d", nano["next_expected_desc"])

        # 3. Verify Hitomi Gallery (Static manga by source_url & engine) -> EXCLUDED
        hitomi = next(s for s in series if s["id"] == 2)
        self.assertFalse(hitomi["updatable"])
        self.assertEqual(hitomi["auto_update"], 0)
        self.assertIn("Static manga", hitomi["updatable_reason"])
        self.assertEqual(hitomi["next_expected_short"], "Static")

        # 4. Verify Solo Leveling (Completed Series) -> EXCLUDED
        solo = next(s for s in series if s["id"] == 3)
        self.assertFalse(solo["updatable"])
        self.assertEqual(solo["auto_update"], 0)
        self.assertEqual(solo["updatable_reason"], "Series status is Completed")

        # 5. Verify Old Doujinshi Work (Missing series source_url, but chapter source_url was hitomi.la) -> EXCLUDED
        old_hitomi = next(s for s in series if s["id"] == 4)
        self.assertFalse(old_hitomi["updatable"])
        self.assertEqual(old_hitomi["auto_update"], 0)
        self.assertIn("Static manga", old_hitomi["updatable_reason"])

        # 6. Verify HentaiFox Work (Slug pattern match) -> EXCLUDED
        hfox = next(s for s in series if s["id"] == 5)
        self.assertFalse(hfox["updatable"])
        self.assertEqual(hfox["auto_update"], 0)
        self.assertIn("Static manga", hfox["updatable_reason"])

        # 7. Test run_library_update with this database:
        # It must ONLY check Nano Machine (id 1) and SKIP all 4 other series!
        with patch("core.updater.get_all_series", return_value=series), \
             patch("core.updater.check_and_enqueue_series_update") as mock_check:
            mock_check.return_value = {"queued": False, "success": True, "series_id": 1, "series_title": "Nano Machine", "new_chapters": []}
            mock_queue = MagicMock()
            res = await run_library_update(queue_manager=mock_queue)
            
            self.assertEqual(res["total_series"], 5)
            self.assertEqual(res["checked_series_count"], 1)  # Only Nano Machine!
            self.assertEqual(res["skipped_series_count"], 4)  # All 4 static / completed titles excluded!
            
            # Verify mock_check was ONLY called for Nano Machine, NEVER for Hitomi / HentaiFox / etc.
            mock_check.assert_called_once()
            args, kwargs = mock_check.call_args
            self.assertEqual(kwargs["series_id"], 1)

    def test_moving_forward_new_chapters_trigger_red_dot_and_clear_on_read(self):
        """Test that moving forward after migration, newly downloaded chapters trigger unread badges and clear upon reading."""
        self.create_v1_0_legacy_database()
        init_db(self.db_path)

        # Before new download: Nano Machine has no unread red dot
        nano_before = get_series_by_id(1, db_path=self.db_path)
        self.assertFalse(nano_before["has_unread"])

        # MOVING FORWARD: A new chapter (Chapter 4.0) is downloaded
        new_ch_id = add_or_update_chapter(
            series_id=1,
            chapter_num=4.0,
            title="Chapter 4",
            status="completed",
            db_path=self.db_path
        )

        # Verify: Red dot is NOW active for this series!
        nano_after_dl = get_series_by_id(1, db_path=self.db_path)
        self.assertTrue(nano_after_dl["has_unread"])
        self.assertEqual(nano_after_dl["unread_count"], 1)
        self.assertEqual(nano_after_dl["latest_downloaded_chapter_num"], 4.0)

        # User starts reading Chapter 4 (page 5 of 20) -> still unread dot active
        update_reading_progress(new_ch_id, read_status=1, last_read_page=5, db_path=self.db_path)
        nano_reading = get_series_by_id(1, db_path=self.db_path)
        self.assertTrue(nano_reading["has_unread"])

        # User completes Chapter 4 (read_status = 2) -> Red dot turns OFF!
        update_reading_progress(new_ch_id, read_status=2, last_read_page=20, db_path=self.db_path)
        nano_finished = get_series_by_id(1, db_path=self.db_path)
        self.assertFalse(nano_finished["has_unread"])
        self.assertEqual(nano_finished["unread_count"], 0)


if __name__ == "__main__":
    unittest.main()
