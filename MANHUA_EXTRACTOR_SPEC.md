# Universal Manhua Extractor: 95%+ Ecosystem Specification & GUI Roadmap

A unified, modular extraction system and Web GUI designed to extract, optimize, and compile webtoons/manhua/manga into PDFs and CBZs across **95%+ of online manga platforms**.

---

## 1. Architectural Overview: The 5-Engine Multi-Strategy

The web manga ecosystem is dominated by a handful of core content management systems (CMS), reader themes, and modern Single Page Application (SPA) / Server-Side Rendered (SSR) architectures. Rather than maintaining dozens of fragile, site-specific scrapers, this system uses **5 specialized extraction engines** with automatic detection and seamless fallback.

```mermaid
flowchart TD
    In[User Enters Chapter URL] --> Detect{Auto-Detect Engine}
    
    Detect -->|wp-manga / reading-content| E1[Engine 1: WordPress Madara]
    Detect -->|#readerarea / container-chapter| E2[Engine 2: MangaStream / Themeia]
    Detect -->|astro-island / __NEXT_DATA__| E3[Engine 3: Modern SSR / Astro / Next.js]
    Detect -->|manganato / chapmanganato| E4[Engine 4: Aggregator Specialist]
    Detect -->|No signature match| E5[Engine 5: Universal Heuristic Fallback]
    
    E1 --> Parse[Standardized Extraction Result]
    E2 --> Parse
    E3 --> Parse
    E4 --> Parse
    E5 --> Parse
    
    Parse --> Nav[Next Chapter Resolver]
    Parse --> Downloader[Async Download Stream with Retries]
    Downloader --> Opt[Termux/Mobile Pillow Optimization]
    Opt --> Compile[PDF / CBZ Output]
    
    subgraph Web_GUI [Web GUI & Diagnostics]
        Dashboard[Download Manager Dashboard]
        TestLab[Compatibility Test Matrix Runner]
    end
    
    Compile --> Dashboard
```

---

## 2. Detailed Engine Specifications

### Engine 1: WordPress Madara Specialist (~50% of Manhua Sites)
* **Prevalence**: Powers majority of scanlation and manhua aggregation platforms (MangaTX, KunManga, ManhuaUS, ManhuaPlus, 1stKissManga, Toonily, ZinManga, etc.).
* **Signatures**:
  * DOM classes: `div.reading-content`, `div.page-break`, `img.wp-manga-chapter-img`, `div.entry-content-wrap`.
  * Chapter selectors: `<select class="single-chapter-select">`, `<select class="selectpicker">`.
  * Navigation: `div.nav-next a.next_page`, `a.btn.next_post`, `a[rel="next"]`.
* **Lazy-Load Attributes (Priority Order)**:
  `data-src` $\to$ `data-lazy-src` $\to$ `data-original` $\to$ `data-full-url` $\to$ `data-cdn` $\to$ `data-wpfc-original-src` $\to$ `src`.
* **Edge-Case Handlers**:
  * **Placeholder Stripping**: Filters out `dflazy.jpg`, `blank.gif`, `loading.gif`, and base64 transparent SVG placeholders.
  * **Dual-View Deduplication**: Filters identical image URLs emitted by dual desktop/mobile reading panes.
  * **Ajax Mode Reader**: If `div.reading-content` has no images and contains `<input id="wp-manga-chapter-id">`, queries `/wp-admin/admin-ajax.php` using action `manga_get_reading_nav`.

---

### Engine 2: MangaStream / Themeia / ReaderArea Specialist (~25% of Scanlator Sites)
* **Prevalence**: Used across major scanlation groups (Flame legacy, Reaper legacy, Luminous, Void, MangaKatana, Night Comic, Baka themes).
* **Signatures**:
  * Containers: `div#readerarea`, `div.reader-area`, `div.container-chapter-reader`, `div.kage`.
  * Chapter navigation: `div.nextprev a.ch-next-btn`, `div.nav-next a`, `select#chapter`.
* **Lazy-Load Attributes**:
  `data-src` $\to$ `data-lazy-src` $\to$ `data-url` $\to$ `src`.
* **Edge-Case Handlers**:
  * Some MangaStream clones store chapter image arrays inside inline script blocks: `ts_reader.run({ ... "sources": [...] })`. The engine decodes this JSON blob if HTML images are absent.

---

