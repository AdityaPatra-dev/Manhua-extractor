import os
import re
import json
import shutil
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable, Tuple

from database.db import (
    DEFAULT_DB_PATH,
    get_connection,
    get_all_series,
    get_chapters_for_series,
    get_or_create_series,
    add_or_update_chapter,
    update_series_cover,
    get_series_by_id
)

DEFAULT_BATCH_SIZE_BYTES = 1450 * 1024 * 1024  # 1.45 GB soft ceiling
CHUNK_SIZE = 64 * 1024  # 64 KB streaming buffer


def format_bytes(num_bytes: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"


def sanitize_filename(name: str) -> str:
    """Remove unsafe filesystem characters for directory or file naming."""
    clean = re.sub(r'[\\/*?:"<>|]', '_', name or '').strip()
    return clean or "series"


def calculate_chapter_disk_size(file_path: Optional[str]) -> int:
    """Accurately calculates disk size of a chapter (whether single archive or folder)."""
    if not file_path or not os.path.exists(file_path):
        return 0
    try:
        if os.path.isfile(file_path):
            return os.path.getsize(file_path)
        elif os.path.isdir(file_path):
            total = 0
            for root, _, files in os.walk(file_path):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        total += os.path.getsize(fp)
            return total
    except Exception:
        return 0
    return 0


def estimate_backup_batches(
    db_path: str = DEFAULT_DB_PATH,
    target_batch_bytes: int = DEFAULT_BATCH_SIZE_BYTES
) -> Dict[str, Any]:
    """
    Scans the local database and filesystem, bin-packing all downloaded chapters
    into self-contained batches of approximately target_batch_bytes (default 1.45 GB).
    """
    all_series = get_all_series(db_path=db_path)
    total_chapters_count = 0
    total_size_bytes = 0

    all_downloaded_items: List[Dict[str, Any]] = []

    for s in all_series:
        s_id = s["id"]
        chapters = get_chapters_for_series(s_id, db_path=db_path)
        for c in chapters:
            fp = c.get("file_path")
            if fp and os.path.exists(fp) and c.get("status") == "completed":
                size = calculate_chapter_disk_size(fp)
                if size > 0:
                    total_chapters_count += 1
                    total_size_bytes += size
                    all_downloaded_items.append({
                        "series_id": s_id,
                        "series_title": s["title"],
                        "series_slug": s.get("slug") or sanitize_filename(s["title"]),
                        "series_author": s.get("author"),
                        "series_status": s.get("status", "Ongoing"),
                        "series_cover_path": s.get("cover_path"),
                        "series_cover_url": s.get("cover_url"),
                        "series_engine": s.get("engine"),
                        "chapter_id": c["id"],
                        "chapter_num": c["chapter_num"],
                        "chapter_slug": c.get("chapter_slug"),
                        "chapter_title": c.get("title") or f"Chapter {c['chapter_num']}",
                        "file_path": fp,
                        "file_format": c.get("file_format") or ("pdf" if fp.endswith(".pdf") else "cbz"),
                        "file_size": size,
                        "panel_count": c.get("panel_count", 0),
                        "read_status": c.get("read_status", 0),
                        "last_read_page": c.get("last_read_page", 0)
                    })

    if not all_downloaded_items:
        return {
            "total_series": len(all_series),
            "total_chapters": 0,
            "total_size_bytes": 0,
            "total_size_formatted": "0 B",
            "batch_count": 0,
            "batches": []
        }

    # Bin-packing into batches
    batches: List[Dict[str, Any]] = []
    current_batch_items: List[Dict[str, Any]] = []
    current_batch_bytes = 0

    for item in all_downloaded_items:
        item_size = item["file_size"]
        # If adding this item exceeds target and current batch isn't empty, flush current batch
        if (current_batch_bytes + item_size > target_batch_bytes) and current_batch_items:
            batches.append({
                "batch_index": len(batches) + 1,
                "chapter_count": len(current_batch_items),
                "uncompressed_bytes": current_batch_bytes,
                "uncompressed_formatted": format_bytes(current_batch_bytes),
                "items": current_batch_items
            })
            current_batch_items = []
            current_batch_bytes = 0

        current_batch_items.append(item)
        current_batch_bytes += item_size

    if current_batch_items:
        batches.append({
            "batch_index": len(batches) + 1,
            "chapter_count": len(current_batch_items),
            "uncompressed_bytes": current_batch_bytes,
            "uncompressed_formatted": format_bytes(current_batch_bytes),
            "items": current_batch_items
        })

    # Update total_batches and labels in each batch
    total_b = len(batches)
    for b in batches:
        b["total_batches"] = total_b
        b["batch_label"] = f"Part {b['batch_index']} of {total_b}" if total_b > 1 else "Complete Library"
        b["formatted_size"] = b.get("uncompressed_formatted", format_bytes(b.get("uncompressed_bytes", 0)))

    # Unique series count in backup
    unique_series = {it["series_id"] for it in all_downloaded_items}

    return {
        "total_series": len(unique_series),
        "total_chapters": total_chapters_count,
        "total_size_bytes": total_size_bytes,
        "total_size_formatted": format_bytes(total_size_bytes),
        "batch_count": total_b,
        "batches": batches
    }


def create_backup_batch_file(
    batch_index: int,
    total_batches: int,
    batch_items: List[Dict[str, Any]],
    output_zip_path: str,
    include_files: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[str, Any]:
    """
    Creates a standalone, self-contained backup ZIP archive for a specific batch.
    Includes manifest.json, series definitions, covers, and chapter archives.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_zip_path)), exist_ok=True)
    temp_zip_path = f"{output_zip_path}.tmp_{os.getpid()}"

    # Group items by series to construct clean manifest
    series_map: Dict[int, Dict[str, Any]] = {}
    total_items = len(batch_items)

    for it in batch_items:
        s_id = it["series_id"]
        if s_id not in series_map:
            safe_s_title = sanitize_filename(it["series_title"])
            series_map[s_id] = {
                "id": s_id,
                "title": it["series_title"],
                "slug": it["series_slug"],
                "author": it.get("series_author"),
                "status": it.get("series_status", "Ongoing"),
                "engine": it.get("series_engine"),
                "cover_url": it.get("series_cover_url"),
                "cover_path_local": it.get("series_cover_path"),
                "cover_relative_path": f"files/{safe_s_title}/cover.jpg" if (it.get("series_cover_path") and os.path.exists(it.get("series_cover_path"))) else None,
                "chapters": []
            }
        
        safe_s_title = sanitize_filename(it["series_title"])
        filename = os.path.basename(it["file_path"].rstrip('/\\'))
        rel_path = f"files/{safe_s_title}/{filename}"

        series_map[s_id]["chapters"].append({
            "chapter_num": it["chapter_num"],
            "chapter_slug": it.get("chapter_slug"),
            "title": it["chapter_title"],
            "relative_path": rel_path,
            "file_format": it["file_format"],
            "file_size": it["file_size"],
            "panel_count": it["panel_count"],
            "read_status": it["read_status"],
            "last_read_page": it["last_read_page"],
            "_source_file_path": it["file_path"]
        })

    manifest = {
        "format_version": "1.0",
        "app_version": "1.1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "batch": {
            "is_batched": total_batches > 1,
            "batch_index": batch_index,
            "total_batches": total_batches,
            "batch_label": f"Part {batch_index} of {total_batches}" if total_batches > 1 else "Complete Library"
        },
        "stats": {
            "series_count": len(series_map),
            "chapter_count": total_items,
            "uncompressed_bytes": sum(it["file_size"] for it in batch_items)
        },
        "series": []
    }

    # Clean internal source paths before writing manifest
    for s in series_map.values():
        cleaned_chaps = []
        for ch in s["chapters"]:
            ch_copy = dict(ch)
            ch_copy.pop("_source_file_path", None)
            cleaned_chaps.append(ch_copy)
        s_entry = dict(s)
        s_entry["chapters"] = cleaned_chaps
        s_entry.pop("cover_path_local", None)
        manifest["series"].append(s_entry)

    # Write ZIP stream with ZIP64 enabled
    processed_count = 0
    with zipfile.ZipFile(temp_zip_path, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        # 1. Write manifest.json
        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode('utf-8')
        zf.writestr("manifest.json", manifest_bytes)

        # 2. Write series covers (self-contained for every referenced series)
        for s in series_map.values():
            cov_local = s.get("cover_path_local")
            cov_rel = s.get("cover_relative_path")
            if cov_local and cov_rel and os.path.exists(cov_local) and os.path.isfile(cov_local):
                try:
                    zf.write(cov_local, arcname=cov_rel)
                except Exception:
                    pass

        # 3. Write chapter files
        if include_files:
            for s in series_map.values():
                for ch in s["chapters"]:
                    src_path = ch["_source_file_path"]
                    rel_path = ch["relative_path"]
                    if progress_callback:
                        progress_callback(processed_count, total_items, f"Archiving {s['title']} Ch {ch['chapter_num']}")

                    if os.path.isfile(src_path):
                        zf.write(src_path, arcname=rel_path)
                    elif os.path.isdir(src_path):
                        # Recursive folder archive
                        for root, _, files in os.walk(src_path):
                            for f in files:
                                f_src = os.path.join(root, f)
                                f_rel = os.path.relpath(f_src, src_path)
                                arcname = os.path.join(rel_path, f_rel)
                                zf.write(f_src, arcname=arcname)

                    processed_count += 1

    # Atomic move
    if os.path.exists(output_zip_path):
        os.remove(output_zip_path)
    shutil.move(temp_zip_path, output_zip_path)

    return {
        "success": True,
        "zip_path": output_zip_path,
        "file_size": os.path.getsize(output_zip_path),
        "manifest": manifest
    }


def inspect_backup_archive(zip_path: str) -> Dict[str, Any]:
    """
    Validates backup archive integrity, checks for Zip-Slip vulnerabilities,
    and extracts manifest metadata without unpacking files.
    """
    if not os.path.exists(zip_path) or not zipfile.is_zipfile(zip_path):
        return {"success": False, "error": "Invalid or corrupted ZIP archive."}

    with zipfile.ZipFile(zip_path, 'r', allowZip64=True) as zf:
        namelist = zf.namelist()
        if "manifest.json" not in namelist:
            return {"success": False, "error": "Missing manifest.json in backup archive."}

        # Zip-Slip Vulnerability Defense Check
        for name in namelist:
            if name.startswith('/') or name.startswith('\\') or '..' in name.split('/') or '..' in name.split('\\'):
                return {"success": False, "error": f"Security violation: Illegal relative path detected in archive ({name})."}

        try:
            with zf.open("manifest.json") as mf:
                manifest_data = json.loads(mf.read().decode('utf-8'))
        except Exception as e:
            return {"success": False, "error": f"Corrupt manifest.json: {str(e)}"}

    return {
        "success": True,
        "manifest": manifest_data,
        "file_count": len(namelist),
        "zip_size_bytes": os.path.getsize(zip_path)
    }


def restore_backup_archive(
    zip_path: str,
    downloads_dir: str,
    db_path: str = DEFAULT_DB_PATH,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[str, Any]:
    """
    Fault-tolerant, sequential incremental sync.
    Restores chapters and series from a backup ZIP into downloads_dir and db_path
    without overwriting existing chapters or creating duplicate cards.
    """
    inspection = inspect_backup_archive(zip_path)
    if not inspection["success"]:
        return inspection

    manifest = inspection["manifest"]
    series_list = manifest.get("series", [])
    total_chapters = sum(len(s.get("chapters", [])) for s in series_list)

    # Pre-flight disk space verification
    uncompressed_bytes = manifest.get("stats", {}).get("uncompressed_bytes", 0)
    try:
        free_bytes = shutil.disk_usage(downloads_dir).free
        if uncompressed_bytes > 0 and free_bytes < (uncompressed_bytes + 50 * 1024 * 1024):
            return {
                "success": False,
                "error": f"Insufficient disk space. Needed: {format_bytes(uncompressed_bytes)}, Free: {format_bytes(free_bytes)}"
            }
    except Exception:
        pass

    staging_import_dir = os.path.join(downloads_dir, f".staging_import_{os.getpid()}_{int(datetime.now(timezone.utc).timestamp())}")
    os.makedirs(staging_import_dir, exist_ok=True)

    imported_chapters_count = 0
    skipped_duplicate_count = 0
    synced_series_count = 0

    try:
        # Extract files safely into staging
        with zipfile.ZipFile(zip_path, 'r', allowZip64=True) as zf:
            for member in zf.infolist():
                # Defend against Zip Slip
                target_path = os.path.abspath(os.path.join(staging_import_dir, member.filename))
                if not target_path.startswith(os.path.abspath(staging_import_dir)):
                    continue
                zf.extract(member, staging_import_dir)

        # Merge database & relocate files to final downloads directory
        for s in series_list:
            s_title = s.get("title") or "Unknown Series"
            s_slug = s.get("slug") or sanitize_filename(s_title).lower()
            safe_s_title = sanitize_filename(s_title)
            series_dest_dir = os.path.join(downloads_dir, safe_s_title)
            os.makedirs(series_dest_dir, exist_ok=True)

            # Get or create series using multi-key matching (prevents duplicate cards!)
            series_id = get_or_create_series(
                slug=s_slug,
                title=s_title,
                alt_titles=s.get("alt_titles"),
                author=s.get("author"),
                status=s.get("status", "Ongoing"),
                cover_url=s.get("cover_url"),
                engine=s.get("engine"),
                db_path=db_path
            )
            synced_series_count += 1

            # Restore cover image if present
            cover_rel = s.get("cover_relative_path")
            if cover_rel:
                staging_cover = os.path.join(staging_import_dir, cover_rel)
                dest_cover = os.path.join(series_dest_dir, "cover.jpg")
                if os.path.exists(staging_cover) and not os.path.exists(dest_cover):
                    try:
                        shutil.copy2(staging_cover, dest_cover)
                        update_series_cover(series_id, dest_cover, cover_url=s.get("cover_url"), db_path=db_path)
                    except Exception:
                        pass

            # Process chapters
            chapters = s.get("chapters", [])
            for ch in chapters:
                ch_num = float(ch.get("chapter_num", 1.0))
                rel_path = ch.get("relative_path")
                if not rel_path:
                    continue

                staging_ch_file = os.path.join(staging_import_dir, rel_path)
                filename = os.path.basename(rel_path.rstrip('/\\'))
                dest_ch_path = os.path.join(series_dest_dir, filename)

                if progress_callback:
                    progress_callback(
                        imported_chapters_count + skipped_duplicate_count,
                        total_chapters,
                        f"Restoring {s_title} Ch {ch_num}"
                    )

                # Move file from staging to final location if file exists in staging
                file_size = int(ch.get("file_size", 0))
                if os.path.exists(staging_ch_file):
                    if not os.path.exists(dest_ch_path) or os.path.getsize(dest_ch_path) < file_size:
                        if os.path.isdir(staging_ch_file):
                            if os.path.exists(dest_ch_path):
                                shutil.rmtree(dest_ch_path, ignore_errors=True)
                            shutil.move(staging_ch_file, dest_ch_path)
                        else:
                            shutil.move(staging_ch_file, dest_ch_path)
                    file_size = calculate_chapter_disk_size(dest_ch_path)

                # Record or update chapter in database with Phone B's local path
                ch_id = add_or_update_chapter(
                    series_id=series_id,
                    chapter_num=ch_num,
                    chapter_slug=ch.get("chapter_slug") or f"chapter-{ch_num:g}".replace('.', '_'),
                    title=ch.get("title") or f"Chapter {ch_num}",
                    panel_count=ch.get("panel_count", 0),
                    file_path=dest_ch_path,
                    file_format=ch.get("file_format") or "cbz",
                    file_size=file_size,
                    status="completed",
                    db_path=db_path
                )

                # Sync reading progress: preserve max reading page and read status
                try:
                    conn = get_connection(db_path)
                    with conn:
                        conn.execute("""
                            UPDATE chapters
                            SET read_status = max(read_status, ?),
                                last_read_page = max(last_read_page, ?)
                            WHERE id = ?
                        """, (int(ch.get("read_status", 0)), int(ch.get("last_read_page", 0)), ch_id))
                    conn.close()
                except Exception:
                    pass

                imported_chapters_count += 1

    finally:
        # Always clean up temporary staging import directory
        if os.path.exists(staging_import_dir):
            shutil.rmtree(staging_import_dir, ignore_errors=True)

    return {
        "success": True,
        "batch_label": manifest.get("batch", {}).get("batch_label", "Complete Library"),
        "series_synced": synced_series_count,
        "chapters_imported": imported_chapters_count,
        "chapters_skipped_duplicate": skipped_duplicate_count,
        "uncompressed_bytes": uncompressed_bytes
    }
