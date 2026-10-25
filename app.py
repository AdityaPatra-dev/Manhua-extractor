import os
import sys
import shutil
import time
import re
import json
import asyncio
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from fastapi import FastAPI, BackgroundTasks, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from urllib.parse import urlparse

from database.db import (
    init_db,
    get_or_create_series,
    get_all_series,
    get_series_by_id,
    delete_series,
    delete_chapter,
    add_or_update_chapter,
    get_chapters_for_series,
    get_chapter_by_id,
    update_reading_progress,
    record_site_diagnostic,
    get_all_site_diagnostics,
    get_setting,
    set_setting,
    get_all_settings,
    add_promo_signature,
    get_all_promo_signatures,
    delete_promo_signature,
    update_series_trackers,
    update_series_cover,
    update_series_rich_metadata,
    get_cached_search,
    set_cached_search,
    add_or_update_series_source,
    get_series_sources,
    create_folder,
    rename_folder,
    delete_folder,
    add_series_to_folder,
    remove_series_from_folder,
    get_all_folders_with_items,
    get_folder_by_id
)
from core.search import search_dispatcher, cluster_search_results
from extractors.dispatcher import dispatcher
from core.downloader import download_panels_stream, get_staging_dir, cleanup_staging_dir
from core.slicer import slice_chapter_panels
from core.ad_filter import compute_perceptual_hash, filter_chapter_panels
from core.scrobbler import verify_anilist_token, verify_mal_token, sync_trackers
from core.app_updater import CURRENT_APP_VERSION, get_latest_release
from core.compiler import (
    compile_pdf,
    compile_cbz,
    save_raw_images,
    get_chapter_page_count,
    get_chapter_page_bytes
)
from core.updater import run_library_update
from core.notifier import send_test_alert
from core.backup_engine import (
    estimate_backup_batches,
    create_backup_batch_file,
    inspect_backup_archive,
    restore_backup_archive,
    format_bytes,
    DEFAULT_BATCH_SIZE_BYTES
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.environ.get("MANHUA_DOWNLOADS_DIR") or os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
BACKUPS_DIR = os.environ.get("MANHUA_BACKUPS_DIR") or os.path.join(BASE_DIR, "backups")
os.makedirs(BACKUPS_DIR, exist_ok=True)

# Initialize Database
init_db()

app = FastAPI(title="Universal Manhua Extractor & Library")

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "platform": "android" if os.environ.get("MANHUA_IS_ANDROID") else "desktop"
    }

@app.get("/api/app/version")
async def get_app_version():
    return {
        "version": CURRENT_APP_VERSION,
        "platform": "android" if os.environ.get("MANHUA_IS_ANDROID") else "desktop"
    }

@app.get("/api/app/check-update")
async def check_app_update(force: bool = False, simulate: bool = False, debug: bool = False):
    info = await asyncio.to_thread(get_latest_release, force=force, simulate=simulate, prefer_debug=debug)
    return info

@app.get("/api/app/download-update")
async def download_update_redirect():
    info = await asyncio.to_thread(get_latest_release, force=False)
    apk_url = info.get("apk_url")
    if not apk_url:
        return JSONResponse(status_code=404, content={"error": "No APK asset found for latest release"})
    return RedirectResponse(url=apk_url)

# Mount static folder
static_path = os.path.join(BASE_DIR, "static")
os.makedirs(static_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.on_event("startup")
async def start_periodic_scheduler():
    async def scheduler_worker():
        await asyncio.sleep(20)  # Wait 20 seconds after startup
        while True:
            try:
                enabled = get_setting("auto_update_enabled", "false") == "true"
                interval_hours = int(get_setting("auto_update_interval_hours", "6") or "6")
                if enabled and not download_progress["is_running"]:
                    await run_library_update()
            except Exception:
                pass
            interval_hours = max(1, int(get_setting("auto_update_interval_hours", "6") or "6"))
            await asyncio.sleep(interval_hours * 3600)

    asyncio.create_task(scheduler_worker())

# Global Download State & Progress Queues
download_progress = {
    "is_running": False,
    "is_paused": False,
    "is_cancelled": False,
    "current_url": None,
    "series_title": "",
    "chapter_num": 0,
    "current_panel": 0,
    "total_panels": 0,
    "chapter_index": 0,
    "total_chapters": 1,
    "status": "idle",
    "message": "Ready",
    "last_downloaded_series_id": None,
    "last_downloaded_chapter_id": None,
    "last_downloaded_chapter_num": None
}

# --- Request Models ---

class AnalyzeRequest(BaseModel):
    url: str

class InspectSeriesRequest(BaseModel):
    url: str
    cover_url: Optional[str] = None

class DownloadRequest(BaseModel):
    url: str
    mode: str = "single"  # single, range, crawl_all
    count: int = 1
    format: str = "pdf"   # pdf, cbz, folder
    max_width: int = 1080
    quality: int = 75
    image_format: str = "jpeg" # jpeg, webp
    webp_quality: int = 80
    upscale_scale: int = 1     # 1 = off, 2 = 2x, 4 = 4x
    upscale_engine: str = "auto" # auto, api, waifu2x, realesrgan, lanczos
    slice_eink: bool = False
    aspect_ratio: float = 1.414
    filter_promos: bool = True
    save_dir: Optional[str] = None
    chapter_urls: Optional[List[str]] = None
    cover_url: Optional[str] = None
    series_title: Optional[str] = None



class TestSiteRequest(BaseModel):
    url: str

class ProgressUpdateRequest(BaseModel):
    last_read_page: int = 0
    read_status: int = 1

class PromoSignatureRequest(BaseModel):
    phash: str
    label: str = "Promo"
    threshold: int = 10

class MarkPromoRequest(BaseModel):
    chapter_id: int
    page_index: int
    label: str = "Promo"
    threshold: int = 10

class VerifyTrackerRequest(BaseModel):
    token: str

class CreateFolderRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#4f46e5"
    series_ids: Optional[List[int]] = []

class RenameFolderRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class AddFolderItemRequest(BaseModel):
    series_id: int



# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(static_path, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Universal Manhua Extractor API Running</h1>"

@app.post("/api/analyze")
async def analyze_url(req: AnalyzeRequest):
    url = req.url.strip()
    if not url:
        return JSONResponse({"success": False, "error": "Empty URL"}, status_code=400)

    try:
        res = dispatcher.analyze_url(url)
        return res
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/api/inspect-series")
async def inspect_series_catalog(req: InspectSeriesRequest):
    url = req.url.strip()
    if not url:
        return JSONResponse({"success": False, "error": "Empty URL"}, status_code=400)

    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, dispatcher.inspect_series, url)
        if not res.get("success"):
            return JSONResponse(res, status_code=400)

        # Prioritize search cover passed from frontend or resolve from global search
        if req.cover_url and not res.get("cover_url"):
            res["cover_url"] = req.cover_url
        elif not res.get("cover_url"):
            from core.search.clustering import resolve_cover_from_search
            sc = resolve_cover_from_search(res.get("series_title") or "")
            if sc:
                res["cover_url"] = sc

        return res
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)



@app.get("/api/search")
async def api_search(q: str = "", tier: str = "fast", nocache: bool = False):
    query = q.strip()
    if not query:
        return JSONResponse({"success": False, "error": "Query cannot be empty"}, status_code=400)

    if not nocache:
        cached = get_cached_search(query)
        if cached is not None:
            return {
                "success": True,
                "cached": True,
                "query": query,
                "total_clusters": len(cached),
                "clusters": cached
            }

    clusters = await search_dispatcher.search_all(query, tier=tier)
    if clusters:
        set_cached_search(query, clusters)
    return {
        "success": True,
        "cached": False,
        "query": query,
        "total_clusters": len(clusters),
        "clusters": clusters
    }


@app.get("/api/search/stream")
async def api_search_stream(q: str = "", tier: str = "fast", nocache: bool = False):
    query = q.strip()
    if not query:
        return JSONResponse({"success": False, "error": "Query cannot be empty"}, status_code=400)

    async def sse_event_stream():
        if not nocache:
            cached = get_cached_search(query)
            if cached is not None:
                yield f"event: init\ndata: {json.dumps({'total_sources': 1, 'query': query, 'tier': tier, 'cached': True})}\n\n"
                yield f"event: complete\ndata: {json.dumps({'total_sources': 1, 'total_clusters': len(cached), 'clusters': cached, 'cached': True})}\n\n"
                return

        final_clusters = []
        try:
            async for item in search_dispatcher.search_stream(query, tier=tier):
                event_type = item.get("event", "update")
                event_data = item.get("data", {})
                if event_type == "complete":
                    final_clusters = event_data.get("clusters", [])
                yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

            if final_clusters:
                set_cached_search(query, final_clusters)
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        sse_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


class RegisterSourcePayload(BaseModel):
    source_key: str
    source_name: str
    source_url: str
    total_chapters: Optional[int] = 0
    latest_chapter_num: Optional[float] = 0.0
    quality_tag: Optional[str] = "Standard"
    latency_ms: Optional[int] = 0


@app.get("/api/series/{series_id}/sources")
async def api_get_series_sources(series_id: int):
    sources = get_series_sources(series_id)
    return {"success": True, "series_id": series_id, "sources": sources}


@app.post("/api/series/{series_id}/sources")
async def api_add_series_source(series_id: int, payload: RegisterSourcePayload):
    add_or_update_series_source(
        series_id=series_id,
        source_key=payload.source_key,
        source_name=payload.source_name,
        source_url=payload.source_url,
        total_chapters=payload.total_chapters or 0,
        latest_chapter_num=payload.latest_chapter_num or 0.0,
        quality_tag=payload.quality_tag or "Standard",
        latency_ms=payload.latency_ms or 0
    )
    return {"success": True, "message": f"Source '{payload.source_name}' registered for series {series_id}"}



