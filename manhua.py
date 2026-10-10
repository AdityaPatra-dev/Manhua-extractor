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
    add_or_update_chapter
)
from extractors.dispatcher import dispatcher
from core.downloader import download_panels_stream
from core.compiler import compile_pdf, compile_cbz, save_raw_images

DEFAULT_CONCURRENCY = 6

def run_cli_downloader():
    print("=" * 65)
    print("   UNIVERSAL MANHUA EXTRACTOR & DATABASE (95%+ ENGINE)   ")
    print("=" * 65)

    pasted_url = input("\nPaste the chapter URL:\n> ").strip()
    if not pasted_url:
        print("[-] Error: URL cannot be empty.")
        return

    print("\n[*] Analyzing page layout and detecting CMS engine...")
    data = dispatcher.analyze_url(pasted_url)
    if not data.get("success") or not data.get("pages"):
        print(f"[-] Error: Could not isolate layout from {pasted_url}")
        print(f"[-] Details: {data.get('error', 'No images found')}")
        return

    series_title = data.get("series_title") or "Unknown Series"
    series_slug = data.get("series_slug") or "series"
    chapter_num = data.get("chapter_num", 1)
    engine_name = data.get("engine_name", "Unknown")
    total_panels = data.get("panel_count", 0)

    print(f"\n[✅] Matched Engine : {engine_name}")
    print(f"[✅] Series Title   : {series_title}")
    print(f"[✅] Chapter        : {chapter_num}")
    print(f"[✅] Isolated Panels: {total_panels}")
    if data.get("next_chapter_url"):
        print(f"[✅] Next Chapter   : {data.get('next_chapter_url')}")

    try:
        total_chapters = int(input("\nHow many chapters do you want to download? (1 = single):\n> ") or "1")
    except ValueError:
        print("[-] Invalid number. Defaulting to 1.")
        total_chapters = 1

    print("\nSelect Output Format:")
    print(" 1 -> Compressed PDF (Default, optimized for mobile/Termux)")
    print(" 2 -> CBZ Comic Archive (With ComicInfo.xml metadata)")
    print(" 3 -> Raw JPEG Folder")
    fmt_choice = input("> ").strip()
    fmt_map = {"1": "pdf", "2": "cbz", "3": "folder"}
    out_format = fmt_map.get(fmt_choice, "pdf")

    # Safe destination directory
    print("\nWhere would you like to save your downloads?")
    print(" -> Press [ENTER] for default 'downloads/' directory")
    print(" -> Or type custom location (e.g. /storage/emulated/0/manhua/ )")
    dest_input = input("> ").strip()

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

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        panel_bytes = loop.run_until_complete(
            download_panels_stream(
                image_urls=current_panels,
                referer=current_url,
                concurrency=DEFAULT_CONCURRENCY,
                max_width=1080,
                jpeg_quality=75,
                progress_callback=on_step
            )
        )
        pbar.close()

        if not panel_bytes:
            print(f"[-] No panels could be downloaded for Chapter {current_ch_num}.")
            continue

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
            print(f"[*] Compiling CBZ archive with ComicInfo.xml metadata...")
            compile_cbz(panel_bytes, output_file, series_title=series_title, chapter_num=current_ch_num, source_url=current_url)
            print(f"[✅] Created CBZ: {output_file}")
        else:
            output_file = os.path.join(series_dir, f"Ch_{ch_str}")
            save_raw_images(panel_bytes, output_file)
            print(f"[✅] Saved raw images to: {output_file}")

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

        current_url = ch_data.get("next_chapter_url")

    print("\n" + "=" * 65)
    print(f"[🎉] Run complete! Series and chapters recorded in SQLite library.db.")
    print(f"[📁] Output directory: {series_dir}")
    print("=" * 65)

def main():
    parser = argparse.ArgumentParser(description="Universal Manhua Extractor & Database")
    parser.add_argument("--web", "-w", action="store_true", help="Launch the Web GUI dashboard on http://localhost:8000")
    parser.add_argument("--port", "-p", type=int, default=8000, help="Port for the Web GUI (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address for Web GUI (default: 0.0.0.0)")
    parser.add_argument("--test", "-t", type=str, help="Test URL compatibility and print diagnostic report")

    args = parser.parse_args()

    if args.web:
        import uvicorn
        print(f"\n🚀 Launching Universal Manhua Extractor Web GUI on http://localhost:{args.port}")
        uvicorn.run("app:app", host=args.host, port=args.port, reload=False)
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
    else:
        run_cli_downloader()

if __name__ == "__main__":
    main()