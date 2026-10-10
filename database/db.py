import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Any

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library.db")

def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize SQLite database schemas for series, chapters, downloads, and site diagnostics."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS series (
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL,
                chapter_num REAL NOT NULL,
                chapter_slug TEXT,
                title TEXT,
                source_url TEXT,
                panel_count INTEGER DEFAULT 0,
                file_path TEXT,
                file_format TEXT,
                file_size INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending', -- pending, downloading, completed, failed
                read_status INTEGER DEFAULT 0,  -- 0: unread, 1: reading, 2: completed
                last_read_page INTEGER DEFAULT 0,
                downloaded_at TIMESTAMP,
                FOREIGN KEY (series_id) REFERENCES series(id) ON DELETE CASCADE,
                UNIQUE (series_id, chapter_num)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS site_diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                domain TEXT NOT NULL,
                engine_detected TEXT,
                status TEXT NOT NULL, -- PASS, PARTIAL, BLOCKED, FAILED
                panels_found INTEGER DEFAULT 0,
                next_chapter_found INTEGER DEFAULT 0,
                protection TEXT,
                last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS promo_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT,
                phash TEXT UNIQUE NOT NULL,
                match_threshold INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration columns for series table
        try:
            conn.execute("ALTER TABLE series ADD COLUMN anilist_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE series ADD COLUMN mal_id INTEGER")
        except sqlite3.OperationalError:
            pass
    conn.close()

# --- Series Operations ---