def generate_svg_cover(title: str) -> bytes:
    clean_title = (title or "Manga").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="420" viewBox="0 0 300 420">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
  </defs>
  <rect width="300" height="420" fill="url(#bg)" rx="8"/>
  <rect x="15" y="15" width="270" height="390" fill="none" stroke="#334155" stroke-width="2" stroke-dasharray="4" rx="6"/>
  <text x="150" y="180" font-family="system-ui, sans-serif" font-size="48" fill="#6366f1" text-anchor="middle">📖</text>
  <text x="150" y="240" font-family="system-ui, sans-serif" font-size="16" font-weight="bold" fill="#f1f5f9" text-anchor="middle">
    <tspan x="150" dy="0">{clean_title[:24]}</tspan>
  </text>
  <text x="150" y="270" font-family="system-ui, sans-serif" font-size="12" fill="#94a3b8" text-anchor="middle">Cover</text>
</svg>"""
    return svg.encode('utf-8')

def save_series_cover_locally(
    series_id: int,
    series_dir: str,
    cover_url: Optional[str] = None,
    series_title: Optional[str] = None,
    fallback_bytes: Optional[bytes] = None,
    referer: Optional[str] = None
) -> Optional[str]:
    os.makedirs(series_dir, exist_ok=True)
    target_path = os.path.join(series_dir, "cover.jpg")

    def _try_fetch(url: str, ref: Optional[str] = None) -> bool:
        if not url or not url.startswith("http"):
            return False
        try:
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": ref or url,
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            }
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200 and len(resp.content) > 1000 and b"<html" not in resp.content[:200].lower():
                with open(target_path, "wb") as f:
                    f.write(resp.content)
                update_series_cover(series_id, target_path, url)
                return True
        except Exception:
            pass
        return False

    # 1. Try provided remote cover_url
    if cover_url and _try_fetch(cover_url, referer):
        return target_path

    # 2. Try looking up verified cover from Global Search
    stitle = series_title
    if not stitle:
        s_rec = get_series_by_id(series_id)
        if s_rec:
            stitle = s_rec.get("title")

    if stitle:
        try:
            from core.search.clustering import resolve_cover_from_search
            search_cover = resolve_cover_from_search(stitle)
            if search_cover and _try_fetch(search_cover, None):
                return target_path
        except Exception:
            pass

    # 3. Try fallback bytes (first panel of downloaded chapter) ONLY as absolute last resort
    if fallback_bytes and len(fallback_bytes) > 500:
        try:
            with open(target_path, "wb") as f:
                f.write(fallback_bytes)
            update_series_cover(series_id, target_path, cover_url)
            return target_path
        except Exception:
            pass

    if os.path.exists(target_path):
        return target_path
    return None

class DownloadQueueManager:
    """Manages active and queued multi-series chapter downloads with pause, resume, and cancellation."""
    def __init__(self):
        self.queue: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.active_job: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()
        self._worker_task: Optional[asyncio.Task] = None

    def enqueue(self, req: DownloadRequest) -> Dict[str, Any]:
        urls = [u.strip() for u in req.chapter_urls if u.strip()] if req.chapter_urls else []
        title_display = req.series_title or "Analyzing Series..."

        # Deduplication against active job and queued jobs
        active_urls = set()
        if self.active_job and self.active_job.get("req") and self.active_job["req"].chapter_urls:
            active_urls = {u.strip() for u in self.active_job["req"].chapter_urls if u.strip()}

        queued_urls = set()
        for j in self.queue:
            if j.get("req") and j["req"].chapter_urls:
                for u in j["req"].chapter_urls:
                    if u.strip():
                        queued_urls.add(u.strip())

        all_in_flight = active_urls | queued_urls

        if urls:
            remaining_urls = [u for u in urls if u not in all_in_flight]
            if not remaining_urls:
                if self.active_job and any(u in active_urls for u in urls):
                    return self.active_job
                for j in self.queue:
                    if any(u in (j.get("req").chapter_urls or []) for u in urls):
                        return j
                return self.active_job or (self.queue[0] if self.queue else {})
            urls = remaining_urls
            req.chapter_urls = urls
        else:
            if self.active_job and self.active_job.get("url") == req.url and self.active_job["status"] in ("downloading", "analyzing", "starting"):
                return self.active_job
            for j in self.queue:
                if j.get("url") == req.url and j["status"] in ("queued", "downloading"):
                    return j

        job_id = f"job_{int(time.time() * 1000)}_{len(self.queue) + len(self.history) + 1}"
        target_count = len(urls) if urls else (req.count if req.mode in ("range", "single") else 999)
        if not urls and req.mode == "single":
            target_count = 1

        job = {
            "id": job_id,
            "url": req.url,
            "series_title": title_display,
            "cover_url": req.cover_url,
            "format": (req.format or "pdf").lower(),
            "total_chapters": target_count,
            "chapters_processed": 0,
            "current_chapter_num": None,
            "current_panel": 0,
            "total_panels": 0,
            "status": "queued",
            "message": "Waiting in queue...",
            "req": req,
            "is_paused": False,
            "is_cancelled": False,
            "created_at": time.time()
        }
        self.queue.append(job)
        self.ensure_worker()
        return job

    def ensure_worker(self):
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                if self._worker_task is None or self._worker_task.done():
                    self._worker_task = loop.create_task(self._worker_loop())
        except RuntimeError:
            pass

    def pause_job(self, job_id: str) -> bool:
        if self.active_job and self.active_job["id"] == job_id:
            self.active_job["is_paused"] = True
            self.active_job["status"] = "paused"
            self.active_job["message"] = "Download paused."
            global download_progress
            download_progress["is_paused"] = True
            download_progress["status"] = "paused"
            download_progress["message"] = "Download paused."
            return True
        for j in self.queue:
            if j["id"] == job_id:
                j["is_paused"] = True
                j["status"] = "paused"
                j["message"] = "Paused in queue."
                return True
        return False

    def resume_job(self, job_id: str) -> bool:
        if self.active_job and self.active_job["id"] == job_id:
            self.active_job["is_paused"] = False
            self.active_job["status"] = "downloading"
            self.active_job["message"] = "Resuming download..."
            global download_progress
            download_progress["is_paused"] = False
            download_progress["status"] = "downloading"
            download_progress["message"] = "Resuming download..."
            return True
        for j in self.queue:
            if j["id"] == job_id:
                j["is_paused"] = False
                j["status"] = "queued"
                j["message"] = "Waiting in queue..."
                self.ensure_worker()
                return True
        return False

    def cancel_job(self, job_id: str) -> bool:
        if self.active_job and self.active_job["id"] == job_id:
            self.active_job["is_cancelled"] = True
            self.active_job["is_paused"] = False
            self.active_job["status"] = "cancelled"
            self.active_job["message"] = "Cancelling download..."
            global download_progress
            download_progress["is_cancelled"] = True
            download_progress["is_paused"] = False
            download_progress["status"] = "cancelled"
            download_progress["message"] = "Download stopped by user."
            return True
        for i, j in enumerate(self.queue):
            if j["id"] == job_id:
                j["status"] = "cancelled"
                j["message"] = "Cancelled from queue."
                self.history.insert(0, {k: v for k, v in j.items() if k != "req"})
                self.queue.pop(i)
                return True
        return False

    def clear_history(self):
        self.history.clear()

    def get_state(self) -> Dict[str, Any]:
        return {
            "active_job": {k: v for k, v in self.active_job.items() if k != "req"} if self.active_job else None,
            "queue": [{k: v for k, v in j.items() if k != "req"} for j in self.queue],
            "history": [{k: v for k, v in j.items() if k != "req"} for j in self.history[:20]]
        }

    async def _worker_loop(self):
        global download_progress
        while True:
            next_job = None
            async with self._lock:
                for j in self.queue:
                    if j["status"] == "queued" and not j["is_paused"]:
                        next_job = j
                        break
                if not next_job:
                    self.active_job = None
                    download_progress["is_running"] = False
                    if download_progress.get("status") in ("downloading", "analyzing", "compiling", "slicing", "upscaling", "starting"):
                        download_progress["status"] = "idle"
                        download_progress["message"] = "Ready"
                    break

                self.queue.remove(next_job)
                self.active_job = next_job
                self.active_job["status"] = "downloading"

            try:
                await execute_download_job(self.active_job)
            except Exception as e:
                self.active_job["status"] = "error"
                self.active_job["message"] = f"Error: {str(e)}"
            finally:
                async with self._lock:
                    summary = {k: v for k, v in self.active_job.items() if k != "req"}
                    self.history.insert(0, summary)
                    if len(self.history) > 30:
                        self.history.pop()
                    self.active_job = None
            await asyncio.sleep(0.5)

download_queue_manager = DownloadQueueManager()

async def execute_download_job(job: Dict[str, Any]):
    req: DownloadRequest = job["req"]
    global download_progress
    download_progress["is_running"] = True
    download_progress["is_paused"] = job.get("is_paused", False)
    download_progress["is_cancelled"] = job.get("is_cancelled", False)
    download_progress["status"] = "starting"
    download_progress["message"] = "Starting extraction..."
    job["status"] = "starting"
    job["message"] = "Starting extraction..."

    specific_urls = [u.strip() for u in req.chapter_urls if u.strip()] if req.chapter_urls else []
    target_count = len(specific_urls) if specific_urls else (req.count if req.mode in ("range", "single") else 999)
    if not specific_urls and req.mode == "single":
        target_count = 1

    job["total_chapters"] = target_count
    download_progress["total_chapters"] = target_count

    current_url = specific_urls[0] if specific_urls else req.url.strip()
    chapters_processed = 0
    base_save_dir = req.save_dir or DOWNLOADS_DIR
    downloaded_chapter_nums = set()

    try:
        while chapters_processed < target_count:
            if job.get("is_cancelled") or download_progress.get("is_cancelled"):
                job["status"] = "cancelled"
                job["message"] = "Download stopped by user."
                download_progress["status"] = "cancelled"
                download_progress["message"] = "Download stopped by user."
                break

            while (job.get("is_paused") or download_progress.get("is_paused")) and not (job.get("is_cancelled") or download_progress.get("is_cancelled")):
                job["status"] = "paused"
                job["message"] = "Download paused."
                download_progress["status"] = "paused"
                download_progress["message"] = "Download paused."
                await asyncio.sleep(0.5)

            if job.get("is_cancelled") or download_progress.get("is_cancelled"):
                job["status"] = "cancelled"
                job["message"] = "Download stopped by user."
                download_progress["status"] = "cancelled"
                download_progress["message"] = "Download stopped by user."
                break

            if specific_urls:
                current_url = specific_urls[chapters_processed]
            elif not current_url:
                break

            download_progress["current_url"] = current_url
            download_progress["chapter_index"] = chapters_processed + 1
            download_progress["total_chapters"] = target_count
            download_progress["status"] = "analyzing"
            download_progress["message"] = f"Analyzing chapter {chapters_processed + 1} of {target_count}..."

            job["chapters_processed"] = chapters_processed
            job["status"] = "analyzing"
            job["message"] = f"Analyzing chapter {chapters_processed + 1} of {target_count}..."

            # Analyze page
            data = await asyncio.to_thread(dispatcher.analyze_url, current_url)
            if not data.get("success") or not data.get("pages"):
                job["message"] = f"Failed to extract panels from {current_url}"
                download_progress["message"] = f"Failed to extract panels from {current_url}"
                break

            if job.get("is_cancelled") or download_progress.get("is_cancelled"):
                job["status"] = "cancelled"
                job["message"] = "Download stopped by user."
                download_progress["status"] = "cancelled"
                download_progress["message"] = "Download stopped by user."
                break

            raw_title = req.series_title or data.get("series_title") or "Unknown Series"
            is_hitomi = (data.get("engine_id") == "hitomi") or ("hitomi.la" in current_url) or (str(data.get("series_slug") or "").lower().startswith("hitomi"))

            if not is_hitomi:
                clean_series_title = re.sub(r'(?:[-—|:]\s*)?(?:chapter|episode|ep|ch|vol|volume|#)\s*[\d\.\-]+.*', '', raw_title, flags=re.I).strip(' -:|—')
                clean_series_title = re.sub(r'\s+[\d\.\-]+(?:\s*raw|\s*end)?$', '', clean_series_title, flags=re.I).strip(' -:|—')
                series_title = clean_series_title if clean_series_title else raw_title
            else:
                series_title = raw_title

            series_slug = data.get("series_slug")
            if series_slug and not is_hitomi:
                series_slug = re.sub(r'[-_](?:chapter|episode|ch|ep|vol|volume)?[-_.]?\d+(?:\.\d+)?$', '', str(series_slug), flags=re.I)
            if not series_slug or (not is_hitomi and re.search(r'^(?:ch(?:apter)?|ep(?:isode)?)[-_.]?\d+|^\d+(?:\.\d+)?$', str(series_slug), re.I)):
                if series_title and series_title != "Unknown Series":
                    series_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', series_title.lower()).strip('_')
                else:
                    series_slug = series_slug or "unknown_series"

            extracted_ch_num = data.get("chapter_num")
            if is_hitomi:
                chapter_num = 1.0
            elif extracted_ch_num is not None and extracted_ch_num > 0:
                chapter_num = extracted_ch_num
            elif downloaded_chapter_nums:
                chapter_num = max(downloaded_chapter_nums) + 1.0
            else:
                chapter_num = extracted_ch_num or (chapters_processed + 1.0)
            downloaded_chapter_nums.add(chapter_num)

            pages = data.get("pages", [])

            # Register/Update in Database (prioritize verified cover from global search if provided)
            effective_cover = req.cover_url or data.get("series_cover")
            series_id = get_or_create_series(
                slug=series_slug,
                title=series_title,
                author=data.get("series_author"),
                status=data.get("series_status") or "Ongoing",
                synopsis=data.get("series_synopsis"),
                cover_url=effective_cover,
                source_url=current_url,
                engine=data.get("engine_id")
            )

            # Also update rich metadata in case series already existed
            if data.get("series_synopsis") or data.get("series_author") or data.get("series_artist"):
                update_series_rich_metadata(series_id, {
                    "author": data.get("series_author"),
                    "artist": data.get("series_artist"),
                    "synopsis": data.get("series_synopsis"),
                    "genres": data.get("series_genres"),
                    "tags": data.get("series_tags"),
                    "status": data.get("series_status") or "Ongoing"
                })

            # Ensure canonical series title from database is used for directory & metadata
            canonical = get_series_by_id(series_id)
            if canonical and canonical.get("title"):
                series_title = canonical["title"]

            job["series_title"] = series_title
            if effective_cover and not job.get("cover_url"):
                job["cover_url"] = effective_cover
            job["current_chapter_num"] = chapter_num
            job["total_panels"] = len(pages)
            job["current_panel"] = 0

            download_progress["series_title"] = series_title
            download_progress["chapter_num"] = chapter_num
            download_progress["total_panels"] = len(pages)
            download_progress["current_panel"] = 0

            # Create series directory
            safe_title = re.sub(r'[\/*?:"<>|]', "", series_title)
            series_dir = os.path.join(base_save_dir, safe_title)
            os.makedirs(series_dir, exist_ok=True)

            # Progress callback for downloader
            def on_progress(done, total):
                job["current_panel"] = done
                job["total_panels"] = total
                download_progress["current_panel"] = done
                download_progress["total_panels"] = total

            # Stream download pages
            staging_dir = get_staging_dir(base_save_dir, series_slug, chapter_num)
            job["status"] = "downloading"
            job["message"] = f"Downloading Chapter {chapter_num} (0/{len(pages)} panels)..."
            download_progress["status"] = "downloading"
            download_progress["message"] = f"Downloading Chapter {chapter_num} (0/{len(pages)} panels)..."

            panel_bytes = await download_panels_stream(
                image_urls=pages,
                referer=current_url,
                max_width=req.max_width,
                jpeg_quality=req.quality,
                staging_dir=staging_dir,
                image_format=req.image_format,
                webp_quality=req.webp_quality,
                progress_callback=on_progress,
                is_cancelled_callback=lambda: job.get("is_cancelled", False) or download_progress.get("is_cancelled", False),
                is_paused_callback=lambda: job.get("is_paused", False) or download_progress.get("is_paused", False)
            )

            if job.get("is_cancelled") or download_progress.get("is_cancelled"):
                job["status"] = "cancelled"
                job["message"] = "Download stopped by user."
                download_progress["status"] = "cancelled"
                download_progress["message"] = "Download stopped by user."
                break

            if not panel_bytes:
                job["status"] = "error"
                job["message"] = f"Could not download panels for Chapter {chapter_num}"
                download_progress["status"] = "error"
                download_progress["message"] = f"Could not download panels for Chapter {chapter_num}"
                break

            # Filter recurring promotional / ad pages
            if req.filter_promos:
                known_sigs = get_all_promo_signatures()
                if known_sigs:
                    clean_panels, removed = await asyncio.to_thread(filter_chapter_panels, panel_bytes, known_signatures=known_sigs)
                    if removed > 0:
                        job["message"] = f"Removed {removed} promotional credit pages..."
                        download_progress["message"] = f"Removed {removed} promotional credit pages..."
                        panel_bytes = clean_panels
                        job["total_panels"] = len(panel_bytes)
                        download_progress["total_panels"] = len(panel_bytes)

            # AI Super-Resolution Upscaling (Waifu2x / Real-ESRGAN / Lanczos)
            if req.upscale_scale > 1:
                job["status"] = "upscaling"
                job["message"] = f"Upscaling {len(panel_bytes)} panels ({req.upscale_scale}x)..."
                download_progress["status"] = "upscaling"
                download_progress["message"] = f"Upscaling {len(panel_bytes)} panels ({req.upscale_scale}x)..."
                from core.upscaler import upscale_panel, is_upscaler_api_available
                upscaler_url = get_setting("ai_upscaler_url", "http://localhost:5000/upscale")
                api_online = is_upscaler_api_available(upscaler_url)
                effective_url = upscaler_url if api_online else None
                def _do_upscale():
                    return [
                        upscale_panel(b, scale=req.upscale_scale, engine=req.upscale_engine, endpoint=effective_url)
                        for b in panel_bytes
                    ]
                panel_bytes = await asyncio.to_thread(_do_upscale)

            # Smart E-Ink / Kindle slicing
            if req.slice_eink:
                job["status"] = "slicing"
                job["message"] = f"Slicing webtoon ribbons into e-ink pages..."
                download_progress["status"] = "slicing"
                download_progress["message"] = f"Slicing webtoon ribbons into e-ink pages..."
                panel_bytes = await asyncio.to_thread(
                    slice_chapter_panels,
                    panel_bytes,
                    target_aspect_ratio=req.aspect_ratio,
                    jpeg_quality=req.quality
                )
                job["total_panels"] = len(panel_bytes)
                download_progress["total_panels"] = len(panel_bytes)

            # Compile into chosen format
            effective_format = (req.format or "pdf").lower()
            job["status"] = "compiling"
            job["message"] = f"Compiling Chapter {chapter_num} to {effective_format.upper()}..."
            download_progress["status"] = "compiling"
            download_progress["message"] = f"Compiling Chapter {chapter_num} to {effective_format.upper()}..."

            safe_slug = re.sub(r'[^a-zA-Z0-9_\-]+', '_', series_slug).strip('_')
            ch_str = f"{chapter_num:g}".replace('.', '_')
            output_file = ""
            compile_success = False

            if effective_format == "pdf":
                output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.pdf")
                compile_success = await asyncio.to_thread(compile_pdf, panel_bytes, output_file)
                # Robust fallback: If PDF compilation failed or produced a 0-byte file, fall back to CBZ so panels are preserved
                if not compile_success or not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                    print(f"[Compiler] PDF compilation failed for {output_file}, falling back to CBZ archive...", file=sys.stderr)
                    cbz_output = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.cbz")
                    compile_success = await asyncio.to_thread(
                        compile_cbz,
                        panel_bytes,
                        cbz_output,
                        series_title=series_title,
                        chapter_num=chapter_num,
                        source_url=current_url,
                        chapter_title=f"Chapter {chapter_num}"
                    )
                    if compile_success and os.path.exists(cbz_output) and os.path.getsize(cbz_output) > 0:
                        output_file = cbz_output
                        effective_format = "cbz"
            elif effective_format == "cbz":
                output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.cbz")
                series_meta = get_series_by_id(series_id)
                if not series_meta or not series_meta.get("author") or series_meta.get("author") == "Unknown":
                    try:
                        from core.metadata import fetch_rich_metadata
                        fetched_meta = fetch_rich_metadata(series_title)
                        if fetched_meta:
                            update_series_rich_metadata(series_id, fetched_meta)
                            series_meta = get_series_by_id(series_id)
                    except Exception:
                        pass
                compile_success = await asyncio.to_thread(
                    compile_cbz,
                    panel_bytes,
                    output_file,
                    series_title=series_title,
                    chapter_num=chapter_num,
                    source_url=current_url,
                    chapter_title=f"Chapter {chapter_num}",
                    metadata=dict(series_meta) if series_meta else None
                )
            else: # folder
                output_file = os.path.join(series_dir, f"Ch_{ch_str}")
                compile_success = await asyncio.to_thread(save_raw_images, panel_bytes, output_file)
                effective_format = "folder"

            # Ensure local series cover is cached
            series_rec = get_series_by_id(series_id)
            if not series_rec or not series_rec.get("cover_path") or not os.path.exists(series_rec.get("cover_path") or ""):
                await asyncio.to_thread(
                    save_series_cover_locally,
                    series_id=series_id,
                    series_dir=series_dir,
                    cover_url=effective_cover or (series_rec.get("cover_url") if series_rec else None),
                    series_title=series_title,
                    fallback_bytes=panel_bytes[0] if panel_bytes else None,
                    referer=current_url
                )

            file_size = os.path.getsize(output_file) if (output_file and os.path.exists(output_file) and os.path.isfile(output_file)) else 0

            # Only mark completed and cleanup staging if output file was successfully written and non-empty
            if compile_success and file_size > 0:
                cleanup_staging_dir(staging_dir)
                status_str = "completed"
                # Overwrite cleanup: remove any obsolete conflicting file with same chapter number in a different format
                possible_conflicts = [
                    os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.pdf"),
                    os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.cbz"),
                    os.path.join(series_dir, f"Ch_{ch_str}")
                ]
                for conf in possible_conflicts:
                    if conf != output_file and os.path.exists(conf):
                        try:
                            if os.path.isdir(conf):
                                shutil.rmtree(conf, ignore_errors=True)
                            else:
                                os.remove(conf)
                        except Exception:
                            pass
            else:
                status_str = "failed"
                print(f"[Compiler] Warning: Compilation produced empty/invalid file for {output_file}. Preserving staging directory.", file=sys.stderr)

            # Record chapter in database
            chap_id = add_or_update_chapter(
                series_id=series_id,
                chapter_num=chapter_num,
                chapter_slug=f"chapter-{ch_str}",
                title=f"Chapter {chapter_num}",
                source_url=current_url,
                panel_count=len(panel_bytes),
                file_path=output_file,
                file_format=effective_format,
                file_size=file_size,
                status=status_str
            )

            download_progress["last_downloaded_series_id"] = series_id
            download_progress["last_downloaded_chapter_id"] = chap_id
            download_progress["last_downloaded_chapter_num"] = chapter_num

            # Scrobble reading progress to configured trackers
            try:
                sync_trackers(title=series_title, chapter_num=chapter_num)
            except Exception:
                pass

            chapters_processed += 1
            job["chapters_processed"] = chapters_processed
            if not specific_urls:
                next_url = data.get("next_chapter_url")
                if not next_url and chapters_processed < target_count:
                    from extractors.heuristic import HeuristicExtractor
                    next_url = HeuristicExtractor().extract_next_chapter(None, current_url)
                current_url = next_url

            # Small breather between chapters
            await asyncio.sleep(0.5)

        if job.get("is_cancelled") or download_progress.get("is_cancelled"):
            job["status"] = "cancelled"
            job["message"] = f"Download stopped. {chapters_processed} chapter(s) saved."
            download_progress["status"] = "cancelled"
            download_progress["message"] = f"Download stopped. {chapters_processed} chapter(s) saved."
        elif chapters_processed > 0:
            job["status"] = "completed"
            job["message"] = f"Successfully downloaded {chapters_processed} chapter(s)!"
            download_progress["status"] = "completed"
            download_progress["message"] = f"Successfully downloaded {chapters_processed} chapter(s)!"
        else:
            if job.get("status") not in ("error", "cancelled"):
                job["status"] = "error"
                job["message"] = "Download failed: No chapters or panels could be downloaded."
                download_progress["status"] = "error"
                download_progress["message"] = "Download failed: No chapters or panels could be downloaded."
    except Exception as e:
        job["status"] = "error"
        job["message"] = f"Error: {str(e)}"
        download_progress["status"] = "error"
        download_progress["message"] = f"Error: {str(e)}"
    finally:
        has_pending = any(j.get("status") == "queued" and not j.get("is_paused") for j in download_queue_manager.queue)
        if not has_pending:
            download_progress["is_running"] = False
        download_progress["is_paused"] = False

async def run_download_job(req: DownloadRequest):
    """Legacy helper: enqueues job and waits until completed (backward compatibility)."""
    job = download_queue_manager.enqueue(req)
    while True:
        if job["status"] in ("completed", "cancelled", "error"):
            break
        await asyncio.sleep(0.5)


@app.post("/api/download")
async def start_download(req: DownloadRequest):
    job = download_queue_manager.enqueue(req)
    is_active = bool(download_queue_manager.active_job and download_queue_manager.active_job.get("id") == job.get("id"))
    queue_pos = 0
    if not is_active:
        for idx, j in enumerate(download_queue_manager.queue):
            if j.get("id") == job.get("id"):
                queue_pos = idx + 1
                break
    return {
        "success": True,
        "job_id": job.get("id"),
        "series_title": job.get("series_title"),
        "queued": not is_active,
        "queue_position": queue_pos,
        "message": f"Download task started for '{job.get('series_title')}'." if is_active else f"'{job.get('series_title')}' added to download queue (position #{queue_pos})."
    }

@app.get("/api/queue")
async def get_download_queue():
    """Retrieve full status of active, queued, and recently finished download jobs."""
    return {
        "success": True,
        **download_queue_manager.get_state()
    }

@app.post("/api/queue/pause/{job_id}")
async def pause_queue_job(job_id: str):
    ok = download_queue_manager.pause_job(job_id)
    return {"success": ok, "message": "Job paused." if ok else "Job not found in queue."}

@app.post("/api/queue/resume/{job_id}")
async def resume_queue_job(job_id: str):
    ok = download_queue_manager.resume_job(job_id)
    return {"success": ok, "message": "Job resumed." if ok else "Job not found in queue."}

@app.post("/api/queue/cancel/{job_id}")
async def cancel_queue_job(job_id: str):
    ok = download_queue_manager.cancel_job(job_id)
    return {"success": ok, "message": "Job cancelled." if ok else "Job not found in queue."}

@app.post("/api/queue/clear")
async def clear_queue_history():
    download_queue_manager.clear_history()
    return {"success": True, "message": "Download history cleared."}

@app.post("/api/download/pause")
async def pause_download():
    global download_progress
    if not download_progress.get("is_running") and not download_queue_manager.active_job:
        return JSONResponse({"success": False, "error": "No download currently in progress."}, status_code=400)
    download_progress["is_paused"] = True
    download_progress["status"] = "paused"
    download_progress["message"] = "Download paused."
    if download_queue_manager.active_job:
        download_queue_manager.pause_job(download_queue_manager.active_job["id"])
    return {"success": True, "message": "Download paused."}

@app.post("/api/download/resume")
async def resume_download():
    global download_progress
    if not download_progress.get("is_running") and not download_queue_manager.active_job:
        paused_in_q = False
        for j in download_queue_manager.queue:
            if j.get("is_paused"):
                download_queue_manager.resume_job(j["id"])
                paused_in_q = True
                break
        if not paused_in_q:
            return JSONResponse({"success": False, "error": "No download currently in progress."}, status_code=400)
        return {"success": True, "message": "Queued download resumed."}
    download_progress["is_paused"] = False
    download_progress["status"] = "downloading"
    download_progress["message"] = "Resuming download..."
    if download_queue_manager.active_job:
        download_queue_manager.resume_job(download_queue_manager.active_job["id"])
    return {"success": True, "message": "Download resumed."}

@app.post("/api/download/stop")
async def stop_download():
    global download_progress
    if not download_progress.get("is_running") and not download_queue_manager.active_job:
        return JSONResponse({"success": False, "error": "No download currently in progress."}, status_code=400)
    download_progress["is_cancelled"] = True
    download_progress["is_paused"] = False
    download_progress["status"] = "stopping"
    download_progress["message"] = "Stopping download..."
    if download_queue_manager.active_job:
        download_queue_manager.cancel_job(download_queue_manager.active_job["id"])
    return {"success": True, "message": "Download stop signal sent."}

@app.get("/api/download/progress")
async def get_progress_stream(request: Request):
    """Server-Sent Events (SSE) streaming live progress and download queue to the frontend."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            q_state = download_queue_manager.get_state()
            active = q_state["active_job"]
            total_active_and_pending = len(q_state["queue"]) + (1 if active else 0)
            payload = json.dumps({
                **download_progress,
                "active_job": active,
                "queue": q_state["queue"],
                "history": q_state["history"],
                "queue_count": total_active_and_pending
            })
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- Library Endpoints ---

