import re
import difflib
from typing import List, Dict, Any, Optional

NOISE_REGEX = re.compile(
    r"(\[.*?\]|\(.*?\)|season\s*\d+|remake|official|reboot|uncensored|webtoon|raw|comic|manga|manhua|manhwa)",
    re.IGNORECASE
)

def normalize_title(title: str) -> str:
    """Normalize a series title by stripping noise, brackets, and extra symbols."""
    if not title:
        return ""
    # Strip bracketed remarks like [Season 2], (Official), etc.
    cleaned = NOISE_REGEX.sub(" ", title)
    # Remove all non-alphanumeric characters except spaces
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned)
    # Collapse multiple whitespaces
    return " ".join(cleaned.lower().split())


def token_sort_ratio(s1: str, s2: str) -> float:
    """Compute token sort similarity ratio between two titles."""
    norm1 = normalize_title(s1)
    norm2 = normalize_title(s2)
    if not norm1 or not norm2:
        return 0.0
    if norm1 == norm2:
        return 1.0

    # Sort tokens alphabetically
    tokens1 = " ".join(sorted(norm1.split()))
    tokens2 = " ".join(sorted(norm2.split()))

    matcher = difflib.SequenceMatcher(None, tokens1, tokens2)
    return matcher.ratio()


def is_same_series(
    title1: str,
    title2: str,
    alt_titles1: Optional[List[str]] = None,
    alt_titles2: Optional[List[str]] = None,
    threshold: float = 0.82
) -> bool:
    """Determine if two titles represent the same underlying series."""
    # Direct token match
    if token_sort_ratio(title1, title2) >= threshold:
        return True

    # Cross-reference alternative titles
    all_t1 = [title1] + (alt_titles1 or [])
    all_t2 = [title2] + (alt_titles2 or [])

    for t1 in all_t1:
        for t2 in all_t2:
            if token_sort_ratio(t1, t2) >= threshold:
                return True

    return False


def cluster_search_results(raw_hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group individual search hits from multiple websites into unified canonical series objects."""
    clusters: List[Dict[str, Any]] = []

    for hit in raw_hits:
        hit_title = hit.get("title") or "Unknown"
        hit_alt = hit.get("alt_titles") or []
        hit_source = {
            "source_key": hit.get("source_key", "unknown"),
            "source_name": hit.get("source_name", "Unknown Source"),
            "source_logo": hit.get("source_logo") or f"/docs/logos/{hit.get('source_key', 'heuristic')}.png",
            "series_url": hit.get("series_url") or "",
            "latest_chapter": hit.get("latest_chapter") or "Chapter 1",
            "latest_chapter_num": float(hit.get("latest_chapter_num") or 0.0),
            "quality_tag": hit.get("quality_tag", "Standard"),
            "latency_ms": int(hit.get("latency_ms") or 0)
        }

        matched_cluster = None
        for c in clusters:
            if is_same_series(hit_title, c["title"], hit_alt, c.get("alt_titles")):
                matched_cluster = c
                break

        if matched_cluster:
            # Append source if not already present for this source_key
            existing_keys = [s["source_key"] for s in matched_cluster["sources"]]
            if hit_source["source_key"] not in existing_keys:
                matched_cluster["sources"].append(hit_source)
                matched_cluster["total_sources"] = len(matched_cluster["sources"])
                # Update latest chapter if this source has a higher chapter number
                if hit_source["latest_chapter_num"] > matched_cluster["latest_chapter_num"]:
                    matched_cluster["latest_chapter_num"] = hit_source["latest_chapter_num"]
                    matched_cluster["max_chapter_num"] = hit_source["latest_chapter_num"]
                    matched_cluster["latest_chapter"] = hit_source["latest_chapter"]
                # Collect alternative titles
                for a in hit_alt:
                    if a and a not in matched_cluster["alt_titles"]:
                        matched_cluster["alt_titles"].append(a)
                # Upgrade cover if current cover is generic or missing
                if not matched_cluster.get("cover_url") and hit.get("cover_url"):
                    matched_cluster["cover_url"] = hit.get("cover_url")
        else:
            # Create a new canonical cluster
            canonical_slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalize_title(hit_title)).strip("-")
            new_cluster = {
                "canonical_id": canonical_slug or "series",
                "canonical_title": hit_title,
                "title": hit_title,
                "alt_titles": [a for a in hit_alt if a],
                "synopsis": hit.get("synopsis") or "",
                "cover_url": hit.get("cover_url") or "",
                "status": hit.get("status") or "Ongoing",
                "latest_chapter": hit_source["latest_chapter"],
                "latest_chapter_num": hit_source["latest_chapter_num"],
                "max_chapter_num": hit_source["latest_chapter_num"],
                "total_sources": 1,
                "sources": [hit_source]
            }
            clusters.append(new_cluster)

    # Sort sources inside each cluster by latest_chapter_num DESC, then latency ASC
    for c in clusters:
        c["sources"].sort(key=lambda s: (s["latest_chapter_num"], -s["latency_ms"]), reverse=True)

    # Sort clusters by total sources DESC, then latest_chapter_num DESC
    clusters.sort(key=lambda c: (c["total_sources"], c["latest_chapter_num"]), reverse=True)
    return clusters
