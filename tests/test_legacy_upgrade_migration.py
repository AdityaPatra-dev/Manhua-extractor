import os
import sqlite3
import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from database.db import (
    init_db,
    get_all_series,
    get_series_by_id,
    add_or_update_chapter,
    update_reading_progress,
    is_series_updatable,
    _calc_release_schedule
)


class TestLegacyUpgradeMigration(unittest.TestCase):
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

            # 2. Insert an existing completed static manga (e.g. Hitomi)
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

        conn.close()

    def test_upgrade_from_legacy_version_runs_cleanly(self):
        """Test that updating an older version database runs flawlessly without data corruption or errors."""
        self.create_v1_0_legacy_database()

        # Execute init_db which runs all schema migrations and legacy data migration
        init_db(self.db_path)

        # 1. Verify schema was upgraded without losing any data
        series = get_all_series(self.db_path)
        self.assertEqual(len(series), 3)

        # 2. Verify Nano Machine (Ongoing Manhua)
        nano = next(s for s in series if s["id"] == 1)
        self.assertTrue(nano["updatable"])
        self.assertEqual(nano["auto_update"], 1)
        self.assertEqual(nano["downloaded_chapters"], 3)
        # Old completed chapters established a clean baseline (no false red dot)
        self.assertFalse(nano["has_unread"])
        self.assertEqual(nano["unread_count"], 0)
        # Downloaded_at was backfilled from file mtime (4 days ago) -> next expected in ~3d
        self.assertIsNotNone(nano["latest_downloaded_at"])
        self.assertIn("in 3d", nano["next_expected_desc"])
        self.assertEqual(nano["next_expected_short"], "In 3d")

        # 3. Verify Hitomi Gallery (Static manga website)
        hitomi = next(s for s in series if s["id"] == 2)
        # Static source is automatically excluded from updates
        self.assertFalse(hitomi["updatable"])
        self.assertIn("Static manga", hitomi["updatable_reason"])
        self.assertEqual(hitomi["next_expected_desc"], "Static Archive (Single Release)")
        self.assertEqual(hitomi["next_expected_short"], "Static")

        # 4. Verify Solo Leveling (Completed Series)
        solo = next(s for s in series if s["id"] == 3)
        self.assertFalse(solo["updatable"])
        self.assertEqual(solo["updatable_reason"], "Series status is Completed")
        self.assertEqual(solo["next_expected_desc"], "Series Completed")
        self.assertEqual(solo["next_expected_short"], "Completed")

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
        # Downloaded today -> expected in ~7 days
        self.assertIn("in 7d", nano_after_dl["next_expected_desc"])

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