@app.get("/api/library")
async def list_library():
    series_list = get_all_series()
    folders = get_all_folders_with_items()

    folder_map = {}
    for f in folders:
        for s_id in f.get("series_ids", []):
            folder_map[s_id] = {"folder_id": f["id"], "folder_name": f["name"]}

    for s in series_list:
        if s["id"] in folder_map:
            s["folder_id"] = folder_map[s["id"]]["folder_id"]
            s["folder_name"] = folder_map[s["id"]]["folder_name"]
        else:
            s["folder_id"] = None
            s["folder_name"] = None

    return {
        "success": True,
        "series": series_list,
        "folders": folders
    }

@app.get("/api/library/folders")
async def list_library_folders():
    folders = get_all_folders_with_items()
    return {"success": True, "folders": folders}

@app.post("/api/library/folders")
async def create_new_folder(req: CreateFolderRequest):
    folder_id = create_folder(name=req.name, description=req.description, color=req.color, series_ids=req.series_ids)
    folder = get_folder_by_id(folder_id)
    return {"success": True, "folder": folder}

@app.get("/api/library/folders/{folder_id}")
async def get_folder_details(folder_id: int):
    folder = get_folder_by_id(folder_id)
    if not folder:
        return JSONResponse({"success": False, "error": "Folder not found"}, status_code=404)
    return {"success": True, "folder": folder}

