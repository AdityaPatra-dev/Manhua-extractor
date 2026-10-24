import os
import re
import asyncio
from typing import Dict, List, Any, Optional, Callable, Tuple
from urllib.parse import urlparse

from database.db import (
    get_all_series,
    get_series_by_id,
    get_series_sources,
    get_chapters_for_series,
    add_or_update_chapter,
    get_setting,
    get_all_promo_signatures
)
from extractors.dispatcher import dispatcher
from core.downloader import download_panels_stream, get_staging_dir, cleanup_staging_dir
from core.compiler import compile_pdf, compile_cbz, save_raw_images
from core.ad_filter import filter_chapter_panels
from core.scrobbler import sync_trackers
from core.notifier import dispatch_notification

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")


def resolve_series_update_url(series: Dict[str, Any]) -> Optional[str]:
    """Find the best catalog inspection URL for a given series."""
    # 1. Direct series source_url
    src = series.get("source_url")
    if src and src.strip():
        return src.strip()

    # 2. Recorded series sources in series_sources table
    try:
        sources = get_series_sources(series["id"])
        if sources:
            best_source = sources[0]
            if best_source.get("source_url"):
                return best_source["source_url"].strip()
    except Exception:
        pass

    # 3. Known chapter source_url from database
    try:
        chapters = get_chapters_for_series(series["id"])
        if chapters:
            latest_ch = max(chapters, key=lambda c: c.get("chapter_num") or 0.0)
            if latest_ch.get("source_url"):
                return latest_ch["source_url"].strip()
    except Exception:
        pass

    return None