def get_or_create_series(
    slug: str,
    title: str,
    alt_titles: Optional[str] = None,
    author: Optional[str] = None,
    status: str = "Ongoing",
    synopsis: Optional[str] = None,
    cover_url: Optional[str] = None,
    source_url: Optional[str] = None,
    engine: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> int:
    conn = get_connection(db_path)
    with conn:
        row = conn.execute("SELECT id FROM series WHERE slug = ?", (slug,)).fetchone()
        if row:
            series_id = row["id"]
            conn.execute("""
                UPDATE series 
                SET title = coalesce(?, title),
                    cover_url = coalesce(?, cover_url),
                    source_url = coalesce(?, source_url),
                    engine = coalesce(?, engine),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (title, cover_url, source_url, engine, series_id))
            return series_id

        cursor = conn.execute("""
            INSERT INTO series (slug, title, alt_titles, author, status, synopsis, cover_url, source_url, engine)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (slug, title, alt_titles, author, status, synopsis, cover_url, source_url, engine))
        return cursor.lastrowid

def get_all_series(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT s.*, 
               COUNT(c.id) as total_chapters,
               SUM(CASE WHEN c.status = 'completed' THEN 1 ELSE 0 END) as downloaded_chapters
        FROM series s
        LEFT JOIN chapters c ON s.id = c.series_id
        GROUP BY s.id
        ORDER BY s.updated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_series_by_id(series_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def delete_series(series_id: int, db_path: str = DEFAULT_DB_PATH) -> bool:
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
    conn.close()
    return cursor.rowcount > 0

# --- Chapter Operations ---

def add_or_update_chapter(
    series_id: int,
    chapter_num: float,
    chapter_slug: Optional[str] = None,
    title: Optional[str] = None,
    source_url: Optional[str] = None,
    panel_count: int = 0,
    file_path: Optional[str] = None,
    file_format: Optional[str] = None,
    file_size: int = 0,
    status: str = "pending",
    db_path: str = DEFAULT_DB_PATH
) -> int:
    conn = get_connection(db_path)
    with conn:
        row = conn.execute(
            "SELECT id FROM chapters WHERE series_id = ? AND chapter_num = ?",
            (series_id, chapter_num)
        ).fetchone()

        if row:
            chap_id = row["id"]
            conn.execute("""
                UPDATE chapters 
                SET chapter_slug = coalesce(?, chapter_slug),
                    title = coalesce(?, title),
                    source_url = coalesce(?, source_url),
                    panel_count = CASE WHEN ? > 0 THEN ? ELSE panel_count END,
                    file_path = coalesce(?, file_path),
                    file_format = coalesce(?, file_format),
                    file_size = CASE WHEN ? > 0 THEN ? ELSE file_size END,
                    status = coalesce(?, status),
                    downloaded_at = CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE downloaded_at END
                WHERE id = ?
            """, (chapter_slug, title, source_url, panel_count, panel_count, file_path, file_format, file_size, file_size, status, status, chap_id))
            return chap_id

        cursor = conn.execute("""
            INSERT INTO chapters (series_id, chapter_num, chapter_slug, title, source_url, panel_count, file_path, file_format, file_size, status, downloaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'completed' THEN CURRENT_TIMESTAMP ELSE NULL END)
        """, (series_id, chapter_num, chapter_slug, title, source_url, panel_count, file_path, file_format, file_size, status, status))
        return cursor.lastrowid

def get_chapters_for_series(series_id: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM chapters WHERE series_id = ? ORDER BY chapter_num ASC",
        (series_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_chapter_by_id(chapter_id: int, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_reading_progress(chapter_id: int, read_status: int, last_read_page: int, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            "UPDATE chapters SET read_status = ?, last_read_page = ? WHERE id = ?",
            (read_status, last_read_page, chapter_id)
        )
    conn.close()

# --- Site Diagnostics Operations ---

def record_site_diagnostic(
    url: str,
    domain: str,
    engine_detected: str,
    status: str,
    panels_found: int = 0,
    next_chapter_found: int = 0,
    protection: Optional[str] = None,
    notes: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH
) -> int:
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("""
            INSERT INTO site_diagnostics (url, domain, engine_detected, status, panels_found, next_chapter_found, protection, notes, last_checked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(url) DO UPDATE SET
                engine_detected = excluded.engine_detected,
                status = excluded.status,
                panels_found = excluded.panels_found,
                next_chapter_found = excluded.next_chapter_found,
                protection = excluded.protection,
                notes = excluded.notes,
                last_checked = CURRENT_TIMESTAMP
        """, (url, domain, engine_detected, status, panels_found, next_chapter_found, protection, notes))
        return cursor.lastrowid

def get_all_site_diagnostics(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM site_diagnostics ORDER BY last_checked DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- App Settings Operations ---

def get_setting(key: str, default: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> Optional[str]:
    conn = get_connection(db_path)
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str, db_path: str = DEFAULT_DB_PATH) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))
    conn.close()

def get_all_settings(db_path: str = DEFAULT_DB_PATH) -> Dict[str, str]:
    conn = get_connection(db_path)
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# --- Promotional Signatures Operations ---

def add_promo_signature(
    phash: str,
    label: str = "Promo",
    match_threshold: int = 10,
    db_path: str = DEFAULT_DB_PATH
) -> int:
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("""
            INSERT INTO promo_signatures (phash, label, match_threshold)
            VALUES (?, ?, ?)
            ON CONFLICT(phash) DO UPDATE SET label = excluded.label, match_threshold = excluded.match_threshold
        """, (phash, label, match_threshold))
        sig_id = cursor.lastrowid
    conn.close()
    return sig_id


def get_all_promo_signatures(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM promo_signatures ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_promo_signature(signature_id: int, db_path: str = DEFAULT_DB_PATH) -> bool:
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("DELETE FROM promo_signatures WHERE id = ?", (signature_id,))
        deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def update_series_trackers(
    series_id: int,
    anilist_id: Optional[int] = None,
    mal_id: Optional[int] = None,
    db_path: str = DEFAULT_DB_PATH
) -> None:
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            UPDATE series
            SET anilist_id = COALESCE(?, anilist_id),
                mal_id = COALESCE(?, mal_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (anilist_id, mal_id, series_id))
    conn.close()