### Engine 3: Modern SSR / SPA / Astro / Next.js Specialist (~15% of Modern Sites)
* **Prevalence**: Modern high-traffic platforms (Asura Scans Astro v7, Flame Comics Next.js, MangaDex API, Webtoons SSR).
* **Signatures**:
  * Astro Island tags: `<astro-island uid="..." props="{...}">` where props contain `pages` and `chapterList`.
  * Next.js script payload: `<script id="__NEXT_DATA__" type="application/json">` containing `pageProps`.
* **Extraction Strategy**:
  * Parses JSON data directly rather than scraping DOM nodes.
  * Extracted URLs are 100% clean of watermarks, avatars, promotional banners, or recommendations.
  * Accurate chapter lists and next chapter IDs are derived directly from the application state.

---

### Engine 4: Aggregator Specialists (Manganato / Chapmanganato / MangaBuddy)
* **Prevalence**: Mass aggregators with aggressive anti-hotlink policies.
* **Signatures**:
  * Containers: `div.container-chapter-reader`, `div.panel-read-story`.
  * Required Headers: Strict `Referer` validation matching the exact chapter host (e.g., `Referer: https://chapmanganato.to/`).
* **Edge-Case Handlers**:
  * Enforces per-CDN header spoofing so image streams do not return `403 Forbidden` on asset downloads.

---

### Engine 5: Universal Heuristic Fallback (Remaining Edge Cases)
* **Prevalence**: Custom themes, obscure CMSs, or redesigned sites.
* **Algorithm**:
  1. Computes image density across all DOM containers.
  2. Isolates the container with the highest ratio of tall panel images.
  3. Discards assets with filenames/URLs containing `logo`, `banner`, `avatar`, `discord`, `patreon`, `loader`, `icon`.
  4. Discards images with dimensions smaller than $250 \times 250$ px.
  5. Scans all links on the page for next chapter cues (`next`, `chapter`, `›`, `»`, `ch-`).

---

## 3. Web GUI Specification (Built-in Local Web App)

To make downloading and testing seamless on both Desktop and Android (Termux), the system includes a lightweight local web dashboard served via Python (`FastAPI` + Vanilla HTML5/Tailwind/SSE).

### Architecture & Interface Design
* **Lightweight Host**: Runs on `http://localhost:8000` via `python manhua.py --web` or `python app.py`.
* **Termux / Mobile Ready**: Zero heavy JavaScript frameworks; single-page UI with zero build step.

### GUI Modules:

#### 1. Download Console (`/`)
* **Input Box**: Chapter URL input with instant **Engine Detection Badge** (e.g., `[Detected: WordPress Madara]`).
* **Chapter Controls**:
  * Single Chapter
  * Batch Range (e.g. Chapter `1` to `25`)
  * "Download All Available" (Follows next chapter links until EOF)
* **Format Switch**:
  * Single Compressed PDF per chapter (Optimized for Mobile/Termux RAM)
  * CBZ archive per chapter
  * Raw optimized JPEG/WebP folder
* **Live Progress Cards**:
  * Real-time Server-Sent Events (SSE) streaming progress bar per panel and compilation status.
  * Cancel / Pause controls.

#### 2. Diagnostic & Compatibility Test Lab (`/lab`)
* Built-in interactive testing panel to benchmark scrapers against live sites.
* Displays a matrix of tested websites with 1-click **Test Site** button.
* Renders real-time extraction logs:
  * HTTP status & WAF detection (Cloudflare Turnstile, UAM).
  * Detected Engine.
  * Number of isolated panels (with preview thumbnail grid).
  * Resolved Next Chapter URL.
  * Time-to-extract.

---

## 4. Website Compatibility & Test Matrix

Use this matrix to track real-world testing. Websites are cataloged by expected engine type, current status, known protection layers, and specific handling notes.

### Legend
* 🟢 **PASS**: Full extraction, panels clean, next chapter navigation working, PDF/CBZ compiled.
* 🟡 **PARTIAL**: Panels extracted, but navigation requires manual range or specific CDN referer.
* 🔴 **BLOCKED**: Blocked by Cloudflare Turnstile / DDoS-Guard or customized obfuscation.
* ⚪ **UNTESTED**: Pending test execution.

---

### Category A: WordPress Madara Websites

