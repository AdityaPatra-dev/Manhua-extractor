import asyncio
from typing import List, Optional, Callable, Tuple
import aiohttp
from .optimizer import optimize_panel_image

DEFAULT_CONCURRENCY = 6

async def fetch_single_panel(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    url: str,
    index: int,
    headers: dict,
    max_width: Optional[int] = 1080,
    jpeg_quality: int = 75,
    retries: int = 3
) -> Tuple[int, Optional[bytes]]:
    async with semaphore:
        for attempt in range(retries):
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    if response.status == 200:
                        raw_bytes = await response.read()
                        optimized = optimize_panel_image(raw_bytes, max_width=max_width, jpeg_quality=jpeg_quality)
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
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[bytes]:
    """
    Download a list of panel image URLs concurrently with retry logic and progress reporting.
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
                jpeg_quality=jpeg_quality
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

