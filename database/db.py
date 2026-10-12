import os
import re
import sqlite3
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any

DEFAULT_DB_PATH = os.environ.get("MANHUA_DB_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library.db")

def get_connection(db_path: str = None) -> sqlite3.Connection:
    target_path = db_path or os.environ.get("MANHUA_DB_PATH") or DEFAULT_DB_PATH
    conn = sqlite3.connect(target_path)
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_cache (
                query_hash TEXT PRIMARY KEY,
                query_string TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS series_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_id INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
                source_key TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                total_chapters INTEGER DEFAULT 0,
                latest_chapter_num REAL DEFAULT 0,
                quality_tag TEXT DEFAULT 'Standard',
                latency_ms INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(series_id, source_key)
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
        try:
            conn.execute("ALTER TABLE series ADD COLUMN mangadex_id TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE series ADD COLUMN genres TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE series ADD COLUMN tags TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE series ADD COLUMN year INTEGER")
        except sqlite3.OperationalError:
            pass

        # Deduplicate any existing duplicate series records sharing the same normalized title
        try:
            dup_rows = conn.execute("""
                SELECT lower(trim(title)) as norm_title, COUNT(*) as cnt
                FROM series
                WHERE title IS NOT NULL AND lower(trim(title)) != 'unknown series'
                GROUP BY lower(trim(title))
                HAVING cnt > 1
            """).fetchall()

            for dup in dup_rows:
                norm_title = dup["norm_title"]
                series_records = conn.execute("""
                    SELECT id FROM series
                    WHERE lower(trim(title)) = ?
                    ORDER BY id ASC
                """, (norm_title,)).fetchall()
                if len(series_records) > 1:
                    primary_id = series_records[0]["id"]
                    other_ids = [r["id"] for r in series_records[1:]]
                    placeholders = ",".join("?" for _ in other_ids)
                    conn.execute(f"""
                        UPDATE OR IGNORE chapters
                        SET series_id = ?
                        WHERE series_id IN ({placeholders})
                    """, [primary_id] + other_ids)
                    conn.execute(f"""
                        DELETE FROM chapters
                        WHERE series_id IN ({placeholders})
                    """, other_ids)
                    conn.execute(f"""
                        DELETE FROM series
                        WHERE id IN ({placeholders})
                    """, other_ids)
        except Exception:
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
    clean_title = (title or "").strip()
    clean_slug = (slug or "").strip().lower()

    # If slug looks like a chapter number or unknown, derive from clean_title if available
    is_chapter_slug = bool(clean_slug and (clean_slug.startswith("ch") or clean_slug.isdigit() or re.search(r'^(?:ch(?:apter)?|ep(?:isode)?)[-_.]?\d+|^\d+(?:\.\d+)?$', clean_slug, re.I)))
    if (is_chapter_slug or not clean_slug or clean_slug == "unknown-series") and clean_title and clean_title.lower() != "unknown series":
        clean_slug = re.sub(r'[^a-z0-9]+', '-', clean_title.lower()).strip('-')

    try:
        with conn:
            row = None
            # 1. Match by slug
            if clean_slug and clean_slug != "unknown-series":
                row = conn.execute("SELECT id FROM series WHERE slug = ?", (clean_slug,)).fetchone()

            # 2. Match by exact/case-insensitive title
            if not row and clean_title and clean_title.lower() != "unknown series":
                row = conn.execute("SELECT id FROM series WHERE lower(trim(title)) = lower(trim(?))", (clean_title,)).fetchone()

            # 3. Match by normalized title slug
            if not row and clean_title and clean_title.lower() != "unknown series":
                title_slug = re.sub(r'[^a-z0-9]+', '-', clean_title.lower()).strip('-')
                if title_slug:
                    row = conn.execute("SELECT id FROM series WHERE slug = ?", (title_slug,)).fetchone()

            if row:
                series_id = row["id"]
                conn.execute("""
                    UPDATE series 
                    SET title = coalesce(nullif(?, ''), title),
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
            """, (clean_slug or slug, title, alt_titles, author, status, synopsis, cover_url, source_url, engine))
            return cursor.lastrowid
    finally:
        conn.close()

def update_series_cover(series_id: int, cover_path: str, cover_url: Optional[str] = None, db_path: str = DEFAULT_DB_PATH) -> bool:
    """Update series record with locally downloaded cover image path."""
    conn = get_connection(db_path)
    with conn:
        conn.execute("""
            UPDATE series
            SET cover_path = ?,
                cover_url = coalesce(?, cover_url),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (cover_path, cover_url, series_id))
    conn.close()
    return True

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
        conn.execute("DELETE FROM chapters WHERE series_id = ?", (series_id,))
        cursor = conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
    conn.close()
    return cursor.rowcount > 0

def delete_chapter(chapter_id: int, db_path: str = DEFAULT_DB_PATH) -> bool:
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
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
    try:
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
    finally:
        conn.close()

def get_chapters_for_series(series_id: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM chapters WHERE series_id = ? ORDER BY chapter_num ASC",
        (series_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_downloaded_chapters_map(series_title: str, db_path: str = DEFAULT_DB_PATH) -> Dict[float, Dict[str, Any]]:
    """Return dictionary mapping chapter_num to local chapter record for quick O(1) status lookup."""
    conn = get_connection(db_path)
    series = conn.execute(
        "SELECT id FROM series WHERE title = ? OR slug = ?",
        (series_title, series_title.lower().replace(' ', '-'))
    ).fetchone()
    if not series:
        conn.close()
        return {}
    rows = conn.execute(
        "SELECT * FROM chapters WHERE series_id = ? AND status = 'completed'",
        (series["id"],)
    ).fetchall()
    conn.close()
    return {row["chapter_num"]: dict(row) for row in rows}


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


def update_series_rich_metadata(
    series_id: int,
    metadata: Dict[str, Any],
    db_path: str = DEFAULT_DB_PATH
) -> None:
    conn = get_connection(db_path)
    genres_str = ", ".join(metadata.get("genres") or []) if isinstance(metadata.get("genres"), list) else metadata.get("genres")
    tags_str = ", ".join(metadata.get("tags") or []) if isinstance(metadata.get("tags"), list) else metadata.get("tags")
    with conn:
        conn.execute("""
            UPDATE series
            SET author = COALESCE(?, author),
                artist = COALESCE(?, artist),
                synopsis = COALESCE(?, synopsis),
                genres = COALESCE(?, genres),
                tags = COALESCE(?, tags),
                year = COALESCE(?, year),
                status = COALESCE(?, status),
                mangadex_id = COALESCE(?, mangadex_id),
                anilist_id = COALESCE(?, anilist_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            metadata.get("author"),
            metadata.get("artist"),
            metadata.get("synopsis"),
            genres_str,
            tags_str,
            metadata.get("year"),
            metadata.get("status"),
            metadata.get("mangadex_id"),
            metadata.get("anilist_id"),
            series_id
        ))
    conn.close()


def get_cached_search(query: str, db_path: str = DEFAULT_DB_PATH) -> Optional[List[Dict[str, Any]]]:
    """Retrieve non-expired search results from the search_cache table."""
    norm_query = query.strip().lower()
    q_hash = hashlib.sha256(norm_query.encode("utf-8")).hexdigest()
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT results_json FROM search_cache WHERE query_hash = ? AND expires_at > CURRENT_TIMESTAMP",
            (q_hash,)
        ).fetchone()
        if row and row["results_json"]:
            return json.loads(row["results_json"])
        return None
    except Exception:
        return None
    finally:
        conn.close()


