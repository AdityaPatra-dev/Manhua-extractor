import os
import re
import asyncio
from typing import Dict, List, Any, Optional, Callable
from urllib.parse import urlparse

from database.db import (
    get_all_series,
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

async def check_series_updates(
    series: Dict[str, Any],
    base_save_dir: str = DOWNLOADS_DIR,
    preferred_format: str = "pdf",
    max_width: int = 1080,
    max_new_chapters: int = 10,
    progress_cb: Optional[Callable[[str], None]] = None
) -> List[float]:
    """
    Check a single series for new released chapters and download them.
    Returns list of downloaded chapter numbers.
    """
    series_id = series["id"]
    series_title = series["title"]
    series_slug = series["slug"]

    # Retrieve existing chapters
    chapters = get_chapters_for_series(series_id)
    downloaded_nums = {c["chapter_num"] for c in chapters if c["status"] == "completed"}

    # Find starting point
    start_url = None
    if chapters:
        # Pick the latest chapter URL
        latest_ch = max(chapters, key=lambda c: c["chapter_num"])
        start_url = latest_ch.get("source_url")

    if not start_url:
        start_url = series.get("source_url")

    if not start_url:
        return []

    if progress_cb:
        progress_cb(f"Checking {series_title}...")

    # Analyze the reference chapter
    ref_data = dispatcher.analyze_url(start_url)
    if not ref_data.get("success"):
        return []

    next_url = ref_data.get("next_chapter_url")
    downloaded_now = []

    # Safe folder setup
    safe_folder_name = re.sub(r'[\\/*?:"<>|]', "", series_title)
    series_dir = os.path.join(base_save_dir, safe_folder_name)
    os.makedirs(series_dir, exist_ok=True)

    while next_url and len(downloaded_now) < max_new_chapters:
        ch_data = dispatcher.analyze_url(next_url)
        if not ch_data.get("success") or not ch_data.get("pages"):
            break

        ch_num = ch_data.get("chapter_num", 1.0)

        # Check if we already have this chapter
        if ch_num in downloaded_nums:
            next_url = ch_data.get("next_chapter_url")
            continue

        pages = ch_data.get("pages", [])
        if progress_cb:
            progress_cb(f"Downloading {series_title} Ch {ch_num} ({len(pages)} panels)...")

        # Staging directory for partial resume
        staging_dir = get_staging_dir(base_save_dir, series_slug, ch_num)

        # Download panels
        panel_bytes = await download_panels_stream(
            image_urls=pages,
            referer=next_url,
            max_width=max_width,
            jpeg_quality=75,
            staging_dir=staging_dir
        )

        if not panel_bytes:
            break

        # Filter recurring promotional / ad pages
        known_sigs = get_all_promo_signatures()
        if known_sigs:
            clean_panels, removed = filter_chapter_panels(panel_bytes, known_signatures=known_sigs)
            if removed > 0:
                panel_bytes = clean_panels

        safe_slug = series_slug.replace('-', '_')
        ch_str = f"{ch_num:g}".replace('.', '_')
        output_file = ""

        if preferred_format == "pdf":
            output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.pdf")
            compile_pdf(panel_bytes, output_file)
        elif preferred_format == "cbz":
            output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.cbz")
            compile_cbz(panel_bytes, output_file, series_title=series_title, chapter_num=ch_num, source_url=next_url)
        else:
            output_file = os.path.join(series_dir, f"Ch_{ch_str}")
            save_raw_images(panel_bytes, output_file)

        # Download completed and compiled successfully, clear staging
        cleanup_staging_dir(staging_dir)

        file_size = os.path.getsize(output_file) if os.path.exists(output_file) and os.path.isfile(output_file) else 0

        # Save to database
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=ch_num,
            chapter_slug=f"chapter-{ch_str}",
            title=f"Chapter {ch_num}",
            source_url=next_url,
            panel_count=len(panel_bytes),
            file_path=output_file,
            file_format=preferred_format,
            file_size=file_size,
            status="completed"
        )

        downloaded_now.append(ch_num)
        downloaded_nums.add(ch_num)

        # Scrobble tracker progress
        try:
            sync_trackers(
                title=series_title,
                chapter_num=ch_num,
                anilist_id=series.get("anilist_id"),
                mal_id=series.get("mal_id")
            )
        except Exception:
            pass

        # Send push notification
        dispatch_notification(
            title="New Chapter Downloaded!",
            message=f"Successfully downloaded Chapter {ch_num} ({len(panel_bytes)} panels).",
            series_title=series_title,
            chapter_num=ch_num,
            series_cover=series.get("cover_url"),
            chapter_url=next_url,
            file_path=output_file
        )

        next_url = ch_data.get("next_chapter_url")
        await asyncio.sleep(1)

    return downloaded_now

async def run_library_update(progress_cb: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Check all series in library.db for new releases and download them.
    """
    series_list = get_all_series()
    fmt = get_setting("preferred_format", "pdf")
    results = {
        "total_series": len(series_list),
        "updated_series_count": 0,
        "total_new_chapters": 0,
        "details": []
    }

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