@app.patch("/api/library/folders/{folder_id}")
async def update_folder_name(folder_id: int, req: RenameFolderRequest):
    from database.db import update_folder_metadata
    ok = update_folder_metadata(folder_id, name=req.name, description=req.description)
    if not ok:
        return JSONResponse({"success": False, "error": "Folder not found or invalid data"}, status_code=400)
    return {"success": True, "message": "Folder updated"}

@app.delete("/api/library/folders/{folder_id}")
async def delete_existing_folder(folder_id: int):
    ok = delete_folder(folder_id)
    return {"success": ok}

@app.post("/api/library/folders/{folder_id}/items")
async def add_item_to_folder(folder_id: int, req: AddFolderItemRequest):
    ok = add_series_to_folder(folder_id, req.series_id)
    return {"success": ok}

@app.delete("/api/library/folders/{folder_id}/items/{series_id}")
async def remove_item_from_folder(folder_id: int, series_id: int):
    ok = remove_series_from_folder(folder_id, series_id)
    return {"success": ok}

@app.get("/api/library/{series_id}")
async def get_series_detail(series_id: int):
    series = get_series_by_id(series_id)
    if not series:
        return JSONResponse({"success": False, "error": "Series not found"}, status_code=404)
    chapters = get_chapters_for_series(series_id)
    
    safe_title = re.sub(r'[\\/*?:"<>|]', "", series.get("slug") or series.get("title") or "series")
    storage_dir = os.path.join(DOWNLOADS_DIR, safe_title)
    for c in chapters:
        if c.get("file_path") and os.path.exists(os.path.dirname(c["file_path"])):
            storage_dir = os.path.dirname(c["file_path"])
            break

    # Discover and register any chapter files on disk that aren't yet in the database
    if os.path.exists(storage_dir):
        known_paths = {c.get("file_path") for c in chapters if c.get("file_path")}
        known_nums = {c.get("chapter_num") for c in chapters if c.get("chapter_num") is not None}
        new_found = False
        for fname in sorted(os.listdir(storage_dir)):
            full_p = os.path.join(storage_dir, fname)
            if not os.path.isfile(full_p) or full_p in known_paths:
                continue
            ext = os.path.splitext(fname)[1].lower().lstrip('.')
            if ext not in ("pdf", "cbz"):
                continue
            m = re.search(r'[-_]ch[-_.]?(\d+(?:[\.-]\d+)?)|\b(\d+(?:[\.-]\d+)?)\.(?:pdf|cbz)$', fname, re.I)
            if m:
                raw_num = (m.group(1) or m.group(2)).replace('-', '.')
                try:
                    ch_val = float(raw_num)
                    if ch_val not in known_nums:
                        add_or_update_chapter(
                            series_id=series_id,
                            chapter_num=ch_val,
                            chapter_slug=f"chapter-{int(ch_val) if ch_val.is_integer() else ch_val}",
                            title=f"Chapter {int(ch_val) if ch_val.is_integer() else ch_val}",
                            file_path=full_p,
                            file_format=ext,
                            file_size=os.path.getsize(full_p),
                            status="completed"
                        )
                        known_nums.add(ch_val)
                        known_paths.add(full_p)
                        new_found = True
                except ValueError:
                    pass
        if new_found:
            chapters = get_chapters_for_series(series_id)

    return {
        "success": True, 
        "series": series, 
        "chapters": chapters,
        "storage_dir": os.path.abspath(storage_dir)
    }

