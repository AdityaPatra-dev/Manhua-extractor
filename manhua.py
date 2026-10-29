import os
import sys
import re
import argparse
import asyncio
from urllib.parse import urlparse
try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, total=0, desc="", unit=""):
            self.total = total
            self.n = 0
            self.desc = desc
        def refresh(self):
            print(f"\r{self.desc}: {self.n}/{self.total}", end="", flush=True)
        def close(self):
            print()

from database.db import (
    init_db,
    get_or_create_series,
    add_or_update_chapter,
    get_all_promo_signatures,
    update_series_rich_metadata
)
from extractors.dispatcher import dispatcher
from core.downloader import (
    download_panels_stream,
    get_staging_dir,
    cleanup_staging_dir
)
from core.slicer import slice_chapter_panels
from core.ad_filter import filter_chapter_panels
from core.scrobbler import sync_trackers
from core.compiler import compile_pdf, compile_cbz, save_raw_images

DEFAULT_CONCURRENCY = 6


def download_series(
    pasted_url: str,
    total_chapters: int = 1,
    out_format: str = "pdf",
    dest_input: str = "",
    slice_eink: bool = False,
    aspect_ratio: float = 1.414,
    filter_promos: bool = True,
    image_format: str = "jpeg",
    webp_quality: int = 80,
    upscale_scale: int = 1,
    upscale_engine: str = "auto"
):
    """Core download worker supporting resume cache, WebP compression, upscaling, and smart e-ink slicing."""
    print("\n[*] Analyzing page layout and detecting CMS engine...")
    data = dispatcher.analyze_url(pasted_url)
    if not data.get("success") or not data.get("pages"):
        print(f"[-] Error: Could not isolate layout from {pasted_url}")
        print(f"[-] Details: {data.get('error', 'No images found')}")
        return

    series_title = data.get("series_title") or "Unknown Series"
    series_slug = data.get("series_slug")
    if not series_slug or re.search(r'^(?:ch(?:apter)?|ep(?:isode)?)[-_.]?\d+|^\d+(?:\.\d+)?$', str(series_slug), re.I):
        if series_title and series_title != "Unknown Series":
            series_slug = re.sub(r'[^a-zA-Z0-9_-]', '_', series_title.lower()).strip('_')
        else:
            series_slug = series_slug or "series"
    chapter_num = data.get("chapter_num", 1)
    engine_name = data.get("engine_name", "Unknown")
    total_panels = data.get("panel_count", 0)

    print(f"\n[✅] Matched Engine : {engine_name}")
    print(f"[✅] Series Title   : {series_title}")
    print(f"[✅] Chapter        : {chapter_num}")
    print(f"[✅] Isolated Panels: {total_panels}")
    if data.get("next_chapter_url"):
        print(f"[✅] Next Chapter   : {data.get('next_chapter_url')}")

    base_dir = dest_input if dest_input else os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
    safe_folder_name = re.sub(r'[\\/*?:"<>|]', "", series_title)
    series_dir = os.path.join(base_dir, safe_folder_name)

    try:
        os.makedirs(series_dir, exist_ok=True)
    except PermissionError:
        print("\n[!] Error: Cannot write to that folder path. Check storage permissions.")
        return

    # Initialize SQLite database
    init_db()
    series_id = get_or_create_series(
        slug=series_slug,
        title=series_title,
        cover_url=data.get("series_cover"),
        source_url=pasted_url,
        engine=data.get("engine_id")
    )

    print(f"\n[+] Saving to: {series_dir}")
    if slice_eink:
        print(f"[+] E-Ink / Kindle Mode: Enabled (aspect ratio ~{aspect_ratio})")
    print("=" * 65)

    current_url = pasted_url
    for ch_idx in range(total_chapters):
        if not current_url:
            print("\n[!] No further chapters detected. Reached end of series.")
            break

        print(f"\n[+] Processing Chapter {ch_idx + 1} of {total_chapters}: {current_url}")

        if ch_idx > 0:
            ch_data = dispatcher.analyze_url(current_url)
            if not ch_data.get("success") or not ch_data.get("pages"):
                print(f"[-] Could not extract panels for {current_url}. Stopping.")
                break
        else:
            ch_data = data

        current_panels = ch_data.get("pages", [])
        current_ch_num = ch_data.get("chapter_num", ch_idx + 1)
        print(f"[*] Found {len(current_panels)} panels. Downloading concurrently...")

        # Setup progress bar
        pbar = tqdm(total=len(current_panels), desc=f"Ch {current_ch_num} Progress", unit="panel")
        def on_step(done, total):
            pbar.n = done
            pbar.refresh()

        staging_dir = get_staging_dir(base_dir, series_slug, current_ch_num)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        panel_bytes = loop.run_until_complete(
            download_panels_stream(
                image_urls=current_panels,
                referer=current_url,
                concurrency=DEFAULT_CONCURRENCY,
                max_width=1080 if upscale_scale <= 1 else None,
                jpeg_quality=75,
                staging_dir=staging_dir,
                progress_callback=on_step,
                image_format=image_format,
                webp_quality=webp_quality
            )
        )
        pbar.close()

        if not panel_bytes:
            print(f"[-] No panels could be downloaded for Chapter {current_ch_num}.")
            continue

        # Filter recurring promotional / ad pages
        if filter_promos:
            known_sigs = get_all_promo_signatures()
            if known_sigs:
                clean_panels, removed = filter_chapter_panels(panel_bytes, known_signatures=known_sigs)
                if removed > 0:
                    print(f"[*] Trimmed {removed} recurring promotional credit pages.")
                    panel_bytes = clean_panels

        # AI Super-Resolution Upscaling (Waifu2x / Real-ESRGAN / Lanczos)
        if upscale_scale > 1:
            print(f"[*] Upscaling {len(panel_bytes)} panels ({upscale_scale}x using {upscale_engine})...")
            from core.upscaler import upscale_panel
            from database.db import get_setting
            upscaler_url = get_setting("ai_upscaler_url", "http://localhost:5000/upscale")
            panel_bytes = [
                upscale_panel(b, scale=upscale_scale, engine=upscale_engine, endpoint=upscaler_url)
                for b in panel_bytes
            ]
            print(f"[✅] Upscaling complete.")

        # Smart Kindle/E-Ink Slicing for tall webtoon strips
        if slice_eink:
            print(f"[*] Slicing continuous webtoon ribbons into e-ink pages...")
            panel_bytes = slice_chapter_panels(panel_bytes, target_aspect_ratio=aspect_ratio)
            print(f"[*] Formatted into {len(panel_bytes)} readable pages.")


        safe_slug = series_slug.replace('-', '_')
        ch_str = f"{current_ch_num:g}".replace('.', '_')
        output_file = ""

        if out_format == "pdf":
            output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.pdf")
            print(f"[*] Compiling {len(panel_bytes)} panels directly into PDF...")
            compile_pdf(panel_bytes, output_file)
            print(f"[✅] Created Compressed PDF: {output_file}")
        elif out_format == "cbz":
            output_file = os.path.join(series_dir, f"{safe_slug}_Ch_{ch_str}.cbz")
            print(f"[*] Compiling CBZ archive with rich ComicInfo.xml metadata...")
            try:
                from core.metadata import fetch_rich_metadata
                meta = fetch_rich_metadata(series_title)
                update_series_rich_metadata(series_id, meta)
            except Exception:
                meta = None
            compile_cbz(
                panel_bytes,
                output_file,
                series_title=series_title,
                chapter_num=current_ch_num,
                source_url=current_url,
                chapter_title=f"Chapter {current_ch_num}",
                metadata=meta
            )
            print(f"[✅] Created CBZ: {output_file}")
        else:
            output_file = os.path.join(series_dir, f"Ch_{ch_str}")
            save_raw_images(panel_bytes, output_file)
            print(f"[✅] Saved raw images to: {output_file}")

        # Download & compilation verified, clean up staging files
        cleanup_staging_dir(staging_dir)

        file_size = os.path.getsize(output_file) if os.path.exists(output_file) and os.path.isfile(output_file) else 0

        # Log to Database
        add_or_update_chapter(
            series_id=series_id,
            chapter_num=current_ch_num,
            chapter_slug=f"chapter-{ch_str}",
            title=f"Chapter {current_ch_num}",
            source_url=current_url,
            panel_count=len(panel_bytes),
            file_path=output_file,
            file_format=out_format,
            file_size=file_size,
            status="completed"
        )

        # Scrobble reading progress to configured trackers
        try:
            sync_trackers(title=series_title, chapter_num=current_ch_num)
        except Exception:
            pass

        next_url = ch_data.get("next_chapter_url")
        if not next_url and ch_idx + 1 < total_chapters:
            from extractors.heuristic import HeuristicExtractor
            next_url = HeuristicExtractor().extract_next_chapter(None, current_url)
        current_url = next_url

    print("\n" + "=" * 65)
    print(f"[🎉] Run complete! Series and chapters recorded in SQLite library.db.")
    print(f"[📁] Output directory: {series_dir}")
    print("=" * 65)