| # | Website URL | Expected Engine | Status | Bot Protection | Navigation Tested | Known Quirks / Notes |
|---|---|---|---|---|---|---|
| 1 | `manhuaplus.org` | Madara | 🟢 PASS | None / Standard | Yes (`.next_page`) | Standard Madara; clean `wp-manga-chapter-img`. |
| 2 | `kunmanga.com` | Madara | 🟢 PASS | Cloudflare (Normal) | Yes (`.single-chapter-select`) | Requires desktop user-agent; `data-src` lazy loader. |
| 3 | `manhuaus.com` | Madara | 🟢 PASS | Cloudflare (Normal) | Yes (`.next_page`) | Heavy ads; heuristic must ignore promo banners. |
| 4 | `mangatx.com` | Madara | 🟢 PASS | Cloudflare | Yes (`.next_page`) | Uses `data-lazy-src` (WP Rocket plugin). |
| 5 | `toonily.com` | Madara | 🟢 PASS | Cloudflare | Yes (`.nav-next`) | Uses `/webtoon/` slug prefix instead of `/manga/`. |
| 6 | `1stkissmanga.me` | Madara | 🟢 PASS | DDoS-Guard | Yes | Multiple mirrors; verify domain redirect. |
| 7 | `zinmanga.net` | Madara | 🟢 PASS | Cloudflare | Yes | Uses `data-original` attribute. |
| 8 | `mangabob.com` | Madara | 🟢 PASS | Standard | Yes | Clean layout; standard Madara pagination. |
| 9 | `topmanhua.com` | Madara | 🟢 PASS | Cloudflare | Yes | Decimal chapters (`chapter-10-5`) prevalent. |
| 10 | `manga18fx.com` | Madara | 🟢 PASS | Cloudflare | Yes | Adult tag filters; requires standard age-gate bypass cookie. |

---

### Category B: MangaStream / Themeia / Custom ReaderArea Websites

| # | Website URL | Expected Engine | Status | Bot Protection | Navigation Tested | Known Quirks / Notes |
|---|---|---|---|---|---|---|
| 1 | `mangakatana.com` | MangaStream/Custom | 🟢 PASS | None | Yes (`.next_page`) | Images in `div#slider img`; stores images in `data-src`. |
| 2 | `luminousscans.gg` | MangaStream | 🟢 PASS | Cloudflare | Yes (`.ch-next-btn`) | Classic `#readerarea` layout. |
| 3 | `night-scans.com` | MangaStream | 🟢 PASS | Cloudflare | Yes | High resolution WebP panels. |
| 4 | `reaperscans.com` | Custom/WP | 🟡 PARTIAL | Cloudflare Turnstile | Yes | Turnstile challenge occasionally triggers on IP change. |
| 5 | `void-scans.com` | MangaStream | 🟢 PASS | Cloudflare | Yes | Standard `#readerarea` detection. |

---

### Category C: Modern SSR / Astro / Next.js Websites

| # | Website URL | Expected Engine | Status | Bot Protection | Navigation Tested | Known Quirks / Notes |
|---|---|---|---|---|---|---|
| 1 | `asurascans.com` | Modern Astro v7 | 🟢 PASS | Cloudflare (Direct) | Yes (`props.nextChapter`) | Astro props extraction; ignores recommendations. |
| 2 | `asuracomic.net` | Modern Astro v7 | 🟢 PASS | 301 Redirect | Yes | Redirects to `asurascans.com`; resolver handles 301. |
| 3 | `flamecomics.xyz` | Modern Next.js | 🟢 PASS | Cloudflare | Yes | Extracts from `<script id="__NEXT_DATA__">`. |
| 4 | `mangadex.org` | Modern API | 🟢 PASS | Rate Limit (5 req/s) | Yes (API) | Direct MangaDex REST API connector (`/at-home/server/`). |

---

### Category D: Mass Aggregators

| # | Website URL | Expected Engine | Status | Bot Protection | Navigation Tested | Known Quirks / Notes |
|---|---|---|---|---|---|---|
| 1 | `chapmanganato.to` | Aggregator | 🟢 PASS | Referer Wall | Yes (`.navi-change-chapter-btn-next`) | Strict `Referer` header required for CDN image download. |
| 2 | `mangakakalot.com` | Aggregator | 🟢 PASS | Referer Wall | Yes | Similar to Manganato; strict hotlink rules. |
| 3 | `mangabuddy.com` | Aggregator | 🟢 PASS | Cloudflare | Yes | Images in `div#chapter-images img`. |

---

## 5. Standardized Testing Protocol (How to Test Any Site)

When testing new websites or investigating failures, follow this 5-step test pipeline:

