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
    Launches Chrome completely off-screen so no windows pop open or interrupt the user.
    """
    try:
        import nodriver as uc
        import asyncio
        import concurrent.futures

        async def _run():
            c = uc.Config(headless=False)
            c.add_argument("--window-position=-10000,-10000")
            browser = await uc.start(c)
            try:
                page = await browser.get(target_url)
                for _ in range(timeout_seconds):
                    await asyncio.sleep(1)
                    try:
                        title = await page.evaluate("document.title")
                        if title and "Just a moment" not in str(title):
                            break
                    except Exception:
                        pass

                # Allow client-side frameworks (Next.js, Vue, etc.) to hydrate DOM
                for _ in range(5):
                    await asyncio.sleep(1)
                    try:
                        imgs = await page.evaluate('document.querySelectorAll("img").length')
                        if imgs and int(imgs) > 1:
                            break
                    except Exception:
                        pass

                cookies = await page.send(uc.cdp.network.get_cookies())
                try:
                    ua = await page.evaluate("navigator.userAgent")
                except Exception:
                    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                content = await page.get_content()
                cookie_dict = {c.name: c.value for c in cookies} if cookies else {}
                return {
                    "success": True,
                    "status_code": 200,
                    "text": content,
                    "cookies": cookie_dict,
                    "user_agent": ua
                }
            finally:
                browser.stop()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _run()).result(timeout=timeout_seconds + 12)
    except Exception:
        return None


def solve_with_android_webview(target_url: str, timeout_seconds: int = 18) -> Optional[Dict[str, Any]]:
    """
    On-device Android System WebView Turnstile resolver.
    Invokes Kotlin CloudflareResolver on the Android UI thread via Chaquopy.
    """
    try:
        from com.manhua.extractor import CloudflareResolver  # type: ignore
        import json
        from urllib.parse import urlparse
        from database.db import save_clearance_cookie

        res_str = CloudflareResolver.resolveUrl(target_url, timeout_seconds)
        if not res_str:
            return None

        data = json.loads(res_str)
        if data.get("success"):
            raw_cookie = data.get("cookies", "")
            cookie_dict = {}
            for part in raw_cookie.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    cookie_dict[k] = v

            ua = data.get("user_agent", "")
            try:
                domain = urlparse(target_url).netloc
                save_clearance_cookie(domain, raw_cookie, ua)
            except Exception:
                pass

            return {
                "success": True,
                "status_code": data.get("status", 200),
                "text": data.get("html", ""),
                "cookies": cookie_dict,
                "user_agent": ua
            }
    except ImportError:
        pass
    except Exception as e:
        import sys
        print(f"[AndroidResolver] Exception during resolution: {e}", file=sys.stderr)
    return None


def fetch_protected_page(
    url: str,
    flaresolverr_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Tries native Android System WebView first if running on Android,
    otherwise tries FlareSolverr, Playwright fallback, then nodriver / Chrome CDP.
    """
    # 0. Try on-device Android System WebView if on Android
    android_sol = solve_with_android_webview(url)
    if android_sol and android_sol.get("success"):
        return android_sol

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

