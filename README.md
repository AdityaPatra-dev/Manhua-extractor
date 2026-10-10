# ⚡ Universal Manhua Extractor & Library

A high-performance, modular manga/manhua/manhwa downloader and local library manager engineered to support **95%+ of online manga platforms** via a 5-engine auto-detection architecture. Comes with both an interactive CLI and a modern Web GUI.

---

## 🌟 Key Features

* **5 Specialized Extraction Engines**:
  1. **WordPress Madara Engine** (~50% of manhua sites: Toonily, MangaTX, KunManga, ZinManga, etc.)
  2. **MangaStream / Themeia / Liliana Engine** (~25% of scanlator sites: ManhuaPlus, Luminous, Void, etc.)
  3. **Modern SSR / Astro / Next.js Engine** (~15%: Asura Scans Astro v7, Flame Comics Next.js)
  4. **Aggregator Engine** (Manganato, Chapmanganato, MangaBuddy with anti-hotlink referer spoofing)
  5. **Universal Heuristic Fallback** (Density-based panel extraction for custom/unknown themes)
* **Cloudflare Turnstile Bypass Sidecar**:
  * Seamlessly delegates interactive Turnstile checkbox challenges to an external **FlareSolverr** container (`http://localhost:8191/v1`) or headless Playwright stealth driver without bloat.
* **MangaDex API Rich Metadata & `<ComicInfo.xml>`**:
  * Automatically resolves official author, artist, genres, tags, publication year, and synopsis from **MangaDex API** (with AniList fallback).
  * Injects fully schema-compliant `<ComicInfo.xml>` into CBZ archives for immediate **Komga**, **Kavita**, and **ComicRack** recognition.
* **Next-Gen WebP Direct Panel Compression**:
  * Supports high-efficiency WebP re-encoding yielding **40% to 75% file size reduction** over JPEG while retaining ultra-sharp line art and smooth gradients.
* **AI Super-Resolution Upscaling (Waifu2x / Real-ESRGAN)**:
  * Microservice connector to upscale legacy 720p scans into crisp 1440p/4K panels via external neural network containers or local CLI binaries, with pure Lanczos-4 high-quality fallback.
* **Kindle & E-Ink Smart Gutter Strip Slicer**:
  * Automatically scans continuous vertical webtoon ribbons ($1080 \times 16000\text{ px}$) for natural whitespace panel gaps, splitting them into standard book-ratio pages ($1:1.414$).
* **Panel-Level Staging Cache & Resume**:
  * Never re-download panels after an interruption: individual panels are cached in `.staging/` and resumed instantly.
* **Perceptual Hashing (128-bit pHash) Ad Trimming**:
  * Automatically fingerprints and strips recurring site promotional banners, Discord credit pages, and scanlator ads using composite `dHash + aHash`.
* **Reading Tracker Synchronization (Scrobbler)**:
  * Synchronizes reading progress directly to **AniList** (GraphQL) and **MyAnimeList** (API v2).
* **Automated Library Updater & Push Alerts**:
  * Built-in background update daemon scans your library for newly released chapters and triggers rich alerts via **Discord Webhooks**, **Telegram Bots**, or **Ntfy**.
* **Modern Web GUI (`http://localhost:8000`) & In-App Web Reader**:
  * Real-time Server-Sent Events (SSE) download progress monitor.
  * Visual bookshelf with cover cards, metadata viewer, and chapter counts.
  * Continuous fullscreen vertical webtoon reader with reading position persistence and 1-click ad marking.
* **📡 OPDS 1.2 / 2.0 Catalog Feed (`/opds/v1.2/catalog`)**:
  * Connect mobile reader apps (**Tachiyomi**, **Mihon**, **Tachimanga**, **Chunky**, **Moon+ Reader**, **Panels**) directly over local Wi-Fi to browse and stream your manga library.

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/AdityaPatra-dev/Manhua-extractor.git
cd Manhua-extractor

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Web GUI

```bash
python manhua.py --web
```
Open **`http://localhost:8000`** in your browser.

### 3. Interactive CLI Mode

```bash
python manhua.py
```

### 4. Headless Batch Mode

```bash
# Download 5 chapters of a series as high-efficiency WebP CBZ with rich ComicInfo metadata
python manhua.py -U "https://asurascans.com/comics/solo-leveling/chapter/1" -c 5 -f cbz -e webp

# Download and slice for Kindle / E-Ink devices
python manhua.py -U "https://toonily.com/webtoon/tower-of-god/chapter-1" -s -f pdf

# Check and update all series in the library database
python manhua.py --update-library
```

### 5. Run the Automated Unit Test Suite

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

---

## 📁 Project Architecture

```
Manhua-extractor/
├── manhua.py                     # Unified CLI & Web GUI entrypoint
├── app.py                        # FastAPI Backend & SSE streaming manager
├── library.db                    # SQLite Database (Auto-created)
├── requirements.txt              # Dependencies
├── IMPROVEMENTS_AND_ROADMAP.md   # Architectural matrix & roadmap
├── database/
│   ├── __init__.py
│   └── db.py                     # SQLite schema: series, chapters, diagnostics, settings
├── extractors/
│   ├── __init__.py
│   ├── base.py                   # BaseExtractor interface
│   ├── madara.py                 # Engine 1: WordPress Madara Specialist
│   ├── mangastream.py            # Engine 2: MangaStream, Themeia & Liliana AJAX
│   ├── modern_ssr.py             # Engine 3: Astro v7 (Asura) & Next.js (Flame)
│   ├── aggregator.py             # Engine 4: Manganato Referer Spoofing
│   ├── heuristic.py              # Engine 5: Universal Density Fallback
│   ├── dispatcher.py             # Master signature detector & delegator
│   └── browser_sidecar.py        # Cloudflare Turnstile FlareSolverr sidecar
├── core/
│   ├── __init__.py
│   ├── downloader.py             # Async aiohttp streaming with staging resume cache
│   ├── optimizer.py              # Pillow RGBA safe conversion & WebP/JPEG encoding
│   ├── compiler.py               # img2pdf, CBZ (ComicInfo.xml), & page decoders
│   ├── slicer.py                 # Smart whitespace Kindle / E-Ink panel cutter
│   ├── ad_filter.py              # 128-bit perceptual hash (pHash) promo stripper
│   ├── scrobbler.py              # AniList GraphQL & MyAnimeList API v2 sync
│   ├── metadata.py               # MangaDex API rich metadata & ComicInfo generator
│   ├── upscaler.py               # AI Super-Resolution (Waifu2x / Real-ESRGAN / Lanczos)
│   ├── notifier.py               # Discord, Telegram, and Ntfy webhook dispatcher
│   └── updater.py                # Scheduled background library update worker
├── static/
│   ├── index.html                # Single-page Web GUI
│   ├── style.css                 # Responsive dark-mode styling
│   └── app.js                    # SSE live monitor, bookshelf, reader & test lab
└── tests/
    ├── test_matrix.py            # Automated multi-site benchmark runner
    ├── test_v1_3_features.py     # Smart slicer & staging cache tests
    ├── test_v1_4_features.py     # Perceptual hash ad filter & tracker tests
    ├── test_v2_0_features.py     # MangaDex metadata & ComicInfo XML tests
    └── test_v2_1_features.py     # WebP compression & AI upscaling tests
```
