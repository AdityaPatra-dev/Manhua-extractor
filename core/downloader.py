import asyncio
import os
import shutil
import hashlib
import re
from typing import List, Optional, Callable, Tuple, Any
try:
    import aiohttp
except ImportError:
    aiohttp = None
try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
import requests
from .optimizer import optimize_panel_image

DEFAULT_CONCURRENCY = 6


def get_staging_dir(base_dir: str, series_slug: str, chapter_num: float) -> str:
    """Returns a deterministic staging directory path for panel-level caching."""
    slug_clean = re.sub(r'[^a-zA-Z0-9_]', '_', series_slug.replace('-', '_'))
    ch_str = f"{chapter_num:g}".replace('.', '_')
    key = f"{slug_clean}_ch_{ch_str}"
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:8]
    return os.path.join(base_dir, ".staging", f"{key}_{h}")


def cleanup_staging_dir(staging_dir: Optional[str]) -> bool:
    """Removes temporary staging cache once chapter compilation succeeds."""
    if staging_dir and os.path.exists(staging_dir):
        try:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return True
        except Exception:
            return False
    return False


async def fetch_single_panel(
    session: Any,
    semaphore: asyncio.Semaphore,
    url: str,
    index: int,
    headers: dict,
    max_width: Optional[int] = 1080,
    jpeg_quality: int = 75,
    retries: int = 3,
    staging_dir: Optional[str] = None,
    image_format: str = "JPEG",
    webp_quality: int = 80
) -> Tuple[int, Optional[bytes]]:
    # Check if panel was already cached in staging
    if staging_dir:
        try:
            for ext in ("webp", "jpg", "png"):
                stage_file = os.path.join(staging_dir, f"panel_{index:04d}.{ext}")
                if os.path.exists(stage_file) and os.path.getsize(stage_file) > 512:
                    with open(stage_file, "rb") as f:
                        cached_bytes = f.read()
                    if cached_bytes:
                        return index, cached_bytes
        except Exception:
            pass

    # Check database for cached clearance cookie (Cloudflare bypass for protected CDNs)
    try:
        from database.db import get_clearance_cookie
        from urllib.parse import urlparse
        img_domain = urlparse(url).netloc
        ref_domain = urlparse(headers.get("Referer", "")).netloc if headers.get("Referer") else ""
        cached_cf = get_clearance_cookie(img_domain) or (get_clearance_cookie(ref_domain) if ref_domain else None)
        if cached_cf:
            headers = dict(headers)
            if not headers.get("Cookie"):
                headers["Cookie"] = cached_cf["cookie_string"]
            if cached_cf.get("user_agent"):
                headers["User-Agent"] = cached_cf["user_agent"]
    except Exception:
        pass

    async with semaphore:
        for attempt in range(retries):
            try:
                raw_bytes = None
                if aiohttp is not None and session is not None and isinstance(session, aiohttp.ClientSession):
                    try:
                        timeout = aiohttp.ClientTimeout(total=12, connect=5)
                        async with session.get(url, headers=headers, timeout=timeout) as response:
                            if response.status == 200:
                                raw_bytes = await response.read()
                    except Exception:
                        raw_bytes = None

                if raw_bytes is None:
                    def _sync_fetch() -> Optional[bytes]:
                        # 1. Try curl_cffi with Chrome impersonation if available
                        if HAS_CURL_CFFI:
                            try:
                                resp = cffi_requests.get(url, headers=headers, impersonate="chrome120", timeout=12)
                                if resp.status_code == 200 and len(resp.content) > 500:
                                    return resp.content
                            except Exception:
                                pass

                        # 2. Standard fetch
                        try:
                            resp = requests.get(url, headers=headers, timeout=10)
                            if resp.status_code == 200 and len(resp.content) > 500:
                                return resp.content
                        except Exception:
                            pass

                        # 3. Domain root referer with verify=False
                        try:
                            alt_headers = dict(headers)
                            if headers.get("Referer"):
                                ref_parts = headers["Referer"].split("/")
                                domain_ref = "/".join(ref_parts[:3]) + "/" if len(ref_parts) >= 3 else headers["Referer"]
                                alt_headers["Referer"] = domain_ref
                            resp = requests.get(url, headers=alt_headers, timeout=10, verify=False)
                            if resp.status_code == 200 and len(resp.content) > 500:
                                return resp.content
                        except Exception:
                            pass

                        # 4. Bare headers fallback
                        try:
                            bare_headers = {
                                "User-Agent": headers.get("User-Agent", "Mozilla/5.0"),
                                "Accept": "image/*,*/*;q=0.8"
                            }
                            resp = requests.get(url, headers=bare_headers, timeout=25, verify=False)
                            if resp.status_code == 200 and len(resp.content) > 500:
                                return resp.content
                        except Exception:
                            pass
                        return None
                    raw_bytes = await asyncio.to_thread(_sync_fetch)

                if raw_bytes:
                    def _process_and_stage():
                        opt = optimize_panel_image(
                            raw_bytes,
                            max_width=max_width,
                            jpeg_quality=jpeg_quality,
                            image_format=image_format,
                            webp_quality=webp_quality
                        )
                        if opt and staging_dir:
                            try:
                                os.makedirs(staging_dir, exist_ok=True)
                                ext = "webp" if (image_format or "JPEG").upper() == "WEBP" else "jpg"
                                stage_file = os.path.join(staging_dir, f"panel_{index:04d}.{ext}")
                                with open(stage_file, "wb") as f:
                                    f.write(opt)
                            except Exception:
                                pass
                        return opt

                    optimized = await asyncio.to_thread(_process_and_stage)
                    if optimized:
                        return index, optimized
            except Exception:
                if attempt < retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
        return index, None