def run_cli_downloader():
    print("=" * 65)
    print("   UNIVERSAL MANHUA EXTRACTOR & DATABASE (95%+ ENGINE)   ")
    print("=" * 65)

    pasted_url = input("\nPaste the chapter URL:\n> ").strip()
    if not pasted_url:
        print("[-] Error: URL cannot be empty.")
        return

    try:
        total_chapters = int(input("\nHow many chapters do you want to download? (1 = single):\n> ") or "1")
    except ValueError:
        print("[-] Invalid number. Defaulting to 1.")
        total_chapters = 1

    print("\nSelect Output Format:")
    print(" 1 -> Compressed PDF (Default, optimized for mobile/Termux)")
    print(" 2 -> CBZ Comic Archive (With ComicInfo.xml metadata)")
    print(" 3 -> Raw Image Folder (JPEG/WebP)")
    fmt_choice = input("> ").strip()
    fmt_map = {"1": "pdf", "2": "cbz", "3": "folder"}
    out_format = fmt_map.get(fmt_choice, "pdf")

    print("\nSelect Image Encoding:")
    print(" 1 -> Standard JPEG (75% quality)")
    print(" 2 -> High-Efficiency WebP (40-70% smaller file size, Komga/Mihon compatible)")
    enc_choice = input("> ").strip()
    image_format = "webp" if enc_choice == "2" else "jpeg"

    print("\nAI Super-Resolution Upscaling:")
    print(" 1 -> Off (1x Original Resolution)")
    print(" 2 -> 2x AI Upscale (Waifu2x / Real-ESRGAN / Lanczos)")
    upscale_choice = input("> ").strip()
    upscale_scale = 2 if upscale_choice == "2" else 1

    print("\nSmart E-Ink / Kindle Mode:")
    print(" Automatically cut tall vertical webtoon strips into book pages?")
    slice_choice = input(" [y/N]: ").strip().lower()
    slice_eink = slice_choice.startswith("y")

    # Safe destination directory
    print("\nWhere would you like to save your downloads?")
    print(" -> Press [ENTER] for default 'downloads/' directory")
    print(" -> Or type custom location (e.g. /storage/emulated/0/manhua/ )")
    dest_input = input("> ").strip()

    download_series(
        pasted_url=pasted_url,
        total_chapters=total_chapters,
        out_format=out_format,
        dest_input=dest_input,
        slice_eink=slice_eink,
        image_format=image_format,
        upscale_scale=upscale_scale
    )


