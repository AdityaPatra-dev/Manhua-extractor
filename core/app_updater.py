import re
import time
import urllib.request
import json
import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("app_updater")

CURRENT_APP_VERSION = "1.3.0"
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


def get_latest_release(
    force: bool = False,
    simulate: bool = False,
    prefer_debug: bool = False,
    abi: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch latest release metadata from GitHub Releases API with smart ABI split selection.
    Automatically matches device architecture (arm64-v8a, armeabi-v7a, x86_64) to minimize download size.
    Caches results in memory to respect rate limits.
    """
    global _cached_result, _last_fetch_time

    now = time.time()
    device_abi = (abi.split(",")[0].strip().lower() if abi else None)

    if simulate:
        sim_universal_size = 34500000
        sim_arm64_size = 25200000
        sim_armv7_size = 24100000
        sim_x86_size = 26000000

        selected_abi = device_abi or "arm64-v8a"
        if selected_abi == "armeabi-v7a":
            chosen_name = "app-armeabi-v7a-release.apk"
            chosen_size = sim_armv7_size
            savings_pct = int(round((sim_universal_size - sim_armv7_size) / sim_universal_size * 100))
        elif selected_abi == "x86_64":
            chosen_name = "app-x86_64-release.apk"
            chosen_size = sim_x86_size
            savings_pct = int(round((sim_universal_size - sim_x86_size) / sim_universal_size * 100))
        elif selected_abi == "arm64-v8a":
            chosen_name = "app-arm64-v8a-release.apk"
            chosen_size = sim_arm64_size
            savings_pct = int(round((sim_universal_size - sim_arm64_size) / sim_universal_size * 100))
        else:
            chosen_name = "app-universal-release.apk"
            chosen_size = sim_universal_size
            savings_pct = 0

        return {
            "status": "success",
            "current_version": CURRENT_APP_VERSION,
            "latest_version": "1.3.1",
            "tag_name": "v1.3.1",
            "has_update": True,
            "release_name": "Release v1.3.1 (Simulated)",
            "release_notes": "Added dedicated Vortex Scans extractor, real-time download metrics, and lightweight architecture-specific APK downloads.",
            "published_at": "",
            "html_url": f"https://github.com/{GITHUB_REPO}/releases",
            "apk_url": f"https://github.com/{GITHUB_REPO}/releases/download/v1.3.1/{chosen_name}",
            "apk_name": chosen_name,
            "apk_size": chosen_size,
            "apk_abi": selected_abi,
            "is_abi_specific": selected_abi in ("arm64-v8a", "armeabi-v7a", "x86_64"),
            "data_savings_percent": savings_pct,
            "universal_apk_size": sim_universal_size,
            "available_variants": [
                {"name": "app-arm64-v8a-release.apk", "abi": "arm64-v8a", "label": "ARM64 (v8a • Modern Phones)", "size": sim_arm64_size, "url": f"https://github.com/{GITHUB_REPO}/releases/download/v1.3.1/app-arm64-v8a-release.apk"},
                {"name": "app-armeabi-v7a-release.apk", "abi": "armeabi-v7a", "label": "ARM 32-bit (v7a • Older/Budget Phones)", "size": sim_armv7_size, "url": f"https://github.com/{GITHUB_REPO}/releases/download/v1.3.1/app-armeabi-v7a-release.apk"},
                {"name": "app-x86_64-release.apk", "abi": "x86_64", "label": "x86_64 (Emulators/PCs)", "size": sim_x86_size, "url": f"https://github.com/{GITHUB_REPO}/releases/download/v1.3.1/app-x86_64-release.apk"},
                {"name": "app-universal-release.apk", "abi": "universal", "label": "Universal (All Devices)", "size": sim_universal_size, "url": f"https://github.com/{GITHUB_REPO}/releases/download/v1.3.1/app-universal-release.apk"},
            ],
            "apk_debug_url": f"https://github.com/{GITHUB_REPO}/releases/download/v1.3.1/app-debug.apk",
            "checked_at": int(now),
            "simulated": True,
        }

    # If cached and no specific ABI or debug override requested, reuse cache
    if not force and not prefer_debug and not abi and _cached_result and (now - _last_fetch_time < CACHE_TTL):
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

                # Collect release and debug assets
                release_variants: Dict[str, Dict[str, Any]] = {}
                debug_variants: Dict[str, Dict[str, Any]] = {}

                for asset in release.get("assets", []):
                    name = asset.get("name", "")
                    download_url = asset.get("browser_download_url")
                    size = asset.get("size", 0)

                    # Determine ABI
                    matched_abi = None
                    if "arm64-v8a" in name:
                        matched_abi = "arm64-v8a"
                    elif "armeabi-v7a" in name:
                        matched_abi = "armeabi-v7a"
                    elif "x86_64" in name:
                        matched_abi = "x86_64"
                    elif "universal" in name or name in ("app-release.apk", "app-debug.apk"):
                        matched_abi = "universal"

                    item = {
                        "name": name,
                        "url": download_url,
                        "size": size,
                        "abi": matched_abi or "unknown"
                    }

                    if "debug" in name:
                        if matched_abi:
                            debug_variants[matched_abi] = item
                    else:
                        if matched_abi:
                            release_variants[matched_abi] = item

                active_map = debug_variants if (prefer_debug and debug_variants) else release_variants

                # Select best variant based on device_abi
                chosen_item = None
                chosen_abi = "universal"
                if device_abi and device_abi in active_map:
                    chosen_item = active_map[device_abi]
                    chosen_abi = device_abi
                elif "universal" in active_map:
                    chosen_item = active_map["universal"]
                    chosen_abi = "universal"
                elif active_map:
                    # Fallback to whatever release APK is available
                    first_k = next(iter(active_map))
                    chosen_item = active_map[first_k]
                    chosen_abi = first_k

                # Compute data savings vs universal
                universal_size = 0
                if "universal" in active_map:
                    universal_size = active_map["universal"].get("size", 0)

                savings_pct = 0
                if chosen_item and universal_size > 0 and chosen_item.get("size", 0) < universal_size:
                    savings_pct = int(round((universal_size - chosen_item["size"]) / universal_size * 100))

                primary_apk_url = chosen_item["url"] if chosen_item else None
                primary_apk_name = chosen_item["name"] if chosen_item else None
                primary_apk_size = chosen_item["size"] if chosen_item else 0

                has_update = is_version_newer(clean_tag, CURRENT_APP_VERSION)

                # Format available variants for frontend presentation
                variants_list: List[Dict[str, Any]] = []
                abi_labels = {
                    "arm64-v8a": "ARM64 (v8a • Modern Phones)",
                    "armeabi-v7a": "ARM 32-bit (v7a • Older/Budget Phones)",
                    "x86_64": "x86_64 (Emulators/PCs)",
                    "universal": "Universal (All Devices)"
                }
                for vabi, vdata in active_map.items():
                    variants_list.append({
                        "name": vdata["name"],
                        "abi": vabi,
                        "label": abi_labels.get(vabi, vabi),
                        "size": vdata["size"],
                        "url": vdata["url"]
                    })

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
                    "apk_abi": chosen_abi,
                    "is_abi_specific": chosen_abi in ("arm64-v8a", "armeabi-v7a", "x86_64"),
                    "data_savings_percent": savings_pct,
                    "universal_apk_size": universal_size,
                    "available_variants": variants_list,
                    "apk_debug_url": debug_variants.get(chosen_abi, {}).get("url") or debug_variants.get("universal", {}).get("url"),
                    "checked_at": int(now),
                    "simulated": False,
                }

                if not simulate and not abi:
                    _cached_result = result
                    _last_fetch_time = now

                return result

    except Exception as e:
        logger.warning("Failed to check for updates: %s", e)
        if _cached_result and not simulate:
            return _cached_result

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
            "apk_abi": "universal",
            "is_abi_specific": False,
            "data_savings_percent": 0,
            "available_variants": [],
            "apk_debug_url": None,
            "checked_at": int(now),
            "simulated": False,
        }
