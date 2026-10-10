import os
import re
import requests
from typing import Dict, Any, Optional

ANILIST_API_URL = "https://graphql.anilist.co"
MAL_API_URL = "https://api.myanimelist.net/v2"


# --- AniList Operations ---

def verify_anilist_token(token: str) -> Dict[str, Any]:
    """Verifies that the provided AniList token is valid by querying the current viewer."""
    if not token or not token.strip():
        return {"success": False, "error": "Token cannot be empty"}

    query = """
    query {
      Viewer {
        id
        name
        avatar {
          medium
        }
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        r = requests.post(ANILIST_API_URL, json={"query": query}, headers=headers, timeout=12)
        data = r.json()
        if r.status_code == 200 and data.get("data", {}).get("Viewer"):
            viewer = data["data"]["Viewer"]
            return {
                "success": True,
                "user_id": viewer["id"],
                "username": viewer["name"],
                "avatar": viewer.get("avatar", {}).get("medium")
            }
        errors = data.get("errors", [{}])
        err_msg = errors[0].get("message") if errors else f"HTTP {r.status_code}"
        return {"success": False, "error": err_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_anilist_manga(title: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Searches AniList for a manga/manhua by title and returns its media metadata."""
    if not title:
        return None

    # Clean title from aggregator noise
    clean_title = re.sub(r'(?i)\b(manhwa|manhua|manga|webtoon|raw|scan|chapter.*)\b', '', title).strip()
    if not clean_title:
        clean_title = title

    query = """
    query ($search: String) {
      Media(search: $search, type: MANGA) {
        id
        title {
          romaji
          english
          native
        }
        chapters
        status
        coverImage {
          medium
        }
      }
    }
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"

    try:
        r = requests.post(ANILIST_API_URL, json={"query": query, "variables": {"search": clean_title}}, headers=headers, timeout=12)
        if r.status_code == 200:
            data = r.json().get("data", {}).get("Media")
            if data:
                return {
                    "id": data["id"],
                    "title": data.get("title", {}).get("english") or data.get("title", {}).get("romaji") or title,
                    "romaji": data.get("title", {}).get("romaji"),
                    "total_chapters": data.get("chapters"),
                    "status": data.get("status"),
                    "cover": data.get("coverImage", {}).get("medium")
                }
    except Exception:
        pass
    return None


def update_anilist_progress(
    token: str,
    title: str,
    chapter_num: float,
    media_id: Optional[int] = None
) -> Dict[str, Any]:
    """Updates user reading progress on AniList."""
    if not token:
        return {"success": False, "error": "AniList token not configured"}

    # Resolve media ID if not already provided
    target_id = media_id
    resolved_title = title
    if not target_id:
        found = search_anilist_manga(title, token=token)
        if found:
            target_id = found["id"]
            resolved_title = found["title"]
        else:
            return {"success": False, "error": f"Could not find manga '{title}' on AniList"}

    mutation = """
    mutation ($mediaId: Int, $progress: Int) {
      SaveMediaListEntry(mediaId: $mediaId, progress: $progress, status: CURRENT) {
        id
        mediaId
        progress
        status
      }
    }
    """
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        r = requests.post(
            ANILIST_API_URL,
            json={"query": mutation, "variables": {"mediaId": target_id, "progress": int(chapter_num)}},
            headers=headers,
            timeout=12
        )
        data = r.json()
        if r.status_code == 200 and data.get("data", {}).get("SaveMediaListEntry"):
            entry = data["data"]["SaveMediaListEntry"]
            return {
                "success": True,
                "service": "AniList",
                "media_id": target_id,
                "title": resolved_title,
                "progress": entry.get("progress"),
                "status": entry.get("status")
            }
        errors = data.get("errors", [{}])
        err_msg = errors[0].get("message") if errors else f"HTTP {r.status_code}"
        return {"success": False, "error": err_msg}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- MyAnimeList Operations ---

def verify_mal_token(access_token: str) -> Dict[str, Any]:
    """Verifies that the provided MyAnimeList access token is valid."""
    if not access_token or not access_token.strip():
        return {"success": False, "error": "MAL access token cannot be empty"}

    headers = {"Authorization": f"Bearer {access_token.strip()}"}
    try:
        r = requests.get(f"{MAL_API_URL}/users/@me", headers=headers, timeout=12)
        if r.status_code == 200:
            user = r.json()
            return {
                "success": True,
                "user_id": user.get("id"),
                "username": user.get("name"),
                "avatar": user.get("picture")
            }
        return {"success": False, "error": f"HTTP {r.status_code}: {r.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_mal_manga(title: str, access_token: str) -> Optional[Dict[str, Any]]:
    """Searches MyAnimeList for a manga/manhua by title."""
    if not title or not access_token:
        return None

    clean_title = re.sub(r'(?i)\b(manhwa|manhua|manga|webtoon|raw|scan|chapter.*)\b', '', title).strip()
    headers = {"Authorization": f"Bearer {access_token.strip()}"}
    params = {"q": clean_title or title, "limit": 1}

    try:
        r = requests.get(f"{MAL_API_URL}/manga", headers=headers, params=params, timeout=12)
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                node = data[0].get("node", {})
                return {
                    "id": node.get("id"),
                    "title": node.get("title"),
                    "cover": node.get("main_picture", {}).get("medium")
                }
    except Exception:
        pass
    return None


def update_mal_progress(
    access_token: str,
    title: str,
    chapter_num: float,
    manga_id: Optional[int] = None
) -> Dict[str, Any]:
    """Updates user reading progress on MyAnimeList."""
    if not access_token:
        return {"success": False, "error": "MyAnimeList access token not configured"}

    target_id = manga_id
    resolved_title = title
    if not target_id:
        found = search_mal_manga(title, access_token)
        if found:
            target_id = found["id"]
            resolved_title = found["title"]
        else:
            return {"success": False, "error": f"Could not find manga '{title}' on MyAnimeList"}

    headers = {"Authorization": f"Bearer {access_token.strip()}"}
    data = {
        "num_chapters_read": int(chapter_num),
        "status": "reading"
    }

    try:
        r = requests.patch(f"{MAL_API_URL}/manga/{target_id}/my_list_status", headers=headers, data=data, timeout=12)
        if r.status_code == 200:
            res_data = r.json()
            return {
                "success": True,
                "service": "MyAnimeList",
                "manga_id": target_id,
                "title": resolved_title,
                "progress": res_data.get("num_chapters_read"),
                "status": res_data.get("status")
            }
        return {"success": False, "error": f"HTTP {r.status_code}: {r.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# --- Unified Scrobbler Dispatcher ---

def sync_trackers(
    title: str,
    chapter_num: float,
    anilist_id: Optional[int] = None,
    mal_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Checks stored database settings and dispatches progress updates
    to enabled trackers (AniList and/or MyAnimeList).
    """
    from database.db import get_setting

    results = {}

    # 1. AniList Sync
    if get_setting("anilist_enabled", "false") == "true":
        token = get_setting("anilist_token", "")
        if token:
            results["anilist"] = update_anilist_progress(
                token=token,
                title=title,
                chapter_num=chapter_num,
                media_id=anilist_id
            )

    # 2. MyAnimeList Sync
    if get_setting("mal_enabled", "false") == "true":
        mal_token = get_setting("mal_token", "")
        if mal_token:
            results["mal"] = update_mal_progress(
                access_token=mal_token,
                title=title,
                chapter_num=chapter_num,
                manga_id=mal_id
            )

    return results
