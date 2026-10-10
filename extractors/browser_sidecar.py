import os
from typing import Optional, Dict, Any
import requests

DEFAULT_FLARESOLVERR_URL = "http://localhost:8191/v1"


def is_flaresolverr_available(endpoint: Optional[str] = None) -> bool:
    """Checks if a FlareSolverr container is reachable."""
    url = (endpoint or DEFAULT_FLARESOLVERR_URL).rstrip("/")
    try:
        r = requests.get(url if not url.endswith("/v1") else url[:-3], timeout=3)
        return r.status_code in (200, 404, 405)
    except Exception:
        return False


def solve_with_flaresolverr(
    target_url: str,
    endpoint: Optional[str] = None,
    max_timeout: int = 60000
) -> Optional[Dict[str, Any]]:
    """
    Dispatches a Cloudflare Turnstile-protected URL to a FlareSolverr service.
    Returns dictionary with solved HTML, status code, and cookies.
    """
    url = (endpoint or DEFAULT_FLARESOLVERR_URL).rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"

    payload = {
        "cmd": "request.get",
        "url": target_url,
        "maxTimeout": max_timeout
    }

    try:
        r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=max_timeout // 1000 + 5)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "ok" and data.get("solution"):
                solution = data["solution"]
                # Parse cookies list into dict
                cookie_dict = {}
                for c in solution.get("cookies", []):
                    cookie_dict[c.get("name")] = c.get("value")

                return {
                    "success": True,
                    "status_code": solution.get("status", 200),
                    "text": solution.get("response", ""),
                    "cookies": cookie_dict,
                    "user_agent": solution.get("userAgent", "")
                }
    except Exception:
        pass
    return None


def solve_with_playwright(target_url: str, timeout_seconds: int = 30) -> Optional[Dict[str, Any]]:
    """
    On-demand headless Playwright fallback for Turnstile challenges if playwright is installed.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(target_url, timeout=timeout_seconds * 1000)

            # Wait for Turnstile challenge to resolve (check for chapter images or non-challenge body)
            page.wait_for_timeout(4000)

            content = page.content()
            cookies_list = context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies_list}
            browser.close()

            return {
                "success": True,
                "status_code": 200,
                "text": content,
                "cookies": cookie_dict,
                "user_agent": "Playwright/Chrome"
            }
    except ImportError:
        return None
    except Exception:
        return None


def solve_with_nodriver(target_url: str, timeout_seconds: int = 15) -> Optional[Dict[str, Any]]:
    """
    On-demand nodriver / Chrome CDP fallback for Cloudflare Turnstile challenges.
    """
    try:
        import nodriver as uc
        import asyncio
        import concurrent.futures

        async def _run():
            is_headless = not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            browser = await uc.start(headless=is_headless)
            try:
                page = await browser.get(target_url)
                for _ in range(timeout_seconds):
                    await asyncio.sleep(1)
                    title = await page.evaluate("document.title")
                    if title and "Just a moment" not in str(title):
                        break
                # Allow JS/hydration to settle
                await asyncio.sleep(2)
                content = await page.get_content()
                cookies_cdp = await page.send(uc.cdp.network.get_cookies())
                cookie_dict = {c.name: c.value for c in cookies_cdp} if cookies_cdp else {}
                return {
                    "success": True,
                    "status_code": 200,
                    "text": content,
                    "cookies": cookie_dict,
                    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                }
            finally:
                browser.stop()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _run()).result(timeout=timeout_seconds + 8)
    except Exception:
        return None


def fetch_protected_page(
    url: str,
    flaresolverr_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Tries FlareSolverr first, then Playwright fallback, then nodriver / Chrome CDP.
    """
    # 1. Try FlareSolverr if available
    sol = solve_with_flaresolverr(url, endpoint=flaresolverr_url)
    if sol and sol.get("success"):
        return sol

    # 2. Try Playwright fallback
    pw_sol = solve_with_playwright(url)
    if pw_sol and pw_sol.get("success"):
        return pw_sol

    # 3. Try nodriver / Chrome CDP fallback
    nd_sol = solve_with_nodriver(url)
    if nd_sol and nd_sol.get("success"):
        return nd_sol

    return None

