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
* **SQLite Database Integration (`library.db`)**:
  * Tracks series titles, covers, and source URLs.
  * Tracks downloaded chapters, panel counts, file sizes, read/unread states, and formats.
  * Stores site diagnostics and compatibility benchmark history.
* **Modern Web GUI (`http://localhost:8000`)**:
  * **📥 Downloader**: URL input with instant engine detection, chapter range selector, and live Server-Sent Events (SSE) progress bar.
  * **📚 Library & Bookshelf**: Visual bookshelf with cover cards, chapter download stats, search, and series detail modal.
  * **📖 In-App Web Reader**: Fullscreen continuous vertical scroll reader with smooth prefetching, page counter, prev/next buttons, and reading progress tracking.
  * **🧪 Compatibility Lab**: 1-click test bench to benchmark any website against bot protections and layout parsers.
* **📡 OPDS 1.2 / 2.0 Catalog Feed (`/opds/v1.2/catalog`)**:
  * Allows mobile reader apps (**Tachiyomi**, **Mihon**, **Tachimanga**, **Chunky**, **Moon+ Reader**, **Panels**) to connect directly over local Wi-Fi and stream/download your manga library.
* **🛡️ TLS Fingerprint Impersonation (`curl_cffi`)**:
  * Mimics Chrome 124 TLS cipher suites, ALPN, and HTTP/2 handshakes to bypass Cloudflare protection without headless browser overhead.
* **Mobile / Termux Optimized**:
  * Pure Python stack, zero heavy Node.js or browser driver dependencies.
  * Smart Pillow image processing: handles transparency cleanly over white background, bilinear downsampling (1080px), and disables decompression bomb limits.
  * Loss-free, RAM-efficient PDF assembly via `img2pdf` with Pillow fallback.
  * Standard CBZ archive creation with embedded `ComicInfo.xml` metadata for comic readers.

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

### 4. Test Website Compatibility

```bash
# Test a single site from CLI
python manhua.py --test "https://asurascans.com/comics/pick-up-a-grimoire-become-a-mage-bd5bdaf8/chapter/1"

# Run the automated multi-site benchmark
python tests/test_matrix.py
```

---

## 📁 Project Architecture

```
Manhua-extractor/
├── manhua.py                     # Unified CLI & Web GUI launcher
├── app.py                        # FastAPI Backend & SSE streaming manager
├── library.db                    # SQLite Database (Auto-created)
├── requirements.txt              # Project dependencies
├── MANHUA_EXTRACTOR_SPEC.md      # Full 95%+ Technical Specification & Matrix
├── database/
│   ├── __init__.py
│   └── db.py                     # SQLite CRUD for Series, Chapters, and Diagnostics
├── extractors/
│   ├── __init__.py
│   ├── base.py                   # BaseExtractor interface & common sanitizers
│   ├── madara.py                 # Engine 1: WordPress Madara Specialist
│   ├── mangastream.py            # Engine 2: MangaStream, Themeia & Liliana Specialist
│   ├── modern_ssr.py             # Engine 3: Astro v7 (Asura) & Next.js (Flame)
│   ├── aggregator.py             # Engine 4: Manganato & Aggregators
│   ├── heuristic.py              # Engine 5: Universal Density Fallback
│   └── dispatcher.py             # Master signature detector & delegator
├── core/
│   ├── __init__.py
│   ├── downloader.py             # Async aiohttp downloader with 3x retries
│   ├── optimizer.py              # Pillow RGBA safe conversion & 1080px downsampling
│   └── compiler.py               # img2pdf, CBZ (ComicInfo.xml), & raw images
├── static/
│   ├── index.html                # Single-page Web GUI
│   ├── style.css                 # Dark-mode styling
│   └── app.js                    # SSE live monitor, library view & test lab
└── tests/
    └── test_matrix.py            # Automated multi-site benchmark runner
```

---

## 📊 Tested Compatibility Highlights

* **Asura Scans (`asurascans.com`)**: 🟢 **PASS** (29 panels isolated via Astro island props, exact title & next link resolved)
* **Toonily (`toonily.com`)**: 🟢 **PASS** (29 panels isolated via WordPress Madara engine)
* **ManhuaPlus (`manhuaplus.org`)**: 🟢 **PASS** (19 panels isolated via Liliana AJAX reader engine)