def main():
    parser = argparse.ArgumentParser(description="Universal Manhua Extractor & Database")
    parser.add_argument("--web", "-w", action="store_true", help="Launch the Web GUI dashboard on http://localhost:8000")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port for the Web GUI (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address for Web GUI (default: 0.0.0.0)")
    parser.add_argument("--test", "-t", type=str, help="Test URL compatibility and print diagnostic report")
    parser.add_argument("--inspect", "-i", type=str, help="Inspect series URL and list all available chapters")
    parser.add_argument("--update-library", "-u", action="store_true", help="Check all library series for new chapters and download them")


    # Batch / headless download arguments
    parser.add_argument("--url", "-U", type=str, help="Direct chapter URL to download in batch mode")
    parser.add_argument("--count", "-c", type=int, default=1, help="Number of chapters to download (default: 1)")
    parser.add_argument("--format", "-f", choices=["pdf", "cbz", "folder"], default="pdf", help="Output format (default: pdf)")
    parser.add_argument("--dest", "-d", type=str, default="", help="Destination folder (default: downloads/)")
    parser.add_argument("--encoding", "-e", choices=["jpeg", "webp"], default="jpeg", help="Image encoding (default: jpeg)")
    parser.add_argument("--upscale", type=int, choices=[1, 2, 4], default=1, help="AI Super-Resolution upscale factor (default: 1 = off)")
    parser.add_argument("--upscale-engine", choices=["auto", "api", "waifu2x", "realesrgan", "lanczos"], default="auto", help="Upscaling engine (default: auto)")
    parser.add_argument("--eink", "-s", action="store_true", help="Slice vertical webtoon strips for Kindle/E-Ink devices")
    parser.add_argument("--trim-promos", action="store_true", default=True, help="Automatically trim known promotional/ad pages (default: True)")
    parser.add_argument("--no-trim-promos", action="store_false", dest="trim_promos", help="Disable promotional page trimming")

    args = parser.parse_args()

    if args.web:
        import uvicorn
        import socket

        def get_local_ip() -> str:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.5)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            except Exception:
                return "127.0.0.1"

        lan_ip = get_local_ip()
        print("\n" + "=" * 68)
        print(" 🚀 Universal Manhua Extractor & Web Reader Server Online")
        print("=" * 68)
        print(f" 💻 Local PC Access      : http://localhost:{args.port}")
        print(f" 📱 Smartphone Wi-Fi     : http://{lan_ip}:{args.port}")
        print(f" 📚 Mihon / Tachiyomi OPDS: http://{lan_ip}:{args.port}/opds/v1.2/catalog")
        print("=" * 68 + "\n")
        uvicorn.run("app:app", host=args.host, port=args.port, reload=True)
    elif args.update_library:
        from core.updater import run_library_update
        print("\n[*] Checking all library series for new releases...")
        init_db()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        def cb(msg):
            print(f" -> {msg}")
        res = loop.run_until_complete(run_library_update(progress_cb=cb))
        print("\n" + "=" * 65)
        print("[🎉] Library Update Complete!")
        print(f" - Series Checked   : {res['total_series']}")
        print(f" - Series Updated   : {res['updated_series_count']}")
        print(f" - Chapters Acquired: {res['total_new_chapters']}")
        print("=" * 65)
    elif args.test:
        print(f"\n[*] Running compatibility test on: {args.test}")
        res = dispatcher.analyze_url(args.test)
        if res.get("success"):
            print("\n[✅] TEST PASSED!")
            print(f" - Engine Matched : {res.get('engine_name')}")
            print(f" - Series Title   : {res.get('series_title')}")
            print(f" - Chapter Number : {res.get('chapter_num')}")
            print(f" - Panels Found   : {res.get('panel_count')}")
            print(f" - Next Chapter   : {res.get('next_chapter_url') or 'Smart Fallback'}")
        else:
            print("\n[❌] TEST FAILED!")
            print(f" - Error: {res.get('error')}")
    elif args.inspect:
        print(f"\n[*] Inspecting series catalog for: {args.inspect}")
        res = dispatcher.inspect_series(args.inspect)
        if res.get("success"):
            print("\n" + "=" * 65)
            print(f"[✅] Series Title   : {res.get('series_title')}")
            print(f"[✅] Engine         : {res.get('engine_name')}")
            print(f"[✅] Total Chapters : {res.get('total_chapters')}")
            print(f"[✅] Local Cached   : {res.get('downloaded_count')}")
            print("=" * 65)
            for c in res.get("chapters", [])[:20]:
                status_icon = "🟢 [Local]" if c.get("is_downloaded") else "⚪ [Online]"
                print(f" {status_icon} {c.get('title')} -> {c.get('url')}")
            if len(res.get("chapters", [])) > 20:
                print(f" ... and {len(res.get('chapters')) - 20} more chapters available")
        else:
            print(f"\n[❌] Failed: {res.get('error')}")
    elif args.url:
        download_series(

            pasted_url=args.url,
            total_chapters=args.count,
            out_format=args.format,
            dest_input=args.dest,
            slice_eink=args.eink,
            filter_promos=args.trim_promos,
            image_format=args.encoding,
            upscale_scale=args.upscale,
            upscale_engine=args.upscale_engine
        )
    else:
        run_cli_downloader()



if __name__ == "__main__":
    main()