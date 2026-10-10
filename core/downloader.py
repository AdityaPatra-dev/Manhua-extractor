import asyncio
import os
import shutil
import hashlib
import re
from typing import List, Optional, Callable, Tuple
import aiohttp
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
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    url: str,
    index: int,
    headers: dict,
    max_width: Optional[int] = 1080,
    jpeg_quality: int = 75,
    retries: int = 3,
    staging_dir: Optional[str] = None
) -> Tuple[int, Optional[bytes]]:
    # Check if panel was already cached in staging
    if staging_dir:
        try:
            stage_file = os.path.join(staging_dir, f"panel_{index:04d}.jpg")
            if os.path.exists(stage_file) and os.path.getsize(stage_file) > 512:
                with open(stage_file, "rb") as f:
                    cached_bytes = f.read()
                if cached_bytes:
                    return index, cached_bytes
        except Exception:
            pass

    async with semaphore:
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        raw_bytes = await response.read()
                        optimized = optimize_panel_image(raw_bytes, max_width=max_width, jpeg_quality=jpeg_quality)
                        if optimized:
                            if staging_dir:
                                try:
                                    os.makedirs(staging_dir, exist_ok=True)
                                    stage_file = os.path.join(staging_dir, f"panel_{index:04d}.jpg")
                                    with open(stage_file, "wb") as f:
                                        f.write(optimized)
                                except Exception:
                                    pass
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
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[bytes]:
    """
    Download a list of panel image URLs concurrently with retry logic,
    disk staging cache, and progress reporting.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i, url in enumerate(image_urls):
            t = fetch_single_panel(
                session=session,
                semaphore=semaphore,
                url=url,
                index=i,
                headers=headers,
                max_width=max_width,
                jpeg_quality=jpeg_quality,
                staging_dir=staging_dir
            )
            tasks.append(t)

        completed = 0
        total = len(tasks)
        for fut in asyncio.as_completed(tasks):
            res = await fut
            results.append(res)
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    # Sort strictly by original panel index and exclude None
    sorted_bytes = [b for idx, b in sorted(results, key=lambda x: x[0]) if b is not None]
    return sorted_bytes


