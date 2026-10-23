import re
import time
import urllib.request
import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("app_updater")

CURRENT_APP_VERSION = "1.1.0"
GITHUB_REPO = "AdityaPatra-dev/Manhua-extractor"
CACHE_TTL = 1800  # 30 minutes

_cached_result: Optional[Dict[str, Any]] = None
_last_fetch_time: float = 0.0


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Extract numeric components of a version tag (e.g. 'v1.0.9' -> (1, 0, 9))."""
    if not version_str:
        return (0,)
    nums = re.findall(r"\d+", version_str)
    if not nums:
        return (0,)
    return tuple(int(n) for n in nums)


def is_version_newer(latest_version: str, current_version: str) -> bool:
    """Compare two semantic version strings. Returns True if latest > current."""
    latest_parts = parse_version(latest_version)
    current_parts = parse_version(current_version)
    
    # Pad to equal length with zeros
    max_len = max(len(latest_parts), len(current_parts))
    latest_padded = latest_parts + (0,) * (max_len - len(latest_parts))
    current_padded = current_parts + (0,) * (max_len - len(current_parts))
    
    return latest_padded > current_padded


def get_latest_release(force: bool = False, simulate: bool = False, prefer_debug: bool = False) -> Dict[str, Any]:
    """
    Fetch latest release metadata from GitHub Releases API.
    Caches results in memory to respect rate limits.
    """
    global _cached_result, _last_fetch_time

    now = time.time()
    if not force and not simulate and not prefer_debug and _cached_result and (now - _last_fetch_time < CACHE_TTL):
        return _cached_result

    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    headers = {
        "User-Agent": f"ManhuaExtractor/{CURRENT_APP_VERSION}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status == 200:
                raw_data = response.read().decode("utf-8")
                release = json.loads(raw_data)
                
                tag_name = release.get("tag_name", "").strip()
                clean_tag = tag_name.lstrip("vV")
                
                apk_release_url = None
                apk_debug_url = None
                apk_release_size = 0
                apk_debug_size = 0

                for asset in release.get("assets", []):
                    name = asset.get("name", "")
                    download_url = asset.get("browser_download_url")
                    size = asset.get("size", 0)
                    if name == "app-release.apk":
                        apk_release_url = download_url
                        apk_release_size = size
                    elif name == "app-debug.apk":
                        apk_debug_url = download_url
                        apk_debug_size = size

                if prefer_debug and apk_debug_url:
                    primary_apk_url = apk_debug_url
                    primary_apk_size = apk_debug_size
                    primary_apk_name = "app-debug.apk"
                else:
                    primary_apk_url = apk_release_url or apk_debug_url
                    primary_apk_size = apk_release_size or apk_debug_size
                    primary_apk_name = "app-release.apk" if apk_release_url else ("app-debug.apk" if apk_debug_url else None)

                has_update = is_version_newer(clean_tag, CURRENT_APP_VERSION)
                if simulate:
                    has_update = True
                    clean_tag = "1.2.0"
                    tag_name = "v1.2.0"

                result = {
                    "status": "success",
                    "current_version": CURRENT_APP_VERSION,
                    "latest_version": clean_tag,
                    "tag_name": tag_name,
                    "has_update": has_update,
                    "release_name": release.get("name", f"Release {tag_name}"),
                    "release_notes": release.get("body", ""),
                    "published_at": release.get("published_at", ""),
                    "html_url": release.get("html_url", f"https://github.com/{GITHUB_REPO}/releases"),
                    "apk_url": primary_apk_url,
                    "apk_name": primary_apk_name,
                    "apk_size": primary_apk_size,
                    "apk_debug_url": apk_debug_url,
                    "checked_at": int(now),
                    "simulated": simulate,
                }

                if not simulate:
                    _cached_result = result
                    _last_fetch_time = now

                return result

    except Exception as e:
        logger.warning("Failed to check for updates: %s", e)
        # If cache exists, return it even if expired during network failure
        if _cached_result and not simulate:
            return _cached_result

        # Provide a graceful fallback
        return {
            "status": "error",
            "message": str(e),
            "current_version": CURRENT_APP_VERSION,
            "latest_version": CURRENT_APP_VERSION,
            "has_update": False,
            "release_name": f"Current v{CURRENT_APP_VERSION}",
            "release_notes": "",
            "published_at": "",
            "html_url": f"https://github.com/{GITHUB_REPO}/releases",
            "apk_url": None,
            "apk_name": None,
            "apk_size": 0,
            "apk_debug_url": None,
            "checked_at": int(now),
            "simulated": False,
        }
