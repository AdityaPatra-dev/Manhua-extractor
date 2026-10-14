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


TITLE_STOP_WORDS = {"the", "a", "an", "of", "and", "in", "on", "at", "to", "for", "with", "where", "is", "it"}

def _distinctive_content_match(s1: str, s2: str) -> bool:
    c1 = set(normalize_title(s1).split()) - TITLE_STOP_WORDS
    c2 = set(normalize_title(s2).split()) - TITLE_STOP_WORDS
    if not c1 or not c2:
        return False
    inter = len(c1 & c2)
    return (inter >= 3 and inter / max(len(c1), len(c2)) >= 0.70) or (inter >= 2 and (c1.issubset(c2) or c2.issubset(c1)))

def is_same_series(
    title1: str,
    title2: str,
    alt_titles1: Optional[List[str]] = None,
    alt_titles2: Optional[List[str]] = None,
    threshold: float = 0.80
) -> bool:
    """Determine if two titles represent the same underlying series."""
    # Direct token match or distinctive content words match
    if token_sort_ratio(title1, title2) >= threshold or _distinctive_content_match(title1, title2):
        return True

    # Cross-reference alternative titles
    all_t1 = [title1] + (alt_titles1 or [])
    all_t2 = [title2] + (alt_titles2 or [])

    for t1 in all_t1:
        for t2 in all_t2:
            if token_sort_ratio(t1, t2) >= threshold or _distinctive_content_match(t1, t2):
                return True

    return False


def compute_relevance_score(query: str, title: str, alt_titles: Optional[List[str]] = None) -> float:
    """Compute a search query relevance score (0.0 to 1000.0) against title and alternative titles."""
    norm_q = normalize_title(query)
    norm_t = normalize_title(title)
    if not norm_q:
        return 500.0

    candidates = [norm_t] + [normalize_title(a) for a in (alt_titles or []) if a]
    q_words = norm_q.split()
    best = 0.0

    for cand in candidates:
        if not cand:
            continue
        full_ratio = difflib.SequenceMatcher(None, norm_q, cand).ratio()
        if norm_q == cand:
            score = 1000.0
        elif cand.startswith(norm_q):
            score = 850.0 - min(len(cand) - len(norm_q), 50)
        elif norm_q in cand:
            score = 750.0 - min(len(cand) - len(norm_q), 50)
        elif all(w in cand.split() for w in q_words):
            score = 650.0 + (full_ratio * 50.0)
        else:
            c_words = cand.split()
            word_matches = 0
            for qw in q_words:
                if any(qw == cw or (len(qw) >= 4 and difflib.SequenceMatcher(None, qw, cw).ratio() >= 0.75) for cw in c_words):
                    word_matches += 1

            # If query has multiple words and we only matched a partial fraction, penalize heavily
            # so partial collisions from aggregators (e.g. matching 'leveling' in 'Urban Leveling') are dropped!
            if len(q_words) >= 2 and word_matches < len(q_words):
                if full_ratio < 0.8:
                    score = full_ratio * 90.0
                else:
                    score = full_ratio * 350.0
            else:
                token_ratio = word_matches / max(len(q_words), 1)
                token_score = token_ratio * 500.0
                fuzzy_score = full_ratio * 400.0
                score = max(token_score, fuzzy_score) + (full_ratio * 50.0)

        if score > best:
            best = score

    return best


def pick_best_canonical_title(title: str, alt_titles: Optional[List[str]] = None, query: str = "") -> str:
    """
    Select the most user-friendly canonical title for display.
    If a query was provided, pick the title/alias that matches the query best (e.g. 'Solo Leveling'
    instead of the Korean romanization 'Na Honjaman Level-Up').
    """
    candidates = [title] + [a for a in (alt_titles or []) if a and isinstance(a, str)]
    if not candidates:
        return title or "Unknown Series"

    if not query:
        # Prefer the shortest Latin title or original title
        return candidates[0]

    norm_q = normalize_title(query)
    best_cand = candidates[0]
    best_score = -1.0

    for cand in candidates:
        score = compute_relevance_score(norm_q, cand)
        # Give slight tie-break preference to English ASCII titles
        if cand.isascii():
            score += 5.0
        if score > best_score:
            best_score = score
            best_cand = cand

    return best_cand


