# ⚡ Universal Manhua Extractor & Library

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue?logo=python)](https://www.python.org/)
[![Android Support](https://img.shields.io/badge/Android-8.0%2B%20(API%2026%2B)-green?logo=android)](ANDROID_SETUP_GUIDE.md)
[![FastAPI](https://img.shields.io/badge/backend-FastAPI%20%2B%20Uvicorn-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/unit%20tests-33%20passed-success)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A high-performance, modular manga/manhua/manhwa downloader, offline library manager, and **standalone Android application** engineered to support **95%+ of online manga platforms** via a 5-engine auto-detection architecture.

---

## 🌟 Key Highlights

### 📱 1. Standalone Native Android App (`.apk`)
* **Runs 100% on Phone**: Zero PC or computer required! The Python backend runs embedded directly inside the Android APK via **Chaquopy**.
* **Offline Library & Mobile Data**: Works on cellular 4G/5G or offline.
* **Screen-Off Background Downloads**: Uses an Android **Foreground Service** with `PARTIAL_WAKE_LOCK` to ensure large multi-chapter downloads continue uninterrupted when your screen locks.
* **Mihon & Tachiyomi Ready**: Automatically exports `.cbz` archives to your phone's public `Download/Manhua/` directory and notifies Android's `MediaScannerConnection`.
* 👉 **[Read the Complete Android Setup & Installation Guide](ANDROID_SETUP_GUIDE.md)**

### 🔍 2. Interactive Chapter Catalog Inspector
* Paste **any** series landing page or individual chapter link (e.g. Asura, Toonily, ManhuaPlus).
* Discovers all chapters (tested up to 900+ chapters) within 1–2 seconds.
* Live status badges: 🟢 **Saved** vs. ⚪ **Online**.
* Multi-select batch downloading with an instant **"📖 Read Now"** button upon completion.

### 📖 3. Touch-Optimized Mobile Fullscreen Web Reader
* **PWA ("Add to Home Screen")**: Launches as a standalone mobile application.
* **HTML5 Fullscreen API**: Immersive edge-to-edge vertical webtoon reading on mobile and desktop.
* **Tap-to-Toggle HUD**: Tap the page to toggle top navigation and bottom progress indicators.
* **Scroll-Direction Auto-Hide**: Top navigation smoothly slides away on downward scroll and reappears when scrolling up.
* **End-of-Chapter Card**: Quick-action buttons to jump directly to the next chapter.

### ⚡ 4. 5 Specialized Extraction Engines (95%+ Web Coverage)
1. **WordPress Madara Engine** (~50% of manhua sites: Toonily, MangaTX, KunManga, ZinManga, etc.)
2. **MangaStream / Themeia / Liliana Engine** (~25% of scanlator sites: ManhuaPlus, Luminous, Void, etc.)
3. **Modern SSR / Astro / Next.js Engine** (~15%: Asura Scans Astro v7, Flame Comics Next.js)
4. **Aggregator Engine** (Manganato, Chapmanganato, MangaBuddy with anti-hotlink referer spoofing)
5. **Universal Heuristic Fallback** (Density-based panel extraction for custom/unknown themes)

### 🗜️ 5. Next-Gen WebP Direct Compression
* Direct re-encoding into high-efficiency **WebP** providing **40% to 75% file size reduction** over JPEG.
* Preserves ultra-sharp line art and smooth gradients while saving gigabytes on phone and cloud storage.

### 📚 6. MangaDex API Rich Metadata & `<ComicInfo.xml>`
* Automatically queries the **MangaDex API** (with AniList fallback) for official title, author, artist, genres, year, and synopsis.
* Injects schema-compliant `<ComicInfo.xml>` into CBZ archives for immediate recognition in **Komga**, **Kavita**, and **ComicRack**.

### 📖 7. Kindle & E-Ink Whitespace Gutter Slicer
* Scans continuous vertical webtoon ribbons ($1080 \times 16000\text{ px}$) for natural panel gaps, slicing them cleanly into standard book-ratio pages ($1:1.414$).

### 🛡️ 8. 128-bit Perceptual Hash (pHash) Ad Trimmer
* Automatically fingerprints and trims recurring aggregator ad pages, Discord recruitment banners, and credit promos using composite `dHash + aHash`.

### 📡 9. OPDS 1.2 Catalog Server (`/opds/v1.2/catalog`)
* Stream and sync downloaded chapters directly into **Mihon**, **Tachiyomi**, **Moon+ Reader**, **Panels**, or **Chunky** over local Wi-Fi or loopback.

### 🔄 10. Automated Library Updater & Push Alerts
* Scheduled background update daemon checks your saved series for new chapter releases and sends push alerts via **Discord Webhooks**, **Telegram Bots**, or **Ntfy**.

---

## 🚀 Quick Start

### 📱 Method A: Install Standalone Android App on Phone (Zero PC Setup)
1. Go to the **[Actions Tab](../../actions)** in this repository.
2. Select the latest run of **"Build Standalone Android APK"**.
3. Download the `ManhuaExtractor-Standalone-APK` artifact.
4. Install `app-debug.apk` directly on your smartphone.
5. (See [ANDROID_SETUP_GUIDE.md](ANDROID_SETUP_GUIDE.md) for details).

---

### 💻 Method B: Run Web GUI on PC / Mac / Linux
```bash
# 1. Clone repository
git clone https://github.com/AdityaPatra-dev/Manhua-extractor.git
cd Manhua-extractor

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch Web GUI
python manhua.py --web
```
Open **`http://localhost:8000`** in your browser.

Terminal will also display smartphone Wi-Fi access links:
```text
====================================================================
 🚀 Universal Manhua Extractor & Web Reader Server Online
====================================================================
 💻 Local PC Access      : http://localhost:8000
 📱 Smartphone Wi-Fi     : http://192.168.x.x:8000
 📚 Mihon / Tachiyomi OPDS: http://192.168.x.x:8000/opds/v1.2/catalog
====================================================================
```

---

### ⌨️ Method C: CLI & Headless Batch Mode
```bash
# Interactive CLI
python manhua.py

# Download 5 chapters of a series as high-efficiency WebP CBZ with ComicInfo metadata
python manhua.py -U "https://asurascans.com/comics/solo-leveling/chapter/1" -c 5 -f cbz -e webp

# Inspect all chapters of a series from terminal
python manhua.py -i "https://manhuaplus.org/manga/magic-emperor"

# Slice tall webtoon ribbons for Kindle / E-Ink readers
python manhua.py -U "https://toonily.com/webtoon/tower-of-god/chapter-1" -s -f pdf

# Update entire library database with new releases
python manhua.py --update-library
```

---

## 🧪 Test Suite

Run the full automated test suite (all 33 unit tests):
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

---

## 📁 Repository Structure

```
Manhua-extractor/
├── android/                      # Native Android Studio project (Chaquopy + WebView)
│   ├── app/                      # App module (build.gradle.kts, AndroidManifest.xml)
│   ├── build.gradle.kts          # Root Gradle build script
│   └── settings.gradle.kts       # Gradle settings and Chaquopy repository
├── android_entry.py              # Android entrypoint adapter & storage router
├── ANDROID_SETUP_GUIDE.md        # Standalone Android user & installation guide
├── STANDALONE_ANDROID_APP_PLAN.md# Technical architecture specification for Android
├── app.py                        # FastAPI Backend & SSE streaming manager
├── manhua.py                     # Unified CLI & server launcher
├── database/                     # SQLite models: series, chapters, diagnostics, settings
├── extractors/                   # 5 extraction engines, catalog inspector & sidecars
├── core/                         # Downloader, WebP compiler, slicer, pHash, scrobbler
├── static/                       # Mobile-responsive web frontend, PWA manifest & reader
└── tests/                        # Automated unit tests covering all components
```

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
