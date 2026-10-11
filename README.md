<div align="center">

# ⚡ Universal Manhua Extractor & Library
### 🚀 High-Performance Multi-Engine Webtoon Downloader, Offline Library & Standalone Android App

<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&pause=1000&color=6366F1&center=true&vCenter=true&width=750&lines=Download+Manga%2C+Manhua+%26+Manhwa+from+95%25%2B+Sites;100%25+Standalone+Android+App+(Embedded+Python+Inside);Sequential+1.5+GB+Multi-Volume+Backup+%26+Cross-Device+Sync;Cloudflare+Turnstile+Bypass+%2B+Anti-Hotlinking+Spoofer;Kindle+E-Ink+Whitespace+Gutter+Slicer+%2B+128-bit+pHash+Ad+Trimmer" alt="Universal Manhua Extractor Typing Banner" />
</p>

[![Release](https://img.shields.io/github/v/release/AdityaPatra-dev/Manhua-extractor?color=7c3aed&label=Latest%20Release&logo=github&style=for-the-badge)](https://github.com/AdityaPatra-dev/Manhua-extractor/releases)
[![Android APK](https://img.shields.io/badge/Android-APK%20v1.0.5-3DDC84?style=for-the-badge&logo=android&logoColor=white)](https://github.com/AdityaPatra-dev/Manhua-extractor/releases)
[![Python Version](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.99.1-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Unit%20Tests-57%20Passed-10b981?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B?style=for-the-badge&logo=open-source-initiative&logoColor=white)](LICENSE)

<br/>

<p align="center">
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Smartphone.png" alt="Android Phone" width="48" height="48" />
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Books.png" alt="Library" width="48" height="48" />
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Package.png" alt="Backup" width="48" height="48" />
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Travel%20and%20places/High%20Voltage.png" alt="Fast" width="48" height="48" />
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Shield.png" alt="Shield Bypass" width="48" height="48" />
  <img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Antenna%20Bars.png" alt="OPDS" width="48" height="48" />
</p>

**Universal Manhua Extractor** is an all-in-one webtoon/manga extractor, offline reader, cross-device sync engine, and **standalone Android application**. Powered by a 6-engine auto-detection dispatcher, it effortlessly navigates Cloudflare Turnstile, anti-hotlink CDN shields, dynamic Astro/Next.js hydration, and infinite scrolling across **95%+ of online manga platforms**.

</div>

---

## 🌐 Supported Websites & Platform Engine Types

Universal Manhua Extractor utilizes a multi-tiered fallback architecture. Platforms are auto-detected by engine signature, CDN patterns, and DOM layout.

### 📑 Supported Engines Overview

```mermaid
graph TD
    A["Incoming URL"] --> B{"Engine Dispatcher"}
    B -->|Astro v7/v8 / Next.js SSR / API| C["⚡ Modern SSR Engine"]
    B -->|WP-Manga / Ajax REST| D["🌸 WordPress Madara Engine"]
    B -->|Themesia / Tsuyoki / Liliana| E["🌊 MangaStream Engine"]
    B -->|CDN Anti-Hotlink Mirrors| F["📦 Aggregator Engine"]
    B -->|Bato.to v3x / JSON-LD| G["🏔️ Batoto & MangaPeak Engine"]
    B -->|Custom CMS / Unlisted Site| H["🔍 Universal Heuristic Fallback"]
```

---

### 📚 Comprehensive Website Directory

| Site | Platform URL | Engine Type | Protected Assets & Anti-Bot Handled | Operational Status |
| :--- | :--- | :--- | :--- | :---: |
| <img src="https://www.google.com/s2/favicons?domain=asuracomic.net&sz=64" width="24" height="24" alt="Asura Scans" /> **Asura Scans** | [asuracomic.net](https://asuracomic.net) | **Modern SSR** (Astro v7/v8) | Cloudflare Turnstile, Astro Island JSON Hydration | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=flamecomics.xyz&sz=64" width="24" height="24" alt="Flame Comics" /> **Flame Comics** | [flamecomics.xyz](https://flamecomics.xyz) | **Modern SSR** (Next.js) | Next.js State Data (`__NEXT_DATA__`), WebP CDNs | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=mangadex.org&sz=64" width="24" height="24" alt="MangaDex" /> **MangaDex** | [mangadex.org](https://mangadex.org) | **REST API v5** | Global High-Res CDN, Dynamic Chapter Metadata | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=comick.io&sz=64" width="24" height="24" alt="ComicK" /> **ComicK** | [comick.io](https://comick.io) | **Modern SSR** | API v1 JSON Manifests, High-Density Scans | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=webtoons.com&sz=64" width="24" height="24" alt="LINE Webtoon" /> **LINE Webtoon** | [webtoons.com](https://webtoons.com) | **Official Webtoon Engine** | Referer validation, DRM-free ribbon stream | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=toonily.com&sz=64" width="24" height="24" alt="Toonily" /> **Toonily** | [toonily.com](https://toonily.com) | **WP Madara** | Ajax pagination, lazy-loaded `.data-src` panels | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=mangatx.to&sz=64" width="24" height="24" alt="MangaTX" /> **MangaTX** | [mangatx.to](https://mangatx.to) | **WP Madara** | Anti-leech script, Cloudflare challenges | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=kunmanga.com&sz=64" width="24" height="24" alt="KunManga" /> **KunManga** | [kunmanga.com](https://kunmanga.com) | **WP Madara** | WordPress Manga REST API, multi-chapter DOM | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=zinmanga.com&sz=64" width="24" height="24" alt="ZinManga" /> **ZinManga** | [zinmanga.com](https://zinmanga.com) | **WP Madara** | Image proxy routing, encrypted chapter lists | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=1stkissmanga.io&sz=64" width="24" height="24" alt="1stKissManga" /> **1stKissManga** | [1stkissmanga.io](https://1stkissmanga.io) | **WP Madara** | Dynamic DOM slicing, Ajax admin endpoints | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=topmanhua.com&sz=64" width="24" height="24" alt="TopManhua" /> **TopManhua** | [topmanhua.com](https://topmanhua.com) | **WP Madara** | Custom CDN rewrite rules, aggressive ads | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=mangaclash.com&sz=64" width="24" height="24" alt="MangaClash" /> **MangaClash** | [mangaclash.com](https://mangaclash.com) | **WP Madara** | Lazy-load intersection observers | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=manhuaplus.org&sz=64" width="24" height="24" alt="ManhuaPlus" /> **ManhuaPlus** | [manhuaplus.org](https://manhuaplus.org) | **MangaStream** | Themesia framework, dynamic panel layout | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=luminousscans.com&sz=64" width="24" height="24" alt="Luminous Scans" /> **Luminous Scans** | [luminousscans.com](https://luminousscans.com) | **MangaStream** | Cloudflare Turnstile, image referer locks | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=reaperscans.com&sz=64" width="24" height="24" alt="Reaper Scans" /> **Reaper Scans** | [reaperscans.com](https://reaperscans.com) | **MangaStream / SPA** | Inertia.js props, custom scanlator headers | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=drakescans.com&sz=64" width="24" height="24" alt="Drake Scans" /> **Drake Scans** | [drakescans.com](https://drakescans.com) | **MangaStream** | Tsuyoki template, sequential image loading | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=zeroscans.com&sz=64" width="24" height="24" alt="ZeroScans" /> **ZeroScans** | [zeroscans.com](https://zeroscans.com) | **MangaStream** | Custom JSON reader, dynamic chapter slugs | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=chapmanganato.to&sz=64" width="24" height="24" alt="Manganato" /> **Manganato / ChapManganato** | [chapmanganato.to](https://chapmanganato.to) | **Aggregator Engine** | Strict anti-hotlinking (`Referer: chapmanganato.to`) | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=mangabuddy.com&sz=64" width="24" height="24" alt="MangaBuddy" /> **MangaBuddy** | [mangabuddy.com](https://mangabuddy.com) | **Aggregator Engine** | Dynamic image token hashes, multi-mirror failover | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=mangabat.com&sz=64" width="24" height="24" alt="MangaBat" /> **MangaBat** | [mangabat.com](https://mangabat.com) | **Aggregator Engine** | CDN referer authentication, chunked streams | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=mangapill.com&sz=64" width="24" height="24" alt="MangaPill" /> **MangaPill** | [mangapill.com](https://mangapill.com) | **Aggregator Engine** | Zero-JS clean layout, direct image extraction | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=bato.to&sz=64" width="24" height="24" alt="Batoto" /> **Batoto (Bato.to)** | [bato.to](https://bato.to) | **Batoto v3x / JSON-LD** | Dynamic image server assignment, scrambled tokens | `🟢 Verified` |
| <img src="https://www.google.com/s2/favicons?domain=mangapeak.com&sz=64" width="24" height="24" alt="MangaPeak" /> **MangaPeak** | [mangapeak.com](https://mangapeak.com) | **MangaPeak Engine** | Custom image obfuscation, encrypted manifests | `🟢 Verified` |
| <img src="https://raw.githubusercontent.com/Takul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Objects/Magnifying%20Glass%20Tilted%20Right.png" width="24" height="24" alt="Generic Fallback" /> **Any Unlisted Site / Custom Blog** | *Paste any URL* | **Universal Heuristic** | Density-based DOM image crawler, viewport filters | `🟢 Verified` |

---

<details>
<summary><b>🏗️ Full System Architecture & Deep Technical Specifications (Click to Expand)</b></summary>

<br/>

### 1. High-Level Technical Architecture

```mermaid
flowchart TD
    subgraph Client["📱 Frontend Clients"]
        AndroidUI["Android WebView Native App<br/>(Material 3 / Edge-to-Edge)"]
        WebReader["HTML5 PWA Web Reader<br/>(Touch & Directional Gestures)"]
        ExternalApp["Mihon / Tachiyomi / Moon+ Reader<br/>(OPDS 1.2 Catalog)"]
    end

    subgraph Backend["⚙️ Embedded FastAPI / Uvicorn Server"]
        Router["REST API Router & SSE Streamer<br/>(/api/download, /api/backup, /opds)"]
        State["Atomic Progress Queue<br/>(Pause / Resume / Cancel Controls)"]
    end

    subgraph Core["🧠 Extraction & Compilation Engine"]
        Dispatcher["6-Engine Dispatcher<br/>(Modern SSR, Madara, MangaStream, Aggregator)"]
        Sidecar["Bypass Stack<br/>(curl_cffi Chrome 124 TLS + FlareSolverr)"]
        Downloader["Zero-RAM Disk Streamer<br/>(AsyncIO Chunk Buffers)"]
        AdFilter["128-bit pHash Ad Trimmer<br/>(dHash + aHash Composite Analysis)"]
        Slicer["Kindle Whitespace Slicer<br/>(NumPy Energy Histogram Gutter Detection)"]
        Compiler["WebP & CBZ Compiler<br/>(MangaDex & ComicInfo.xml Tagging)"]
    end

    subgraph Storage["💾 Persistence & Sync Subsystem"]
        SQLite[("SQLite 3 DB (library.db)<br/>Multi-Key Series Unification")]
        DownloadsDir["Local Downloads Directory<br/>(/downloads/Series/Chapter.cbz)"]
        BackupEngine["Bin-Packing Multi-Volume Backup Engine<br/>(1.5 GB Batches, ZIP64, Zero-RAM Streaming)"]
    end

    AndroidUI --> Router
    WebReader --> Router
    ExternalApp --> Router
    Router --> State
    Router --> Dispatcher
    Dispatcher --> Sidecar
    Dispatcher --> Downloader
    Downloader --> AdFilter
    AdFilter --> Slicer
    Slicer --> Compiler
    Compiler --> DownloadsDir
    Compiler --> SQLite
    Router --> BackupEngine
    BackupEngine --> SQLite
    BackupEngine --> DownloadsDir
```

---

### 2. Standalone Android Lifecycle Architecture
* **Chaquopy Embedded CPython 3.11**: The full Python runtime, SQLite driver, FastAPI server, and PIL/Pillow image processing suite run inside the Android process sandbox without root or external Python environments.
* **Screen-Off Background Foreground Service**: Utilizes an Android `ForegroundService` tied to a persistent notification channel with `PowerManager.PARTIAL_WAKE_LOCK`. This guarantees downloads continue running at full speed when the user locks their phone or navigates to other apps.
* **Dynamic MediaScanner Integration**: As chapters compile into `.cbz` or `.pdf`, they are committed to `/storage/emulated/0/Download/Manhua/` and registered with Android's `MediaScannerConnection`, making files immediately visible in phone file managers, Mihon, and ComicScreen.

---

### 3. Sequential 1.5 GB Multi-Volume Backup & Sync Engine
* **Greedy Bin-Packing Algorithm**: Inspects uncompressed chapter archives, recursively traversing directory chapters (`file_format == 'folder'`) and standalone CBZ/PDFs. Packs library assets into discrete volumes targeting a **1,450 MB soft ceiling** to guarantee that archives stay under 1.5 GB on disk (ideal for FAT32 SD cards and cloud drives).
* **Self-Contained Series Metadata & Covers**: If Part 2 contains chapters of *Ultra Alter*, Part 2 also bundles that series' `cover.jpg` and canonical metadata, ensuring archives can be restored in **any arbitrary order** without missing covers.
* **Zip-Slip Boundary Defense**: Extraction enforces `os.path.commonpath([dest_dir, target_file]) == dest_dir`, rejecting any malicious directory traversal patterns (`../../`).
* **Zero-RAM Direct-to-Disk Streamer**: Uploaded backup parts stream directly to disk in 64 KB chunks, preventing mobile out-of-memory crashes.
* **Non-Destructive Series Unification**: Restoring backups across phones matches series by `lower(trim(title))`, `slug`, and `title_slug`, preventing duplicate series cards and retaining highest read bookmarks.

---

### 4. 128-bit Perceptual Hash (pHash) Ad Trimming
* Computes dual `dHash` (gradient difference) and `aHash` (average luminance) over a $16 \times 16$ grayscale matrix to generate a resilient 128-bit perceptual signature.
* Compares incoming page hashes against registered aggregator watermarks and Discord promo signatures using Hamming distance thresholds ($\le 6$ bits difference), automatically purging ads before compilation.

---

### 5. Continuous Ribbon Whitespace Slicer
* Scans long continuous vertical strips ($1080 \times 16000\text{ px}$) using a row-wise energy projection histogram:
  $$\Delta E(y) = \sum_{x=0}^{W-1} |I(x, y) - I(x, y-1)|$$
* Identifies natural panel breaks in pure white or black gutters, cutting the ribbon into standard aspect ratio pages ($1:1.414$) for crisp reading on Kindle Paperwhite and E-Ink displays.

---

### 6. Built-in OPDS 1.2 Catalog Feed
* Implements the Atom-compliant OPDS 1.2 catalog specification at `/opds/v1.2/catalog`.
* Exposes series feeds, cover thumbnails, and direct acquisition links (`application/vnd.comicbook+zip`) over local Wi-Fi, allowing instant wireless streaming into **Mihon**, **Tachiyomi**, **Moon+ Reader**, **Panels**, or **Chunky**.

</details>

---

<details>
<summary><b>🚀 Complete Installation & Deployment Guide (Click to Expand)</b></summary>

<br/>

### 📱 Option 1: Standalone Android App (Zero PC Setup)

Install directly on your phone in under 60 seconds:
1. Go to the **[Releases Section](https://github.com/AdityaPatra-dev/Manhua-extractor/releases)**.
2. Download **`app-release.apk`** (v1.0.5).
3. Open the APK on your Android device and tap **Install**.
4. Grant Notification and Storage permissions when prompted.
5. Tap **Start Download** — the embedded FastAPI server boots automatically!

> [!TIP]
> For screen-off background downloading, ensure you allow unrestricted battery usage in **App Info ➔ Battery ➔ Unrestricted**.

---

### 💻 Option 2: Run Web GUI on PC / Mac / Linux

#### Prerequisites
* Python 3.10, 3.11, or 3.12
* `git` installed

```bash
# 1. Clone repository
git clone https://github.com/AdityaPatra-dev/Manhua-extractor.git
cd Manhua-extractor

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install core dependencies
pip install -r requirements.txt

# 4. Launch the Web Interface & Server
python manhua.py --web
```
Open **`http://localhost:8000`** in your browser.

The terminal will display your smartphone Wi-Fi access links:
```text
====================================================================
 🚀 Universal Manhua Extractor & Web Reader Server Online
====================================================================
 💻 Local PC Access       : http://localhost:8000
 📱 Smartphone Wi-Fi      : http://192.168.1.50:8000
 📚 Mihon / Tachiyomi OPDS : http://192.168.1.50:8000/opds/v1.2/catalog
====================================================================
```

---

### 🐳 Option 3: Docker & FlareSolverr Sidecar Setup

Run the extractor alongside FlareSolverr to automatically solve interactive Cloudflare Turnstile challenges:

```yaml
# docker-compose.yml
version: '3.8'

services:
  manhua-extractor:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./downloads:/app/downloads
      - ./backups:/app/backups
      - ./library.db:/app/library.db
    environment:
      - FLARESOLVERR_URL=http://flaresolverr:8191/v1
    restart: unless-stopped

  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    ports:
      - "8191:8191"
    environment:
      - LOG_LEVEL=info
      - CAPTCHA_SOLVER=none
    restart: unless-stopped
```

Start the containers:
```bash
docker compose up -d
```

---

### ⌨️ Option 4: Headless CLI & Automated Scripting

```bash
# Interactive terminal prompt
python manhua.py

# Download 5 chapters of a series as high-efficiency WebP CBZ with ComicInfo metadata
python manhua.py -U "https://asuracomic.net/series/solo-leveling" -c 5 -f cbz -e webp

# Inspect all online chapters of a series from terminal
python manhua.py -i "https://manhuaplus.org/manga/magic-emperor"

# Slice tall webtoon ribbons into book-ratio pages for Kindle / E-Ink
python manhua.py -U "https://toonily.com/webtoon/tower-of-god/chapter-1" -s -f pdf

# Run background library update to check and download new releases
python manhua.py --update-library
```

</details>

---

## 🛡️ Anti-Bot & Protection Bypass Capabilities

Universal Manhua Extractor incorporates a multi-layer bypass pipeline to defeat common scraping defenses:

```mermaid
graph LR
    subgraph Challenge["Scraper Defense"]
        T["Cloudflare Turnstile"]
        H["Anti-Hotlink CDN"]
        D["Scrambled Canvases"]
        L["Lazy-Loading Panels"]
        R["429 Rate Limits"]
        A["Promo & Credit Ads"]
    end

    subgraph Solution["Extractor Engine Solution"]
        T -->|"curl_cffi Chrome 124 TLS Fingerprint + FlareSolverr"| ST["Clearance Pass"]
        H -->|"Contextual Referer & Sec-Fetch Header Spoofing"| SH["Raw Byte Stream"]
        D -->|"De-Scramble Coordinate Matrix Assembly"| SD["Unscrambled JPEG/WebP"]
        L -->|"DOM AST Attribute Crawler (data-src / data-original)"| SL["Complete Page Array"]
        R -->|"Asynchronous Worker Pool + Exponential Jitter Backoff"| SR["Zero-Ban Queue"]
        A -->|"128-bit Composite pHash Hamming Distance Trimmer"| SA["Clean Reading Stream"]
    end
```

### 🔐 Detailed Bypass Specifications

1. **Cloudflare Turnstile & Challenge Checkboxes**:
   * **Tier 1 (Native TLS Spoofing)**: Uses `curl_cffi` to mimic Chrome 124's exact TLS client hello, ALPN, cipher suites, and HTTP/2 settings, passing Cloudflare without running a heavy browser.
   * **Tier 2 (FlareSolverr Sidecar)**: If an interactive checkbox or JS challenge appears, the request automatically routes to FlareSolverr, solves the challenge, and caches clearance cookies.

2. **Anti-Hotlinking & CDN Image Leech Shields**:
   * Sites like Manganato, MangaBuddy, and ChapManganato restrict direct access to image servers (`*.cacaca.net`, `*.cdnpk.net`).
   * The extractor dynamically injects host-specific `Referer`, `Origin`, and `Sec-Fetch-Site: same-site` headers on each individual panel stream.

3. **Dynamic Astro, Next.js & React Hydration Extraction**:
   * Modern scanlators (e.g. Asura Scans Astro v7/v8, Flame Comics Next.js) avoid server-rendered HTML for panels.
   * Extracts JSON payloads directly from `<script id="__NEXT_DATA__">`, `window.__INITIAL_STATE__`, or Astro island components.

4. **Lazy-Loading & Viewport Obfuscation**:
   * Scans attributes including `data-src`, `data-lazy-src`, `data-original`, `data-url`, and base64 SVG placeholders to assemble the full panel list in sequence.

5. **Rate Limiting & IP Throttling**:
   * Built-in asynchronous worker queues enforce domain-specific download pacing with randomized jitter backoff, avoiding `429 Too Many Requests` bans.

6. **Promotional & Ad Page Fingerprint Filter**:
   * Automatically strips recurring scanlator aggregator ads, casino banners, and credit recruiting pages via 128-bit perceptual hashing.

---

## 🧪 Unit Test Suite

The codebase is protected by **57 automated unit tests** covering all extractors, bin-packing estimation, ZIP64 streaming, Zip-Slip vulnerability rejection, and REST API endpoints:

```bash
# Run complete test suite
python3 -m unittest discover -s tests -p "test_*.py"
```

```text
Ran 57 tests in 3.450s
OK
```

---

## 🤝 Contributing & Issue Reporting

Contributions, bug reports, and new engine extractor requests are welcome!
1. Fork this repository.
2. Create your feature branch (`git checkout -b feature/NewExtractor`).
3. Commit your changes (`git commit -m "feat: add support for NewMangaSite"`).
4. Push to the branch (`git push origin feature/NewExtractor`).
5. Open a Pull Request.

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