def cluster_search_results(raw_hits: List[Dict[str, Any]], query: str = "") -> List[Dict[str, Any]]:
    """Group individual search hits from multiple websites into unified canonical series objects."""
    clusters: List[Dict[str, Any]] = []

    for hit in raw_hits:
        hit_title = hit.get("title") or "Unknown"
        hit_alt = hit.get("alt_titles") or []
        series_url = hit.get("series_url") or hit.get("url") or ""
        hit_source = {
            "source_key": hit.get("source_key", "unknown"),
            "source_name": hit.get("source_name", "Unknown Source"),
            "source_logo": hit.get("source_logo") or f"/docs/logos/{hit.get('source_key', 'heuristic')}.png",
            "series_url": series_url,
            "url": series_url,
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
                if hit_source["latest_chapter_num"] > matched_cluster["max_chapter_num"]:
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
                if not matched_cluster.get("series_url") and series_url:
                    matched_cluster["series_url"] = series_url
                    matched_cluster["url"] = series_url
        else:
            # Create a new canonical cluster
            canonical_slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalize_title(hit_title)).strip("-")
            ch_num = hit_source["latest_chapter_num"]
            new_cluster = {
                "canonical_id": canonical_slug or "series",
                "canonical_title": hit_title,
                "title": hit_title,
                "series_url": series_url,
                "url": series_url,
                "alt_titles": [a for a in hit_alt if a],
                "synopsis": hit.get("synopsis") or "",
                "cover_url": hit.get("cover_url") or "",
                "status": hit.get("status") or "Ongoing",
                "latest_chapter": hit_source["latest_chapter"],
                "latest_chapter_num": ch_num,
                "max_chapter_num": ch_num,
                "total_sources": 1,
                "sources": [hit_source],
                "relevance_score": 0.0
            }
            clusters.append(new_cluster)

    # Post-process clusters: canonical titles, accurate chapter format, and relevance scoring
    for c in clusters:
        # Pick best canonical title for display (matching query if available)
        c["canonical_title"] = pick_best_canonical_title(c["title"], c.get("alt_titles", []), query)

        # Determine absolute max chapter number across all sources in this cluster
        max_ch = max([s["latest_chapter_num"] for s in c["sources"]] + [c.get("max_chapter_num", 0.0)])
        c["max_chapter_num"] = max_ch
        c["latest_chapter_num"] = max_ch
        if max_ch > 1.0:
            c["latest_chapter"] = f"Chapter {int(max_ch) if max_ch.is_integer() else max_ch:g}"
        elif c.get("latest_chapter") == "Chapter 1":
            c["latest_chapter"] = "Available"

        # Compute query relevance score
        c["relevance_score"] = compute_relevance_score(query, c["canonical_title"], c.get("alt_titles", []))

        # Sort sources inside each cluster by latest_chapter_num DESC, then latency ASC
        c["sources"].sort(key=lambda s: (s["latest_chapter_num"], -s["latency_ms"]), reverse=True)

    # If query is provided, discard results below cutoff
    if query and len(query.strip()) >= 2:
        clusters = [c for c in clusters if c["relevance_score"] >= 140.0]

        # USER INSTRUCTION: If there are recommendations with MULTIPLE SOURCES (>= 2),
        # suppress low-relevance 1-source noise (especially partial matches from MangaHere / MangaPill, doujinshi, etc.)
        multi_source_clusters = [c for c in clusters if c["total_sources"] >= 2]
        if multi_source_clusters:
            top_multi_score = max(c["relevance_score"] for c in multi_source_clusters)
            filtered = []
            for c in clusters:
                if c["total_sources"] >= 2:
                    filtered.append(c)
                else:
                    title_lower = c["canonical_title"].lower()
                    is_noise = any(tag in title_lower for tag in ["doujinshi", "fan comic", "anthology", "parody", "tribute"])
                    if "novel" in title_lower and "novel" not in query.lower():
                        is_noise = True
                    # Only keep 1-source hits if they have high relevance (>= 750 or near top multi-source score)
                    if not is_noise and c["relevance_score"] >= max(750.0, top_multi_score * 0.85):
                        filtered.append(c)
            clusters = filtered

    # Sort clusters strictly by relevancy first, then max_chapter_num DESC, then total_sources DESC
    clusters.sort(key=lambda c: (c["relevance_score"], c["max_chapter_num"], c["total_sources"]), reverse=True)
    return clusters

