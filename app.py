import os
import re
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from urllib.parse import urlparse

from database.db import (
    init_db,
    get_or_create_series,
    get_all_series,
    get_series_by_id,
    delete_series,
    add_or_update_chapter,
    get_chapters_for_series,
    get_chapter_by_id,
    update_reading_progress,
    record_site_diagnostic,
    get_all_site_diagnostics
)
from extractors.dispatcher import dispatcher
from core.downloader import download_panels_stream
from core.compiler import (
    compile_pdf,
    compile_cbz,
    save_raw_images,
    get_chapter_page_count,
    get_chapter_page_bytes
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Initialize Database
init_db()

app = FastAPI(title="Universal Manhua Extractor & Library")

# Mount static folder
static_path = os.path.join(BASE_DIR, "static")
os.makedirs(static_path, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Global Download State & Progress Queues
download_progress = {
    "is_running": False,
    "current_url": None,
    "series_title": "",
    "chapter_num": 0,
    "current_panel": 0,
    "total_panels": 0,
    "chapter_index": 0,
    "total_chapters": 1,
    "status": "idle",
    "message": "Ready"
}

# --- Request Models ---

class AnalyzeRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    mode: str = "single"  # single, range, crawl_all
    count: int = 1
    format: str = "pdf"   # pdf, cbz, folder
    max_width: int = 1080
    quality: int = 75
    save_dir: Optional[str] = None

class TestSiteRequest(BaseModel):
    url: str

class ProgressUpdateRequest(BaseModel):
    last_read_page: int = 0
    read_status: int = 1

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

async def run_download_job(req: DownloadRequest):
    global download_progress
    download_progress["is_running"] = True
    download_progress["status"] = "starting"
    download_progress["message"] = "Starting extraction..."

    current_url = req.url.strip()
    target_count = req.count if req.mode in ("range", "single") else 999
    if req.mode == "single":
        target_count = 1

    chapters_processed = 0
    base_save_dir = req.save_dir or DOWNLOADS_DIR

    try:
        while current_url and chapters_processed < target_count:
            download_progress["current_url"] = current_url
            download_progress["chapter_index"] = chapters_processed + 1
            download_progress["total_chapters"] = target_count
            download_progress["status"] = "analyzing"
            download_progress["message"] = f"Analyzing chapter {chapters_processed + 1}..."

            # Analyze page
            data = dispatcher.analyze_url(current_url)
            if not data.get("success") or not data.get("pages"):
                download_progress["message"] = f"Failed to extract panels from {current_url}"
                break

            series_title = data.get("series_title") or "Unknown Series"
            series_slug = data.get("series_slug") or re.sub(r'[^a-zA-Z0-9_-]', '_', series_title.lower())
            chapter_num = data.get("chapter_num") or (chapters_processed + 1)
            pages = data.get("pages", [])

            download_progress["series_title"] = series_title
            download_progress["chapter_num"] = chapter_num
            download_progress["total_panels"] = len(pages)
            download_progress["current_panel"] = 0

            # Register/Update in Database
            series_id = get_or_create_series(
                slug=series_slug,
                title=series_title,
                cover_url=data.get("series_cover"),
                source_url=current_url,
                engine=data.get("engine_id")
            )

            # Create series directory
            safe_title = re.sub(r'[\\/*?:"<>|]', "", series_title)
            series_dir = os.path.join(base_save_dir, safe_title)
            os.makedirs(series_dir, exist_ok=True)

            # Progress callback for downloader
            def on_progress(done, total):
                download_progress["current_panel"] = done
                download_progress["total_panels"] = total
                download_progress["status"] = "downloading"
                download_progress["message"] = f"Downloading Ch {chapter_num}: {done}/{total} panels"

            download_progress["status"] = "downloading"
            download_progress["message"] = f"Downloading {len(pages)} panels..."

            # Download panels
            panel_bytes = await download_panels_stream(
                image_urls=pages,
                referer=current_url,
                max_width=req.max_width,
                jpeg_quality=req.quality,
                progress_callback=on_progress
            )

            if not panel_bytes:
                download_progress["message"] = f"Could not download panels for Chapter {chapter_num}"
                break

            # Compile into chosen format
            download_progress["status"] = "compiling"
            download_progress["message"] = f"Compiling Chapter {chapter_num} to {req.format.upper()}..."

            safe_slug = series_slug.replace('-', '_')
            ch_str = f"{chapter_num:g}".replace('.', '_')
            output_file = ""

            if req.format == "pdf":
                output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.pdf")
                compile_pdf(panel_bytes, output_file)
            elif req.format == "cbz":
                output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.cbz")
                compile_cbz(panel_bytes, output_file, series_title=series_title, chapter_num=chapter_num, source_url=current_url)
            else: # folder
                output_file = os.path.join(series_dir, f"Ch_{ch_str}")
                save_raw_images(panel_bytes, output_file)

            file_size = os.path.getsize(output_file) if os.path.exists(output_file) and os.path.isfile(output_file) else 0

            # Record chapter in database
            add_or_update_chapter(
                series_id=series_id,
                chapter_num=chapter_num,
                chapter_slug=f"chapter-{ch_str}",
                title=f"Chapter {chapter_num}",
                source_url=current_url,
                panel_count=len(panel_bytes),
                file_path=output_file,
                file_format=req.format,
                file_size=file_size,
                status="completed"
            )

            chapters_processed += 1
            current_url = data.get("next_chapter_url")

            # Small breather between chapters
            await asyncio.sleep(1)

        download_progress["status"] = "completed"
        download_progress["message"] = f"Successfully downloaded {chapters_processed} chapter(s)!"
    except Exception as e:
        download_progress["status"] = "error"
        download_progress["message"] = f"Error: {str(e)}"
    finally:
        download_progress["is_running"] = False

@app.post("/api/download")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    global download_progress
    if download_progress["is_running"]:
        return JSONResponse({"success": False, "error": "A download task is already in progress."}, status_code=400)

    background_tasks.add_task(run_download_job, req)
    return {"success": True, "message": "Download task launched in background."}

@app.get("/api/download/progress")
async def get_progress_stream(request: Request):
    """Server-Sent Events (SSE) streaming live progress to the frontend."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            payload = json.dumps(download_progress)
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- Library Endpoints ---

@app.get("/api/library")
async def list_library():
    series_list = get_all_series()
    return {"success": True, "series": series_list}

@app.get("/api/library/{series_id}")
async def get_series_detail(series_id: int):
    series = get_series_by_id(series_id)
    if not series:
        return JSONResponse({"success": False, "error": "Series not found"}, status_code=404)
    chapters = get_chapters_for_series(series_id)
    return {"success": True, "series": series, "chapters": chapters}

@app.delete("/api/library/{series_id}")
async def remove_series(series_id: int):
    ok = delete_series(series_id)
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

    total_pages = get_chapter_page_count(chap["file_path"], chap["file_format"])
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
async def serve_chapter_page(chapter_id: int, page_index: int):
    chap = get_chapter_by_id(chapter_id)
    if not chap or not chap.get("file_path"):
        return JSONResponse({"error": "Chapter not found"}, status_code=404)

    img_bytes = get_chapter_page_bytes(chap["file_path"], chap["file_format"], page_index)
    if not img_bytes:
        return JSONResponse({"error": "Page image could not be decoded."}, status_code=404)

    return Response(content=img_bytes, media_type="image/jpeg")

@app.post("/api/chapter/{chapter_id}/progress")
async def update_reading_state(chapter_id: int, req: ProgressUpdateRequest):
    update_reading_progress(chapter_id, req.read_status, req.last_read_page)
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