async def find_new_chapters_for_series(series: Dict[str, Any]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Scrape catalog and compare against local chapters in SQLite database.
    Returns (target_url, list_of_new_chapters).
    """
    target_url = resolve_series_update_url(series)
    if not target_url:
        return None, []

    series_id = series["id"]
    existing_chapters = get_chapters_for_series(series_id)

    completed_nums = set()
    completed_urls = set()
    for c in existing_chapters:
        if c.get("status") == "completed":
            c_num = c.get("chapter_num")
            if c_num is not None:
                try:
                    completed_nums.add(float(c_num))
                except (ValueError, TypeError):
                    pass
            c_u = c.get("source_url")
            if c_u:
                completed_urls.add(c_u.strip().rstrip("/"))

    # Inspect series catalog page
    catalog = await asyncio.to_thread(dispatcher.inspect_series, target_url)
    if not catalog or not catalog.get("success") or not catalog.get("chapters"):
        return target_url, []

    new_chapters = []
    for ch in catalog.get("chapters", []):
        c_num = ch.get("chapter_num")
        c_url = (ch.get("url") or "").strip().rstrip("/")
        if c_num is not None:
            try:
                if float(c_num) in completed_nums:
                    continue
            except (ValueError, TypeError):
                pass
        if c_url and c_url in completed_urls:
            continue
        new_chapters.append(ch)

    # Sort new chapters ascending so earlier chapters download first
    def _ch_key(c):
        num = c.get("chapter_num")
        try:
            return float(num) if num is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    new_chapters.sort(key=_ch_key)
    return target_url, new_chapters


async def check_and_enqueue_series_update(
    series_id: int,
    queue_manager: Any,
    preferred_format: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check for new released chapters for a specific manhua and automatically
    enqueue them into the shared DownloadQueueManager.
    """
    series = get_series_by_id(series_id)
    if not series:
        return {"success": False, "error": f"Series ID {series_id} not found."}

    series_title = series.get("title") or "Unknown Series"
    fmt = (preferred_format or get_setting("preferred_format", "pdf") or "pdf").lower()

    target_url, new_chapters = await find_new_chapters_for_series(series)

    if not new_chapters:
        return {
            "success": True,
            "series_id": series_id,
            "series_title": series_title,
            "new_chapters": [],
            "queued": False,
            "message": f"'{series_title}' is already up to date (no new chapters found)."
        }

    # Prepare DownloadRequest
    from app import DownloadRequest
    chapter_urls = [c["url"].strip() for c in new_chapters if c.get("url")]
    if not chapter_urls:
        return {
            "success": True,
            "series_id": series_id,
            "series_title": series_title,
            "new_chapters": [],
            "queued": False,
            "message": f"'{series_title}' has no downloadable chapter URLs."
        }

    req = DownloadRequest(
        url=target_url or chapter_urls[0],
        chapter_urls=chapter_urls,
        series_title=series_title,
        cover_url=series.get("cover_url"),
        format=fmt,
        mode="batch",
        count=len(chapter_urls)
    )

    job = queue_manager.enqueue(req)
    ch_nums = [c.get("chapter_num") for c in new_chapters if c.get("chapter_num") is not None]

    return {
        "success": True,
        "series_id": series_id,
        "series_title": series_title,
        "new_chapters": ch_nums,
        "queued": True,
        "job_id": job.get("id"),
        "total_queued": len(chapter_urls),
        "message": f"Found {len(chapter_urls)} new chapter(s) for '{series_title}'! Added to Download Queue."
    }


async def check_series_updates(
    series: Dict[str, Any],
    base_save_dir: str = DOWNLOADS_DIR,
    preferred_format: str = "pdf",
    max_width: int = 1080,
    max_new_chapters: int = 10,
    progress_cb: Optional[Callable[[str], None]] = None
) -> List[float]:
    """
    Check a single series for new released chapters and download them directly (CLI fallback).
    """
    series_id = series["id"]
    series_title = series["title"]
    series_slug = series["slug"]

    if progress_cb:
        progress_cb(f"Checking catalog for {series_title}...")

    target_url, new_chaps = await find_new_chapters_for_series(series)
    if not new_chaps:
        return []

    downloaded_now = []
    safe_folder_name = re.sub(r'[\\/*?:"<>|]', "", series_title)
    series_dir = os.path.join(base_save_dir, safe_folder_name)
    os.makedirs(series_dir, exist_ok=True)

    for ch in new_chaps[:max_new_chapters]:
        ch_url = ch.get("url")
        if not ch_url:
            continue
        ch_num = ch.get("chapter_num") or 1.0

        if progress_cb:
            progress_cb(f"Downloading {series_title} Ch {ch_num}...")

        ch_data = await asyncio.to_thread(dispatcher.analyze_url, ch_url)
        if not ch_data.get("success") or not ch_data.get("pages"):
            continue

        pages = ch_data.get("pages", [])
        staging_dir = get_staging_dir(base_save_dir, series_slug, ch_num)

        panel_bytes = await download_panels_stream(
            image_urls=pages,
            referer=ch_url,
            max_width=max_width,
            jpeg_quality=75,
            staging_dir=staging_dir
        )
        if not panel_bytes:
            continue

        known_sigs = get_all_promo_signatures()
        if known_sigs:
            clean_panels, removed = filter_chapter_panels(panel_bytes, known_signatures=known_sigs)
            if removed > 0:
                panel_bytes = clean_panels

        safe_slug = series_slug.replace('-', '_')
        ch_str = f"{ch_num:g}".replace('.', '_')

        if preferred_format == "pdf":
            output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.pdf")
            compile_pdf(panel_bytes, output_file)
        elif preferred_format == "cbz":
            output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.cbz")
            compile_cbz(panel_bytes, output_file, series_title=series_title, chapter_num=ch_num, source_url=ch_url)
        else:
            output_file = os.path.join(series_dir, f"Ch_{ch_str}")
            save_raw_images(panel_bytes, output_file)

        cleanup_staging_dir(staging_dir)
        file_size = os.path.getsize(output_file) if os.path.exists(output_file) and os.path.isfile(output_file) else 0

        add_or_update_chapter(
            series_id=series_id,
            chapter_num=ch_num,
            chapter_slug=f"chapter-{ch_str}",
            title=ch.get("title") or f"Chapter {ch_num}",
            source_url=ch_url,
            panel_count=len(panel_bytes),
            file_path=output_file,
            file_format=preferred_format,
            file_size=file_size,
            status="completed"
        )
        downloaded_now.append(ch_num)
        await asyncio.sleep(0.5)

    return downloaded_now


async def run_library_update(
    queue_manager: Optional[Any] = None,
    progress_cb: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Check all series in library.db for new releases.
    If queue_manager is provided, automatically enqueues new chapters into the download queue!
    """
    series_list = get_all_series()
    fmt = get_setting("preferred_format", "pdf")
    results = {
        "total_series": len(series_list),
        "updated_series_count": 0,
        "total_new_chapters": 0,
        "details": []
    }

    if queue_manager is not None:
        for s in series_list:
            if progress_cb:
                progress_cb(f"Checking updates for '{s['title']}'...")
            res = await check_and_enqueue_series_update(
                series_id=s["id"],
                queue_manager=queue_manager,
                preferred_format=fmt
            )
            if res.get("queued") and res.get("new_chapters"):
                results["updated_series_count"] += 1
                results["total_new_chapters"] += len(res["new_chapters"])
                results["details"].append({
                    "series_id": s["id"],
                    "series_title": s["title"],
                    "new_chapters": res["new_chapters"]
                })
        return results

    # Standalone CLI mode without queue manager
    for s in series_list:
        new_chaps = await check_series_updates(
            series=s,
            preferred_format=fmt,
            progress_cb=progress_cb
        )
        if new_chaps:
            results["updated_series_count"] += 1
            results["total_new_chapters"] += len(new_chaps)
            results["details"].append({
                "series_id": s["id"],
                "series_title": s["title"],
                "new_chapters": new_chaps
            })

    return results
