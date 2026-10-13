# 📱 Manhua Extractor: Standalone Android App Guide

This guide explains how to build, install, and use the **100% Standalone Android Application** on your smartphone without needing a computer, Wi-Fi tethering, or external servers.

---

## ⚡ Overview

The Android version packages the entire Manhua Extractor engine inside an APK using **Chaquopy** and **Android WebView**:
- **Runs Locally**: The Python scraper and downloader run directly on your phone's CPU via embedded Python 3.11.
- **Works Everywhere**: Use on mobile data (4G/5G) or Wi-Fi.
- **Offline Library**: Browse, search, and read downloaded chapters without an internet connection.
- **Screen-Off Downloads**: Android `ForegroundService` with `WakeLock` keeps downloads running even when your screen is locked.
- **Mihon / Tachiyomi Ready**: Saved in standard `.cbz` format in your phone's public `Download/Manhua/` folder.

---

## 🚀 How to Get the APK

### Method 1: Download from GitHub Actions (Easiest - No Android Studio Needed)
1. Push your repository to GitHub:
   ```bash
   git push origin main
   ```
2. On GitHub, go to the **Actions** tab.
3. Select the latest run of **"Build Standalone Android APK"**.
4. Scroll to the **Artifacts** section at the bottom and download `ManhuaExtractor-Standalone-APK`.
5. Unzip the file and transfer `app-debug.apk` to your phone.
6. Tap the `.apk` file to install it! (Allow *"Install unknown apps"* if prompted).

### Method 2: Build Locally with Android Studio
1. Open the `android/` directory in **Android Studio**.
2. Connect your phone via USB with **USB Debugging** enabled.
3. Click **Run 'app'** (or run `./gradlew assembleDebug` in terminal).
4. The compiled APK is located at:
   ```text
   android/app/build/outputs/apk/debug/app-debug.apk
   ```

---

## 📖 How to Use the App on Your Phone

### 1. Launching the App
- Tap the **Manhua Extractor** icon on your home screen.
- A brief splash screen will appear for ~1–2 seconds while the embedded Python engine starts up on loopback `127.0.0.1:8000`.
- The interface will open directly into the mobile downloader.

### 2. Searching & Downloading Chapters
1. Paste any chapter or series link (e.g. Asura, Toonily, ManhuaPlus) into the URL field.
2. Tap **"🔍 Browse Chapters"**:
   - The app scrapes the full catalog and displays all chapters with 🟢 **Saved** and ⚪ **Online** status badges.
3. Select the chapters you want to download (or tap **Select All**).
4. Tap **"⬇️ Download Selected"**:
   - A persistent notification will appear in your status bar:
     *"Manhua Extractor: Downloading Chapter X..."*
   - You can lock your screen or switch to other apps; the `ForegroundService` will ensure your download continues uninterrupted.

### 3. Reading Downloaded Chapters
- **Option A (In-App Reader)**:
  - Once a chapter finishes downloading, tap the **"📖 Read Now"** button.
  - Enjoy continuous vertical webtoon scrolling.
  - Tap **"⛶ Fullscreen"** for edge-to-edge reading.
  - Tap anywhere on the page to hide/show the navigation HUD.
- **Option B (Mihon / Tachiyomi)**:
  - Downloaded chapters are saved in your phone's public `Download/Manhua/` folder as `.cbz` archives.
  - In Mihon / Tachiyomi:
    1. Go to **Settings** → **Downloads** → **Download location**.
    2. Point local storage or local manga directory to `Download/Manhua/`.
    3. Your downloaded series will automatically appear in your Mihon library!

---

## 🛠️ Permissions & Troubleshooting

| Permission | Why It Is Needed |
| :--- | :--- |
| **Internet** | To connect to manga websites and download chapter panels. |
| **Foreground Service** | To show progress notifications and prevent the OS from killing the app during downloads. |
| **Wake Lock** | To prevent the phone from going into deep sleep when the screen turns off during batch downloads. |
| **Notifications** | (Android 13+) Required to show the download progress notification. |

### Battery Optimization (Optional Tip)
For massive downloads (e.g., 50+ chapters at once):
1. Go to your phone's **Settings** → **Apps** → **Manhua Extractor** → **Battery**.
2. Select **"Unrestricted"** so Android's aggressive battery savers never pause your downloads.

---

## 🛡️ Native Android Cloudflare Turnstile Clearance Bridge (v1.0.6+)

Starting in **v1.0.6**, the Android app includes native in-app Cloudflare resolution (`CloudflareResolver.kt`):
- **100% Genuine Chrome WebView Engine**: Passes Cloudflare Turnstile challenges silently in the background on the phone's CPU.
- **SQLite Cookie Vault**: Automatically caches `cf_clearance` and `__cf_bm` tokens in the local SQLite database for up to 48 hours.
- **Zero Configuration**: No Docker, no proxies, no FlareSolverr containers needed on your phone.
- **Pre-Built Releases**:
  - `releases/ManhuaExtractor-v1.0.7-release.apk` (Signed release build, ~32MB)
  - `releases/ManhuaExtractor-v1.0.7-debug.apk` (Debug build, ~34MB)
  - `releases/ManhuaExtractor-v1.0.6-release.apk` (Signed release build, ~32MB)
  - `releases/ManhuaExtractor-v1.0.6-debug.apk` (Debug build, ~34MB)