def detect_image_media_type(path_or_bytes) -> str:
    """Detect appropriate MIME type from image bytes or file header."""
    head = b""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        head = path_or_bytes[:16]
    elif isinstance(path_or_bytes, str) and os.path.exists(path_or_bytes):
        try:
            with open(path_or_bytes, "rb") as f:
                head = f.read(16)
        except Exception:
            pass
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if len(head) >= 8 and head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(head) >= 3 and head[:3] == b"GIF":
        return "image/gif"
    if len(head) >= 2 and head[:2] == b"\xff\xd8":
        return "image/jpeg"
    return "image/jpeg"

@app.get("/api/cover-proxy")
async def proxy_cover_image(url: str, referer: Optional[str] = None):
    """Safely proxy and cache remote cover images with proper headers to prevent 403 Forbidden / CORS blocks."""
    if not url or not url.startswith("http"):
        return Response(content=generate_svg_cover("No Cover"), media_type="image/svg+xml")

    import hashlib
    h = hashlib.md5(url.encode()).hexdigest()
    cache_dir = os.path.join(DOWNLOADS_DIR, ".cover_cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{h}.img")

    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 500:
        with open(cache_file, "rb") as f:
            data = f.read()
        media_type = detect_image_media_type(data)
        return Response(content=data, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})

    try:
        import requests
        ref = referer or url
        if "gold-usergeneratedcontent.net" in url:
            ref = "https://hitomi.la/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": ref,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        }
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200 and len(resp.content) > 500 and b"<html" not in resp.content[:200].lower():
            with open(cache_file, "wb") as f:
                f.write(resp.content)
            media_type = detect_image_media_type(resp.content)
            return Response(content=resp.content, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        pass

    return Response(content=generate_svg_cover("No Cover"), media_type="image/svg+xml")

@app.get("/api/series/{series_id}/cover")
async def get_series_cover_endpoint(series_id: int):
    """Serve series cover image with local caching, chapter panel fallback, and SVG placeholder."""
    series = get_series_by_id(series_id)
    if not series:
        return Response(content=generate_svg_cover("Not Found"), media_type="image/svg+xml")

    # 1. Existing local cover file
    if series.get("cover_path") and os.path.exists(series["cover_path"]):
        return FileResponse(series["cover_path"], media_type=detect_image_media_type(series["cover_path"]))

    safe_title = re.sub(r'[\\/*?:"<>|]', "", series["title"])
    series_dir = os.path.join(DOWNLOADS_DIR, safe_title)
    cand_path = os.path.join(series_dir, "cover.jpg")
    if os.path.exists(cand_path):
        update_series_cover(series_id, cand_path)
        return FileResponse(cand_path, media_type=detect_image_media_type(cand_path))

    # 2. Try downloading remote cover_url or resolving from Global Search
    saved = save_series_cover_locally(
        series_id=series_id,
        series_dir=series_dir,
        cover_url=series.get("cover_url"),
        series_title=series.get("title"),
        referer=series.get("source_url")
    )
    if saved and os.path.exists(saved):
        return FileResponse(saved, media_type=detect_image_media_type(saved))

    # 3. Fallback: extract page 0 of any downloaded chapter
    chapters = get_chapters_for_series(series_id)
    for chap in chapters:
        if chap.get("file_path") and os.path.exists(chap["file_path"]):
            p_bytes = get_chapter_page_bytes(chap["file_path"], chap["file_format"], 0)
            if p_bytes:
                saved = save_series_cover_locally(
                    series_id=series_id,
                    series_dir=series_dir,
                    fallback_bytes=p_bytes
                )
                if saved and os.path.exists(saved):
                    return FileResponse(saved, media_type=detect_image_media_type(saved))
                return Response(content=p_bytes, media_type=detect_image_media_type(p_bytes))

    # 4. Fallback: stylized SVG badge
    return Response(content=generate_svg_cover(series["title"]), media_type="image/svg+xml")

@app.post("/api/series/{series_id}/sync-search-cover")
async def sync_search_cover_endpoint(series_id: int):
    """Force lookup the verified cover from Global Search and update series cover."""
    series = get_series_by_id(series_id)
    if not series:
        return JSONResponse({"success": False, "error": "Series not found"}, status_code=404)

    safe_title = re.sub(r'[\\/*?:"<>|]', "", series["title"])
    series_dir = os.path.join(DOWNLOADS_DIR, safe_title)

    from core.search.clustering import resolve_cover_from_search
    search_cover = resolve_cover_from_search(series["title"])
    if not search_cover:
        return JSONResponse({"success": False, "error": "Could not discover cover in Global Search"}, status_code=404)

    saved = save_series_cover_locally(
        series_id=series_id,
        series_dir=series_dir,
        cover_url=search_cover,
        series_title=series["title"]
    )
    if saved and os.path.exists(saved):
        return {"success": True, "cover_url": search_cover, "cover_path": saved}
    return JSONResponse({"success": False, "error": "Failed to download search cover"}, status_code=500)


@app.post("/api/library/{series_id}/open-folder")
async def open_series_folder(series_id: int):
    series = get_series_by_id(series_id)
    if not series:
        return JSONResponse({"success": False, "error": "Series not found"}, status_code=404)
        
    safe_title = re.sub(r'[\\/*?:"<>|]', "", series.get("slug") or series.get("title") or "series")
    storage_dir = os.path.join(DOWNLOADS_DIR, safe_title)
    chapters = get_chapters_for_series(series_id)
    for c in chapters:
        if c.get("file_path") and os.path.exists(os.path.dirname(c["file_path"])):
            storage_dir = os.path.dirname(c["file_path"])
            break
            
    os.makedirs(storage_dir, exist_ok=True)
    import subprocess
    try:
        if sys.platform == "win32":
            os.startfile(storage_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", storage_dir])
        else:
            subprocess.Popen(["xdg-open", storage_dir])
        return {"success": True, "path": os.path.abspath(storage_dir)}
    except Exception as e:
        return {"success": False, "error": str(e), "path": os.path.abspath(storage_dir)}

@app.delete("/api/library/{series_id}")
async def remove_series(series_id: int):
    series = get_series_by_id(series_id)
    if not series:
        return JSONResponse({"success": False, "error": "Series not found"}, status_code=404)

    # 1. Delete all chapter files on disk
    chapters = get_chapters_for_series(series_id)
    for c in chapters:
        fpath = c.get("file_path")
        if fpath and os.path.exists(fpath):
            try:
                if os.path.isdir(fpath):
                    shutil.rmtree(fpath, ignore_errors=True)
                else:
                    os.remove(fpath)
            except Exception:
                pass

    # 2. Delete series folder if it exists
    safe_title = re.sub(r'[\\/*?:"<>|]', "", series.get("slug") or series.get("title") or "")
    if safe_title:
        series_dir = os.path.join(DOWNLOADS_DIR, safe_title)
        if os.path.exists(series_dir):
            shutil.rmtree(series_dir, ignore_errors=True)

    # 3. Delete cover if local file
    cover_path = series.get("cover_path")
    if cover_path and os.path.exists(cover_path):
        try:
            os.remove(cover_path)
        except Exception:
            pass

    ok = delete_series(series_id)
    return {"success": ok}

@app.delete("/api/chapters/{chapter_id}")
async def remove_chapter(chapter_id: int):
    chapter = get_chapter_by_id(chapter_id)
    if not chapter:
        return JSONResponse({"success": False, "error": "Chapter not found"}, status_code=404)

    fpath = chapter.get("file_path")
    if fpath and os.path.exists(fpath):
        try:
            if os.path.isdir(fpath):
                shutil.rmtree(fpath, ignore_errors=True)
            else:
                os.remove(fpath)
        except Exception:
            pass

    ok = delete_chapter(chapter_id)
    return {"success": ok, "chapter_id": chapter_id}

@app.post("/api/library/{series_id}/check-update")
async def check_single_manhua_update(series_id: int):
    """Check for new chapters for a specific manhua and automatically queue them."""
    from core.updater import check_and_enqueue_series_update
    result = await check_and_enqueue_series_update(
        series_id=series_id,
        queue_manager=download_queue_manager
    )
    return result

@app.post("/api/library/update")
async def trigger_library_update(background_tasks: BackgroundTasks):
    from core.updater import run_library_update

    async def update_task():
        try:
            res = await run_library_update(queue_manager=download_queue_manager)
            print(f"[LibraryUpdate] Library update check complete: {res.get('total_new_chapters', 0)} new chapters queued across {res.get('updated_series_count', 0)} series.", file=sys.stderr)
        except Exception as e:
            print(f"[LibraryUpdate] Error during library update: {e}", file=sys.stderr)

    background_tasks.add_task(update_task)
    return {
        "success": True,
        "message": "Checking library series for updates... Any newly available chapters will be added to the Download Queue."
    }

# --- Settings & Webhook Endpoints ---

@app.get("/api/settings")
async def get_app_settings():
    return {"success": True, "settings": get_all_settings()}

@app.post("/api/settings")
async def save_app_settings(settings: Dict[str, Any]):
    for k, v in settings.items():
        set_setting(k, str(v))
    return {"success": True}

@app.post("/api/settings/test-notification")
async def test_notification_channel(data: Dict[str, str]):
    channel = data.get("channel", "discord")
    target = data.get("target", "")
    ok = send_test_alert(channel, target)
    return {"success": ok}

# --- In-App Web Reader Endpoints ---

@app.get("/api/chapter/{chapter_id}/pages")
async def get_chapter_pages_info(chapter_id: int):
    chap = get_chapter_by_id(chapter_id)
    if not chap or not chap.get("file_path") or not os.path.exists(chap["file_path"]):
        return JSONResponse({"success": False, "error": "Chapter file not found on disk."}, status_code=404)

    series = get_series_by_id(chap["series_id"])
    all_chaps = get_chapters_for_series(chap["series_id"])

    prev_id = None
    next_id = None
    for i, c in enumerate(all_chaps):
        if c["id"] == chapter_id:
            if i > 0:
                prev_id = all_chaps[i - 1]["id"]
            if i + 1 < len(all_chaps):
                next_id = all_chaps[i + 1]["id"]
            break

    total_pages = await asyncio.to_thread(get_chapter_page_count, chap["file_path"], chap["file_format"])
    page_urls = [f"/api/chapter/{chapter_id}/page/{idx}" for idx in range(total_pages)]

    return {
        "success": True,
        "chapter_id": chapter_id,
        "series_title": series["title"] if series else "Series",
        "chapter_title": chap.get("title") or f"Chapter {chap['chapter_num']}",
        "chapter_num": chap["chapter_num"],
        "total_pages": total_pages,
        "last_read_page": chap.get("last_read_page", 0),
        "prev_chapter_id": prev_id,
        "next_chapter_id": next_id,
        "pages": page_urls
    }

@app.get("/api/chapter/{chapter_id}/page/{page_index}")
def serve_chapter_page(chapter_id: int, page_index: int):
    chap = get_chapter_by_id(chapter_id)
    if not chap or not chap.get("file_path"):
        return JSONResponse({"error": "Chapter not found"}, status_code=404)

    img_bytes = get_chapter_page_bytes(chap["file_path"], chap["file_format"], page_index)
    if not img_bytes:
        return JSONResponse({"error": "Page image could not be decoded."}, status_code=404)

    media_type = "image/webp" if (len(img_bytes) >= 12 and img_bytes[:4] == b"RIFF" and img_bytes[8:12] == b"WEBP") else "image/jpeg"
    return Response(content=img_bytes, media_type=media_type)



@app.post("/api/chapter/{chapter_id}/progress")
async def update_reading_state(chapter_id: int, req: ProgressUpdateRequest):
    update_reading_progress(chapter_id, req.read_status, req.last_read_page)
    # If reading or completed, sync progress to configured trackers
    if req.read_status >= 1:
        chap = get_chapter_by_id(chapter_id)
        if chap:
            series = get_series_by_id(chap["series_id"])
            if series:
                try:
                    sync_trackers(
                        title=series["title"],
                        chapter_num=chap["chapter_num"],
                        anilist_id=series.get("anilist_id"),
                        mal_id=series.get("mal_id")
                    )
                except Exception:
                    pass
    return {"success": True}

@app.get("/api/download/file/{chapter_id}")
async def download_chapter_file(chapter_id: int):
    chap = get_chapter_by_id(chapter_id)
    if not chap or not chap.get("file_path") or not os.path.exists(chap["file_path"]):
        return JSONResponse({"error": "File not found"}, status_code=404)
    filename = os.path.basename(chap["file_path"])
    media_type = "application/x-cbz" if chap["file_format"] == "cbz" else "application/pdf"
    return FileResponse(chap["file_path"], media_type=media_type, filename=filename)

# --- OPDS 1.2 Catalog Endpoints (Tachiyomi / Mihon / Reader Apps) ---

@app.get("/opds/v1.2/catalog", response_class=Response)
async def opds_root_catalog(request: Request):
    base_url = str(request.base_url).rstrip('/')
    series_list = get_all_series()

    entries = []
    for s in series_list:
        cover_tag = f'<link rel="http://opds-spec.org/image" href="{s["cover_url"]}" type="image/jpeg"/>' if s.get("cover_url") else ''
        entries.append(f"""
  <entry>
    <title>{s["title"]}</title>
    <id>urn:manhua:series:{s["id"]}</id>
    <updated>{s.get("updated_at") or "2026-10-10T00:00:00Z"}</updated>
    <content type="text">{s.get("synopsis") or s["title"]}</content>
    <link rel="subsection" href="{base_url}/opds/v1.2/series/{s["id"]}" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
    {cover_tag}
  </entry>""")

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:manhua:catalog</id>
  <title>Universal Manhua Extractor Library</title>
  <updated>2026-10-10T12:00:00Z</updated>
  <link rel="self" href="{base_url}/opds/v1.2/catalog" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  <link rel="start" href="{base_url}/opds/v1.2/catalog" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  {''.join(entries)}
</feed>"""
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog")

@app.get("/opds/v1.2/series/{series_id}", response_class=Response)
async def opds_series_feed(series_id: int, request: Request):
    base_url = str(request.base_url).rstrip('/')
    series = get_series_by_id(series_id)
    if not series:
        return JSONResponse({"error": "Series not found"}, status_code=404)

    chapters = get_chapters_for_series(series_id)
    entries = []
    for c in chapters:
        if c.get("file_path") and os.path.exists(c["file_path"]):
            media_type = "application/x-cbz" if c["file_format"] == "cbz" else "application/pdf"
            entries.append(f"""
  <entry>
    <title>{series["title"]} - Chapter {c["chapter_num"]}</title>
    <id>urn:manhua:chapter:{c["id"]}</id>
    <updated>{c.get("downloaded_at") or "2026-10-10T00:00:00Z"}</updated>
    <link rel="http://opds-spec.org/acquisition" href="{base_url}/api/download/file/{c["id"]}" type="{media_type}"/>
  </entry>""")

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:manhua:series:{series_id}</id>
  <title>{series["title"]}</title>
  <updated>2026-10-10T12:00:00Z</updated>
  <link rel="self" href="{base_url}/opds/v1.2/series/{series_id}" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
  {''.join(entries)}
</feed>"""
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog")

# --- Diagnostic Lab Endpoints ---

@app.post("/api/lab/test")
async def test_site_compatibility(req: TestSiteRequest):
    url = req.url.strip()
    parsed = urlparse(url)
    domain = parsed.netloc

    try:
        res = dispatcher.analyze_url(url)
        if res.get("success"):
            panels = res.get("panel_count", 0)
            next_found = 1 if res.get("next_chapter_url") else 0
            status = "PASS" if panels >= 5 else "PARTIAL"

            record_site_diagnostic(
                url=url,
                domain=domain,
                engine_detected=res.get("engine_name"),
                status=status,
                panels_found=panels,
                next_chapter_found=next_found,
                protection="Cloudflare/Passed",
                notes=f"Detected {panels} panels cleanly using {res.get('engine_name')}"
            )
            return {"success": True, "diagnostic": res}
        else:
            status = "BLOCKED" if res.get("status_code") in (403, 503) else "FAILED"
            record_site_diagnostic(
                url=url,
                domain=domain,
                engine_detected="Unknown",
                status=status,
                protection=f"HTTP {res.get('status_code')}",
                notes=res.get("error", "Failed")
            )
            return {"success": False, "diagnostic": res}
    except Exception as e:
        record_site_diagnostic(
            url=url,
            domain=domain,
            engine_detected="None",
            status="FAILED",
            protection="Connection Error",
            notes=str(e)
        )
        return {"success": False, "error": str(e)}

@app.get("/api/lab/sites")
async def list_diagnostic_sites():
    records = get_all_site_diagnostics()
    return {"success": True, "diagnostics": records}


# --- Reading Tracker Endpoints (AniList & MyAnimeList) ---

@app.post("/api/tracker/verify/anilist")
async def verify_anilist(req: VerifyTrackerRequest):
    res = verify_anilist_token(req.token)
    return res

@app.post("/api/tracker/verify/mal")
async def verify_mal(req: VerifyTrackerRequest):
    res = verify_mal_token(req.token)
    return res

@app.post("/api/tracker/sync/{chapter_id}")
async def manual_sync_chapter(chapter_id: int):
    chap = get_chapter_by_id(chapter_id)
    if not chap:
        return JSONResponse({"success": False, "error": "Chapter not found"}, status_code=404)
    series = get_series_by_id(chap["series_id"])
    if not series:
        return JSONResponse({"success": False, "error": "Series not found"}, status_code=404)

    results = sync_trackers(
        title=series["title"],
        chapter_num=chap["chapter_num"],
        anilist_id=series.get("anilist_id"),
        mal_id=series.get("mal_id")
    )
    return {"success": True, "results": results}


# --- Promotional & Ad Page Filter Endpoints ---

@app.get("/api/promos")
async def list_promo_signatures():
    sigs = get_all_promo_signatures()
    return {"success": True, "signatures": sigs}

@app.post("/api/promos")
async def create_promo_signature(req: PromoSignatureRequest):
    sig_id = add_promo_signature(phash=req.phash, label=req.label, match_threshold=req.threshold)
    return {"success": True, "id": sig_id}

@app.delete("/api/promos/{signature_id}")
async def remove_promo_signature(signature_id: int):
    ok = delete_promo_signature(signature_id)
    return {"success": ok}

@app.post("/api/promos/mark")
async def mark_page_as_promo(req: MarkPromoRequest):
    chap = get_chapter_by_id(req.chapter_id)
    if not chap or not chap.get("file_path"):
        return JSONResponse({"success": False, "error": "Chapter not found"}, status_code=404)

    page_bytes = get_chapter_page_bytes(chap["file_path"], chap["file_format"], req.page_index)
    if not page_bytes:
        return JSONResponse({"success": False, "error": "Could not extract page bytes"}, status_code=400)

    phash = compute_perceptual_hash(page_bytes)
    if not phash:
        return JSONResponse({"success": False, "error": "Could not compute perceptual hash"}, status_code=400)

    sig_id = add_promo_signature(phash=phash, label=req.label, match_threshold=req.threshold)
    return {"success": True, "id": sig_id, "phash": phash}


# --- Anti-Bot & Sidecar Endpoints ---

@app.post("/api/settings/test-flaresolverr")
async def test_flaresolverr_conn(data: Dict[str, str]):
    endpoint = data.get("url", "http://localhost:8191/v1")
    from extractors.browser_sidecar import is_flaresolverr_available
    ok = is_flaresolverr_available(endpoint)
    return {"success": ok}


@app.post("/api/series/{series_id}/refresh-metadata")
async def refresh_series_meta(series_id: int):
    s = get_series_by_id(series_id)
    if not s:
        return JSONResponse({"success": False, "error": "Series not found"}, status_code=404)
    from core.metadata import fetch_rich_metadata
    meta = fetch_rich_metadata(s["title"])
    if meta:
        update_series_rich_metadata(series_id, meta)
        updated = get_series_by_id(series_id)
        return {"success": True, "series": dict(updated)}
    return {"success": False, "error": "No metadata found"}


# --- AI Super-Resolution Endpoints ---

@app.get("/api/settings/upscaler-status")
async def get_upscaler_status():
    from core.upscaler import get_available_upscalers, is_upscaler_api_available, DEFAULT_UPSCALER_URL
    endpoint = get_setting("ai_upscaler_url", DEFAULT_UPSCALER_URL)
    status = get_available_upscalers()
    status["api_online"] = is_upscaler_api_available(endpoint)
    return {"success": True, "status": status, "endpoint": endpoint}


@app.post("/api/settings/test-upscaler")
async def test_upscaler_conn(data: Dict[str, str]):
    from core.upscaler import is_upscaler_api_available, DEFAULT_UPSCALER_URL
    endpoint = data.get("url") or get_setting("ai_upscaler_url", DEFAULT_UPSCALER_URL)
    ok = is_upscaler_api_available(endpoint)
    return {"success": ok}


# --- Mobile LAN Discovery & OPDS Info ---

def get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.get("/api/network/info")
async def get_network_info(request: Request):
    lan_ip = get_local_ip()
    port = request.url.port or 8000
    scheme = request.url.scheme or "http"
    return {
        "success": True,
        "lan_ip": lan_ip,
        "port": port,
        "web_url": f"{scheme}://{lan_ip}:{port}",
        "opds_url": f"{scheme}://{lan_ip}:{port}/opds/v1.2/catalog"
    }


# =====================================================================
# --- Cross-Device Backup & Multi-Volume Sync Endpoints ---
# =====================================================================

backup_state: Dict[str, Any] = {
    "is_running": False,
    "action": "idle",       # "idle", "export", "import"
    "job_id": None,
    "current_batch": 0,
    "total_batches": 0,
    "current_step": 0,
    "total_steps": 0,
    "percent": 0.0,
    "message": "Ready",
    "status": "idle",       # "idle", "running", "completed", "error"
    "batch_files": [],
    "error": None,
    "last_result": None
}


class BackupExportRequest(BaseModel):
    mode: str = "batched"  # "single" or "batched"
    batch_size_mb: int = 1450
    include_files: bool = True


def run_backup_export_worker(job_id: str, plan: Dict[str, Any], include_files: bool):
    global backup_state
    try:
        batches = plan.get("batches", [])
        total_batches = len(batches)
        total_chapters = plan.get("total_chapters", 0)
        generated_files = []
        overall_chapter_index = 0

        for b in batches:
            b_idx = b["batch_index"]
            b_items = b["items"]
            filename = f"{job_id}_part{b_idx}.zip" if total_batches > 1 else f"{job_id}.zip"
            zip_dest = os.path.join(BACKUPS_DIR, filename)

            backup_state["current_batch"] = b_idx
            backup_state["total_batches"] = total_batches
            backup_state["message"] = f"Exporting Part {b_idx} of {total_batches} ({b.get('formatted_size', '0 B')})..."

            def on_progress(cur: int, tot: int, msg: str):
                backup_state["current_step"] = overall_chapter_index + cur
                backup_state["total_steps"] = max(1, total_chapters)
                backup_state["message"] = msg
                if total_chapters > 0:
                    backup_state["percent"] = round((backup_state["current_step"] / total_chapters) * 100, 1)

            create_backup_batch_file(
                batch_index=b_idx,
                total_batches=total_batches,
                batch_items=b_items,
                output_zip_path=zip_dest,
                include_files=include_files,
                progress_callback=on_progress
            )
            overall_chapter_index += len(b_items)
            generated_files.append(f"/api/backup/download/{filename}")

            # Auto-save to Android public Downloads and trigger MediaScanner
            if os.environ.get("MANHUA_IS_ANDROID"):
                try:
                    from com.manhua.extractor import FileUtils
                    from com.chaquo.python import Python
                    from java.io import File as JavaFile
                    ctx = Python.getPlatform().getApplication()
                    FileUtils.saveZipToPublicDownloads(ctx, JavaFile(zip_dest))
                except Exception as ex:
                    print(f"[Backup] Auto-save note: {ex}")

        backup_state["status"] = "completed"
        backup_state["is_running"] = False
        backup_state["percent"] = 100.0
        backup_state["message"] = f"Export completed: {len(generated_files)} archive(s) ready."
        backup_state["batch_files"] = generated_files
        backup_state["last_result"] = {
            "success": True,
            "job_id": job_id,
            "total_batches": total_batches,
            "batch_files": generated_files
        }
    except Exception as e:
        backup_state["status"] = "error"
        backup_state["is_running"] = False
        backup_state["error"] = str(e)
        backup_state["message"] = f"Export failed: {str(e)}"


@app.get("/api/backup/estimate")
async def estimate_backup(batch_size_mb: Optional[int] = 1450):
    target_bytes = (batch_size_mb or 1450) * 1024 * 1024
    plan = estimate_backup_batches(target_batch_bytes=target_bytes)
    return {
        "success": True,
        "total_series": plan["total_series"],
        "total_chapters": plan["total_chapters"],
        "total_size_bytes": plan["total_size_bytes"],
        "total_size_formatted": plan["total_size_formatted"],
        "batch_count": plan["batch_count"],
        "batches_1_5gb": plan["batch_count"],
        "batches": [
            {
                "batch_index": b["batch_index"],
                "total_batches": b["total_batches"],
                "batch_label": b["batch_label"],
                "chapter_count": b["chapter_count"],
                "uncompressed_bytes": b["uncompressed_bytes"],
                "formatted_size": b["formatted_size"]
            }
            for b in plan.get("batches", [])
        ]
    }


@app.post("/api/backup/export")
async def export_backup(req: BackupExportRequest):
    global backup_state
    if backup_state["is_running"]:
        return JSONResponse(
            {"success": False, "error": "A backup task is already active."},
            status_code=409
        )

    # Calculate target batch size in bytes
    if req.mode == "single":
        target_bytes = 100 * 1024 * 1024 * 1024  # 100 GB ceiling so everything fits into 1 batch
    else:
        target_bytes = max(10, req.batch_size_mb) * 1024 * 1024

    plan = estimate_backup_batches(target_batch_bytes=target_bytes)
    total_batches = plan["batch_count"]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    job_id = f"bkp_{timestamp}"

    # Precalculate batch filenames & download URLs
    filenames = []
    for b in plan.get("batches", []):
        b_idx = b["batch_index"]
        fn = f"{job_id}_part{b_idx}.zip" if total_batches > 1 else f"{job_id}.zip"
        filenames.append(fn)

    batch_urls = [f"/api/backup/download/{fn}" for fn in filenames]

    # Initialize progress tracker
    backup_state["is_running"] = True
    backup_state["action"] = "export"
    backup_state["job_id"] = job_id
    backup_state["current_batch"] = 1 if total_batches > 0 else 0
    backup_state["total_batches"] = total_batches
    backup_state["current_step"] = 0
    backup_state["total_steps"] = plan["total_chapters"]
    backup_state["percent"] = 0.0
    backup_state["message"] = f"Export scheduled for {total_batches} batch(es)"
    backup_state["status"] = "running"
    backup_state["batch_files"] = batch_urls
    backup_state["error"] = None
    backup_state["last_result"] = None

    # Spawn daemon worker thread
    t = threading.Thread(
        target=run_backup_export_worker,
        args=(job_id, plan, req.include_files),
        daemon=True
    )
    t.start()

    return {
        "success": True,
        "job_id": job_id,
        "total_batches": total_batches,
        "batch_files": batch_urls
    }


@app.get("/api/backup/status")
@app.get("/api/backup/progress")
async def get_backup_status():
    return {
        "success": True,
        "is_running": backup_state["is_running"],
        "action": backup_state["action"],
        "job_id": backup_state["job_id"],
        "current_batch": backup_state["current_batch"],
        "total_batches": backup_state["total_batches"],
        "current_step": backup_state["current_step"],
        "total_steps": backup_state["total_steps"],
        "percent": backup_state["percent"],
        "message": backup_state["message"],
        "status": backup_state["status"],
        "batch_files": backup_state["batch_files"],
        "error": backup_state["error"],
        "last_result": backup_state["last_result"]
    }


@app.get("/api/backup/download/{filename}")
async def download_backup_file(filename: str):
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".zip"):
        return JSONResponse({"success": False, "error": "Invalid archive name"}, status_code=400)
    file_path = os.path.join(BACKUPS_DIR, safe_name)
    if not os.path.exists(file_path):
        return JSONResponse({"success": False, "error": "Archive file not found"}, status_code=404)
    return FileResponse(
        file_path,
        media_type="application/zip",
        filename=safe_name
    )


@app.post("/api/backup/import")
async def import_backup(file: UploadFile = File(...)):
    global backup_state
    if backup_state["is_running"]:
        return JSONResponse(
            {"success": False, "error": "Another backup operation is currently active."},
            status_code=409
        )

    if not file.filename or not file.filename.lower().endswith(".zip"):
        return JSONResponse(
            {"success": False, "error": "Uploaded file must be a valid .zip backup archive."},
            status_code=400
        )

    staging_upload = os.path.join(
        BACKUPS_DIR,
        f".staging_upload_{os.getpid()}_{int(datetime.now(timezone.utc).timestamp())}.zip"
    )

    backup_state["is_running"] = True
    backup_state["action"] = "import"
    backup_state["status"] = "running"
    backup_state["message"] = f"Streaming upload: {file.filename}..."
    backup_state["current_step"] = 0
    backup_state["total_steps"] = 100
    backup_state["percent"] = 0.0

    try:
        # Stream chunks (64 KB) directly to disk to prevent RAM blowup on mobile
        with open(staging_upload, "wb") as f_out:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                f_out.write(chunk)

        # Inspect and validate ZIP structure & Zip-Slip defense
        backup_state["message"] = "Verifying backup archive & manifest..."
        inspection = inspect_backup_archive(staging_upload)
        if not inspection.get("success"):
            return JSONResponse(
                {"success": False, "error": f"Invalid backup archive: {inspection.get('error')}"},
                status_code=400
            )

        manifest = inspection["manifest"]
        total_ch = manifest.get("stats", {}).get("chapter_count", 1)
        backup_state["total_steps"] = max(1, total_ch)

        def on_import_progress(cur: int, tot: int, msg: str):
            backup_state["current_step"] = cur
            backup_state["total_steps"] = max(1, tot)
            backup_state["message"] = msg
            if tot > 0:
                backup_state["percent"] = round((cur / tot) * 100, 1)

        # Perform restoration in a worker thread to keep event loop responsive
        result = await asyncio.to_thread(
            restore_backup_archive,
            staging_upload,
            downloads_dir=DOWNLOADS_DIR,
            progress_callback=on_import_progress
        )

        if not result["success"]:
            backup_state["status"] = "error"
            backup_state["error"] = result.get("error")
            return JSONResponse({"success": False, "error": result.get("error")}, status_code=400)

        folders_synced = result.get("folders_synced", 0)
        folders_msg = f", {folders_synced} groups synced" if folders_synced else ""
        backup_state["status"] = "completed"
        backup_state["percent"] = 100.0
        backup_state["message"] = (
            f"Successfully restored {result['batch_label']}: "
            f"{result['chapters_imported']} chapters imported, {result['series_synced']} series synced{folders_msg}."
        )
        backup_state["last_result"] = result

        return {
            "success": True,
            "batch_info": result.get("batch_label"),
            "batch_label": result.get("batch_label"),
            "series_synced": result.get("series_synced"),
            "chapters_imported": result.get("chapters_imported"),
            "chapters_skipped_duplicate": result.get("chapters_skipped_duplicate"),
            "folders_synced": folders_synced,
            "storage_freed_or_used": f"+{format_bytes(result.get('uncompressed_bytes', 0))}"
        }

    except Exception as e:
        backup_state["status"] = "error"
        backup_state["error"] = str(e)
        backup_state["message"] = f"Import failed: {str(e)}"
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    finally:
        backup_state["is_running"] = False
        if os.path.exists(staging_upload):
            try:
                os.remove(staging_upload)
            except Exception:
                pass


@app.get("/api/backup/list")
async def list_backup_archives():
    files = []
    if os.path.exists(BACKUPS_DIR):
        for f in sorted(os.listdir(BACKUPS_DIR)):
            if f.endswith(".zip") and not f.startswith("."):
                fp = os.path.join(BACKUPS_DIR, f)
                try:
                    sz = os.path.getsize(fp)
                    mtime = os.path.getmtime(fp)
                    files.append({
                        "filename": f,
                        "url": f"/api/backup/download/{f}",
                        "size_bytes": sz,
                        "size_formatted": format_bytes(sz),
                        "created_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                    })
                except Exception:
                    pass
    return {"success": True, "files": files}


@app.post("/api/backup/clear")
async def clear_backup_cache():
    purged_count = 0
    freed_bytes = 0
    if os.path.exists(BACKUPS_DIR):
        for f in os.listdir(BACKUPS_DIR):
            if f.endswith(".zip") and not f.startswith("."):
                fp = os.path.join(BACKUPS_DIR, f)
                try:
                    freed_bytes += os.path.getsize(fp)
                    os.remove(fp)
                    purged_count += 1
                except Exception:
                    pass
    return {
        "success": True,
        "purged_count": purged_count,
        "freed_bytes": freed_bytes,
        "freed_formatted": format_bytes(freed_bytes)
    }


@app.get("/api/backup/folder-info")
async def get_backup_folder_info():
    """Return device backup directory path."""
    return {
        "success": True,
        "backups_dir": BACKUPS_DIR,
        "downloads_dir": DOWNLOADS_DIR,
        "is_android": bool(os.environ.get("MANHUA_IS_ANDROID"))
    }


@app.post("/api/backup/open-folder")
async def open_backup_folder():
    """Request opening the device backup folder in system file manager."""
    try:
        if os.environ.get("MANHUA_IS_ANDROID"):
            try:
                from com.manhua.extractor import FileUtils
                from com.chaquo.python import Python
                ctx = Python.getPlatform().getApplication()
                FileUtils.openBackupFolder(ctx)
                return {"success": True, "path": BACKUPS_DIR, "message": "Opened device file manager"}
            except Exception as e:
                return {"success": True, "path": BACKUPS_DIR, "message": f"Backups at: {BACKUPS_DIR}"}
        else:
            import platform, subprocess
            sys_name = platform.system()
            if sys_name == "Windows":
                os.startfile(BACKUPS_DIR)
            elif sys_name == "Darwin":
                subprocess.Popen(["open", BACKUPS_DIR])
            else:
                subprocess.Popen(["xdg-open", BACKUPS_DIR])
            return {"success": True, "path": BACKUPS_DIR, "message": "Opened folder"}
    except Exception as e:
        return {"success": False, "error": str(e), "path": BACKUPS_DIR}







