import re
import html
from typing import Dict, Any, Optional, List
import requests

MANGADEX_API_URL = "https://api.mangadex.org"
ANILIST_API_URL = "https://graphql.anilist.co"


def clean_search_title(title: str) -> str:
    """Strips aggregator noise, chapter numbers, and scanlation suffixes from title."""
    if not title:
        return ""
    # 1. Remove bracketed tags like [Official], (Color), (Manhua)
    cleaned = re.sub(r'\[.*?\]|\(.*?\)', '', title)
    # 2. Remove chapter and season numbers
    cleaned = re.sub(r'(?i)\b(chapter|ch\.?|season|s|episode|ep\.?|vol\.?|volume)\s*\d+.*', '', cleaned)
    # 3. Remove common taxonomy keywords
    cleaned = re.sub(r'(?i)\b(manhwa|manhua|manga|webtoon|raw|scan|scans|official)\b', '', cleaned)
    # 4. Remove special punctuation
    cleaned = re.sub(r'[_:!\-–—]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or title



def fetch_mangadex_metadata(title: str) -> Optional[Dict[str, Any]]:
    """Queries MangaDex API for rich metadata, authors, artists, genres, and synopsis."""
    clean_title = clean_search_title(title)
    if not clean_title:
        return None

    params = {
        "title": clean_title,
        "limit": 1,
        "includes[]": ["author", "artist", "cover_art"]
    }

    try:
        r = requests.get(f"{MANGADEX_API_URL}/manga", params=params, timeout=12)
        if r.status_code != 200:
            return None
        data = r.json()
        manga_list = data.get("data", [])
        if not manga_list:
            return None

        manga = manga_list[0]
        manga_id = manga.get("id")
        attrs = manga.get("attributes", {})
        rels = manga.get("relationships", [])

        # Extract title
        title_obj = attrs.get("title", {})
        canonical_title = title_obj.get("en") or title_obj.get("ja-ro") or title_obj.get("ko-ro") or list(title_obj.values())[0] if title_obj else title

        # Alt titles
        alt_titles = []
        for alt_item in attrs.get("altTitles", []):
            alt_titles.extend(list(alt_item.values()))

        # Authors and Artists
        authors = [rel.get("attributes", {}).get("name") for rel in rels if rel.get("type") == "author" and rel.get("attributes")]
        artists = [rel.get("attributes", {}).get("name") for rel in rels if rel.get("type") == "artist" and rel.get("attributes")]

        # Genres and Tags
        tags = []
        genres = []
        for tag in attrs.get("tags", []):
            t_name = tag.get("attributes", {}).get("name", {}).get("en")
            t_group = tag.get("attributes", {}).get("group")
            if t_name:
                if t_group == "genre":
                    genres.append(t_name)
                else:
                    tags.append(t_name)

        # Synopsis
        desc_obj = attrs.get("description", {})
        synopsis = desc_obj.get("en") or (list(desc_obj.values())[0] if desc_obj else "")

        # Year
        year = attrs.get("year")

        # Status
        raw_status = attrs.get("status", "ongoing")
        status = raw_status.capitalize() if raw_status else "Ongoing"

        # Content Rating
        rating_map = {
            "safe": "Everyone",
            "suggestive": "Teen",
            "erotica": "Mature 17+",
            "pornographic": "Adult 18+"
        }
        age_rating = rating_map.get(attrs.get("contentRating", "safe"), "Everyone")

        # Cover image
        cover_filename = None
        for rel in rels:
            if rel.get("type") == "cover_art" and rel.get("attributes"):
                cover_filename = rel.get("attributes", {}).get("fileName")
                break
        cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{cover_filename}" if cover_filename else None

        return {
            "title": canonical_title,
            "alt_titles": alt_titles[:5],
            "author": ", ".join(authors) if authors else None,
            "artist": ", ".join(artists) if artists else None,
            "genres": genres,
            "tags": tags,
            "synopsis": synopsis,
            "status": status,
            "year": year,
            "age_rating": age_rating,
            "cover_url": cover_url,
            "mangadex_id": manga_id
        }
    except Exception:
        return None


def fetch_anilist_metadata(title: str) -> Optional[Dict[str, Any]]:
    """Fallback query to AniList GraphQL API for series metadata."""
    clean_title = clean_search_title(title)
    if not clean_title:
        return None

    query = """
    query ($search: String) {
      Media(search: $search, type: MANGA) {
        id
        title {
          romaji
          english
          native
        }
        description(asHtml: false)
        genres
        tags {
          name
        }
        status
        startDate {
          year
        }
        coverImage {
          large
        }
      }
    }
    """
    try:
        r = requests.post(ANILIST_API_URL, json={"query": query, "variables": {"search": clean_title}}, timeout=12)
        if r.status_code != 200:
            return None
        media = r.json().get("data", {}).get("Media")
        if not media:
            return None

        canonical_title = media.get("title", {}).get("english") or media.get("title", {}).get("romaji") or title
        tags = [t.get("name") for t in media.get("tags", []) if t.get("name")]
        genres = media.get("genres", [])
        status = media.get("status", "RELEASING").replace("_", " ").title()

        return {
            "title": canonical_title,
            "author": None,
            "artist": None,
            "genres": genres,
            "tags": tags[:8],
            "synopsis": media.get("description", ""),
            "status": status,
            "year": media.get("startDate", {}).get("year"),
            "age_rating": "Teen",
            "cover_url": media.get("coverImage", {}).get("large"),
            "anilist_id": media.get("id")
        }
    except Exception:
        return None


def fetch_rich_metadata(title: str) -> Dict[str, Any]:
    """
    Unified metadata scraper with primary MangaDex query and secondary AniList fallback.
    Returns standard metadata structure.
    """
    meta = fetch_mangadex_metadata(title)
    if not meta:
        meta = fetch_anilist_metadata(title)

    if not meta:
        meta = {
            "title": title,
            "author": "Unknown",
            "artist": "Unknown",
            "genres": ["Manga"],
            "tags": [],
            "synopsis": "",
            "status": "Ongoing",
            "age_rating": "Everyone",
            "year": None
        }

    return meta


def generate_rich_comicinfo(
    metadata: Dict[str, Any],
    chapter_num: float,
    chapter_title: Optional[str] = None,
    page_count: int = 0,
    source_url: Optional[str] = None
) -> str:
    """
    Builds a full schema-compliant ComicInfo.xml for ComicRack, Komga, and Kavita.
    """
    series_title = html.escape(metadata.get("title") or "Unknown Series")
    writer = html.escape(metadata.get("author") or "")
    penciller = html.escape(metadata.get("artist") or "")
    summary = html.escape(metadata.get("synopsis") or "")
    genres_str = html.escape(", ".join(metadata.get("genres") or []))
    tags_str = html.escape(", ".join(metadata.get("tags") or []))
    web = html.escape(source_url or "")
    age_rating = html.escape(metadata.get("age_rating") or "Everyone")
    year_tag = f"  <Year>{metadata['year']}</Year>\n" if metadata.get("year") else ""
    ch_name = html.escape(chapter_title or f"Chapter {chapter_num}")

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Series>{series_title}</Series>
  <Title>{ch_name}</Title>
  <Number>{chapter_num:g}</Number>
  <Summary>{summary}</Summary>
  <Writer>{writer}</Writer>
  <Penciller>{penciller}</Penciller>
  <Genre>{genres_str}</Genre>
  <Tags>{tags_str}</Tags>
  <AgeRating>{age_rating}</AgeRating>
{year_tag}  <PageCount>{page_count}</PageCount>
  <Format>Digital</Format>
  <Manga>YesAndRightToLeft</Manga>
  <Web>{web}</Web>
</ComicInfo>
"""
    return xml