def set_cached_search(query: str, results: List[Dict[str, Any]], ttl_seconds: int = 1800, db_path: str = DEFAULT_DB_PATH) -> None:
    """Store search results into the search_cache table with a TTL."""
    norm_query = query.strip().lower()
    q_hash = hashlib.sha256(norm_query.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    expires_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
    results_json = json.dumps(results)
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO search_cache (query_hash, query_string, results_json, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(query_hash) DO UPDATE SET
                    results_json = excluded.results_json,
                    expires_at = excluded.expires_at,
                    created_at = CURRENT_TIMESTAMP
            """, (q_hash, norm_query, results_json, expires_str))
    except Exception:
        pass
    finally:
        conn.close()


def add_or_update_series_source(
    series_id: int,
    source_key: str,
    source_name: str,
    source_url: str,
    total_chapters: int = 0,
    latest_chapter_num: float = 0.0,
    quality_tag: str = "Standard",
    latency_ms: int = 0,
    db_path: str = DEFAULT_DB_PATH
) -> None:
    """Register or update an external hosting source for a series."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO series_sources (
                    series_id, source_key, source_name, source_url,
                    total_chapters, latest_chapter_num, quality_tag, latency_ms, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(series_id, source_key) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_url = excluded.source_url,
                    total_chapters = MAX(series_sources.total_chapters, excluded.total_chapters),
                    latest_chapter_num = MAX(series_sources.latest_chapter_num, excluded.latest_chapter_num),
                    quality_tag = excluded.quality_tag,
                    latency_ms = excluded.latency_ms,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                series_id, source_key, source_name, source_url,
                total_chapters, latest_chapter_num, quality_tag, latency_ms
            ))
    finally:
        conn.close()


def get_series_sources(series_id: int, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Retrieve all recorded sources for a series."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM series_sources WHERE series_id = ? ORDER BY latest_chapter_num DESC, latency_ms ASC",
            (series_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()