async def download_panels_stream(
    image_urls: List[str],
    referer: str,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_width: Optional[int] = 1080,
    jpeg_quality: int = 75,
    staging_dir: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    image_format: str = "JPEG",
    webp_quality: int = 80,
    is_cancelled_callback: Optional[Callable[[], bool]] = None,
    is_paused_callback: Optional[Callable[[], bool]] = None
) -> List[bytes]:
    """
    Download a list of panel image URLs concurrently with retry logic,
    disk staging cache, image compression (JPEG/WebP), and progress reporting.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    semaphore = asyncio.Semaphore(concurrency)
    results = []

    if aiohttp is not None:
        async with aiohttp.ClientSession() as session:
            task_objs = [
                asyncio.create_task(fetch_single_panel(
                    session=session,
                    semaphore=semaphore,
                    url=url,
                    index=i,
                    headers=headers,
                    max_width=max_width,
                    jpeg_quality=jpeg_quality,
                    staging_dir=staging_dir,
                    image_format=image_format,
                    webp_quality=webp_quality
                ))
                for i, url in enumerate(image_urls)
            ]
            completed = 0
            total = len(task_objs)
            try:
                pending_set = set(task_objs)
                while pending_set:
                    if is_cancelled_callback and is_cancelled_callback():
                        for t in pending_set:
                            t.cancel()
                        return []
                    while is_paused_callback and is_paused_callback() and not (is_cancelled_callback and is_cancelled_callback()):
                        await asyncio.sleep(0.5)
                    done, pending_set = await asyncio.wait(pending_set, return_when=asyncio.FIRST_COMPLETED, timeout=0.5)
                    for t in done:
                        try:
                            res = t.result()
                            results.append(res)
                            if res[1] is not None:
                                completed += 1
                            if progress_callback:
                                progress_callback(completed, total)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                for t in task_objs:
                    t.cancel()
                return []
    else:
        task_objs = [
            asyncio.create_task(fetch_single_panel(
                session=None,
                semaphore=semaphore,
                url=url,
                index=i,
                headers=headers,
                max_width=max_width,
                jpeg_quality=jpeg_quality,
                staging_dir=staging_dir,
                image_format=image_format,
                webp_quality=webp_quality
            ))
            for i, url in enumerate(image_urls)
        ]
        completed = 0
        total = len(task_objs)
        try:
            pending_set = set(task_objs)
            while pending_set:
                if is_cancelled_callback and is_cancelled_callback():
                    for t in pending_set:
                        t.cancel()
                    return []
                while is_paused_callback and is_paused_callback() and not (is_cancelled_callback and is_cancelled_callback()):
                    await asyncio.sleep(0.5)
                done, pending_set = await asyncio.wait(pending_set, return_when=asyncio.FIRST_COMPLETED, timeout=0.5)
                for t in done:
                    try:
                        res = t.result()
                        results.append(res)
                        if res[1] is not None:
                            completed += 1
                        if progress_callback:
                            progress_callback(completed, total)
                    except Exception:
                        pass
        except asyncio.CancelledError:
            for t in task_objs:
                t.cancel()
            return []

    # Sort strictly by original panel index and exclude None
    sorted_bytes = [b for idx, b in sorted(results, key=lambda x: x[0]) if b is not None]
    return sorted_bytes


