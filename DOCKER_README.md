<div align="center">

# 📖 Universal Manhua Extractor & Web Reader

**High-performance, automated manga/manhua/manhwa downloader, offline reading library, and OPDS 1.2 streaming server.**

[![Docker Pulls](https://img.shields.io/docker/pulls/adityapatra/manhua-extractor?style=flat-square&color=2496ED&logo=docker&logoColor=white)](https://hub.docker.com/r/adityapatra/manhua-extractor)
[![Docker Image Size](https://img.shields.io/docker/image-size/adityapatra/manhua-extractor/latest?style=flat-square&color=38bdf8)](https://hub.docker.com/r/adityapatra/manhua-extractor)
[![GitHub Release](https://img.shields.io/github/v/release/AdityaPatra-dev/Manhua-extractor?style=flat-square&color=7c3aed)](https://github.com/AdityaPatra-dev/Manhua-extractor/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-F59E0B?style=flat-square)](https://github.com/AdityaPatra-dev/Manhua-extractor/blob/main/LICENSE)

---

### [GitHub Repository](https://github.com/AdityaPatra-dev/Manhua-extractor) • [Releases & Android APK](https://github.com/AdityaPatra-dev/Manhua-extractor/releases) • [Supported Websites Matrix](https://github.com/AdityaPatra-dev/Manhua-extractor#supported-websites--platform-engine-types)

</div>

---

## ⚡ Highlights

* 🌐 **89+ Platforms Supported**: Built-in automated extractors for Modern SSR (Astro/Next.js), WordPress Madara, MangaStream/Themesia, Aggregators, Batoto, and universal heuristic fallback.
* 🛡️ **Anti-Bot & Shield Bypass**: Native TLS fingerprint spoofing (Chrome 124 TLS via `curl_cffi`), Cloudflare Turnstile token resolution, and anti-hotlink CDN bypass.
* 📚 **Built-in Web Reader & Dashboard**: Modern, responsive dark-mode HTML5 PWA reader with continuous vertical webtoon ribbon scrolling and directional manga mode.
* 📡 **Wireless OPDS 1.2 Catalog**: Stream and acquire chapters wirelessly into **Mihon**, **Tachiyomi**, **Moon+ Reader**, **Panels**, or **Chunky** at `http://<server-ip>:8000/opds/v1.2/catalog`.
* 📦 **Atomic Backup & Multi-Volume Sync**: Export whole-library or split 1.5 GB sequential ZIP archives with Zip-Slip protection and cross-device SQLite state synchronization.
* ✂️ **Kindle E-Ink Slicing & Ad Trimming**: NumPy energy-histogram gutter detection for tall webtoon strips, plus 128-bit perceptual hashing (pHash) to filter scanlator promo pages.

---

## 🚀 Quick Start

### 1. Run with Docker CLI

```bash
docker run -d \
  --name manhua-extractor \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/downloads:/app/downloads \
  -v $(pwd)/backups:/app/backups \
  --restart unless-stopped \
  adityapatra/manhua-extractor:latest
```

Open **`http://localhost:8000`** in your web browser.

---

### 2. Run with Docker Compose (Recommended)

Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  manhua-extractor:
    image: adityapatra/manhua-extractor:latest
    container_name: manhua-extractor
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - PORT=8000
      - HOST=0.0.0.0
      - MANHUA_DB_PATH=/app/data/library.db
      - MANHUA_DOWNLOADS_DIR=/app/downloads
      - MANHUA_BACKUPS_DIR=/app/backups
      # Optional: Cloudflare solver sidecar
      - FLARESOLVERR_URL=http://flaresolverr:8191/v1
    volumes:
      - ./data:/app/data
      - ./downloads:/app/downloads
      - ./backups:/app/backups
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

  # Optional sidecar for automated Cloudflare Turnstile bypass
  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    container_name: flaresolverr
    restart: unless-stopped
    ports:
      - "8191:8191"
    environment:
      - LOG_LEVEL=info
      - CAPTCHA_SOLVER=none
```

Launch the stack:
```bash
docker compose up -d
```

---

## 📂 Persistent Storage & Volumes

| Container Path | Host Recommended Path | Description |
| :--- | :--- | :--- |
| `/app/data` | `./data` | Stores SQLite `library.db` (reading history, series tracking, diagnostics) |
| `/app/downloads` | `./downloads` | Stores downloaded chapters, CBZ archives, and raw panels |
| `/app/backups` | `./backups` | Stores exported multi-volume backup `.zip` archives |

---

## ⚙️ Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `8000` | Port for the Web GUI and OPDS catalog server |
| `HOST` | `0.0.0.0` | Host bind address |
| `MANHUA_DB_PATH` | `/app/data/library.db` | Absolute path to SQLite library database |
| `MANHUA_DOWNLOADS_DIR` | `/app/downloads` | Directory path where chapters and CBZ files are stored |
| `MANHUA_BACKUPS_DIR` | `/app/backups` | Directory path where backup archives are staged |
| `FLARESOLVERR_URL` | *None* | Optional URL to FlareSolverr sidecar (e.g. `http://flaresolverr:8191/v1`) |

---

## 📱 Connect Mobile Readers via OPDS

You can stream your library directly into mobile reader apps over your local network:

1. Open **Mihon**, **Tachiyomi**, or **Moon+ Reader**.
2. Add a new **OPDS Catalog**:
   ```text
   http://<YOUR-SERVER-IP>:8000/opds/v1.2/catalog
   ```
3. Browse series, view high-res cover art, and download or stream CBZ files wirelessly without USB cables.

---

## 🩺 Healthcheck & Monitoring

The container includes a built-in healthcheck:
```bash
curl -f http://localhost:8000/api/health
```
**Response:**
```json
{"status":"ok","platform":"desktop"}
```

---

## 📄 License & Credits

* Distributed under the **MIT License**.
* Maintained by [Aditya Patra](https://github.com/AdityaPatra-dev).
* Sourced icons and community extensions thanks to Keiyoushi & Tachiyomi.