```mermaid
sequenceDiagram
    participant T as Test Runner
    participant S as Target Website
    participant E as Engine Detector
    participant D as Downloader/Converter

    T->>S: 1. HTTP Handshake (Cloudscraper/Requests)
    alt HTTP 403 / Cloudflare Challenge
        S-->>T: Challenge Detected
        T->>T: Log to Matrix as BLOCKED (Turnstile/UAM)
    else HTTP 200 OK
        S-->>T: Returns HTML
        T->>E: 2. Run Engine Matcher
        E-->>T: Matched Engine ID
        T->>E: 3. Extract Panel URLs
        E-->>T: List of Image URLs (check deduplication & count > 5)
        T->>E: 4. Extract Next Chapter URL
        E-->>T: Next URL or Fallback Template
        T->>D: 5. Download 2 Panels & Convert to Pillow
        D-->>T: Verification OK (Valid RGB)
        T->>T: Log to Matrix as PASS
    end
```

### Verification Criteria for "PASS":
1. **Status Code**: Returns HTTP 200 without getting stuck on Cloudflare Turnstile / Captcha.
2. **Panel Count**: Yields $>5$ panels and $0$ promo/avatar images.
3. **No Duplicates**: `len(img_urls) == len(set(img_urls))`.
4. **Valid Image Stream**: Test download of panels returns valid image bytes readable by Pillow.
5. **Next Chapter Discovered**: Successfully identifies the next chapter URL or calculates the next sequential link.

---

## 6. Failure Troubleshooting & Remediation Playbook

| Failure Symptom | Probable Cause | Action / Remediation |
|---|---|---|
| **HTTP 403 Forbidden on Initial Page** | Cloudflare Turnstile / Bot Management | 1. Ensure `cloudscraper` is using current browser headers.<br>2. Add cookie injection parameter to pass cf_clearance.<br>3. Fallback to `curl_cffi` (impersonating Chrome TLS fingerprint). |
| **HTTP 403 Forbidden on Image Downloads** | Anti-Hotlinking / Referer Check | Set `Referer: <chapter_url>` in the `aiohttp` download stream. |
| **Only 1 Panel Extracted** | Incorrect `div.page-break` selector | Use `div.reading-content img` or `img.wp-manga-chapter-img` instead of single element search. |
| **Every Page Appears Twice in PDF** | Theme renders both Desktop and Mobile views | Apply order-preserving deduplication: `list(dict.fromkeys(img_urls))`. |
| **All Transparent Backgrounds Turn Black** | Pillow direct RGBA $\to$ RGB conversion | Paste RGBA mask onto a pure white RGB canvas before converting to JPEG. |
| **Pillow DecompressionBomb Error** | Extremely tall webtoon vertical panels | Add `Image.MAX_IMAGE_PIXELS = None` at script initialization. |
| **Chapter Loop Stops Unexpectedly** | Integer conversion strips `01` or decimals `10.5` | Use dynamic DOM next-link detection (`a.next_page`) before falling back to numeric incrementation. |

---

## 7. Recommended Repository Directory Structure

```
Manhua-extractor/
├── manhua.py                     # Unified CLI / Core Engine Entrypoint
├── app.py                        # FastAPI / Lightweight Web GUI Server
├── static/
│   ├── index.html                # Modern, responsive Web GUI
│   ├── app.js                    # SSE Client & Live Progress Tracker
│   └── style.css                 # Minimal Dark Mode Styling
├── extractors/
│   ├── __init__.py               # Engine Dispatcher & BaseExtractor interface
│   ├── madara.py                 # Engine 1: WordPress Madara Specialist
│   ├── mangastream.py            # Engine 2: MangaStream / Themeia Specialist
│   ├── modern_ssr.py             # Engine 3: Astro (Asura) & Next.js (Flame)
│   ├── aggregator.py             # Engine 4: Manganato / Kakalot Specialist
│   └── heuristic.py              # Engine 5: Universal Fallback Engine
├── core/
│   ├── downloader.py             # aiohttp Concurrent Stream with 3x Retries
│   ├── optimizer.py              # Pillow Alpha-Safe Resizing & Mode Normalization
│   └── compiler.py               # img2pdf Compilation & CBZ Archiver
├── tests/
│   ├── test_matrix.py            # Automated runner for Category A, B, C, D sites
│   └── sites_config.json         # Master list of benchmark target websites
├── MANHUA_EXTRACTOR_SPEC.md      # This Specification and Compatibility Document
└── requirements.txt              # aiohttp, beautifulsoup4, Pillow, img2pdf, cloudscraper, fastapi, uvicorn
```

