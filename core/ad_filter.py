import os
from io import BytesIO
from typing import List, Tuple, Optional, Dict, Any
from PIL import Image

# Disable DecompressionBombError for high-res images
Image.MAX_IMAGE_PIXELS = None


def compute_perceptual_hash(raw_bytes: bytes) -> Optional[str]:
    """
    Computes a robust 128-bit composite perceptual hash (64-bit dHash + 64-bit aHash).
    - Invariant to image scaling, resolution changes, and minor JPEG recompression.
    - Operates purely using Pillow with zero external C-dependencies.
    """
    try:
        with Image.open(BytesIO(raw_bytes)) as im:
            gray = im.convert("L")

            # 1. Difference Hash (dHash) - captures relative gradient changes
            resized_d = gray.resize((9, 8), Image.Resampling.BILINEAR)
            pixels_d = list(resized_d.tobytes())
            d_bits = 0
            for r in range(8):
                for c in range(8):
                    if pixels_d[r * 9 + c] > pixels_d[r * 9 + c + 1]:
                        d_bits |= 1 << (r * 8 + c)

            # 2. Average Hash (aHash) - captures overall spatial intensity distribution
            resized_a = gray.resize((8, 8), Image.Resampling.BILINEAR)
            pixels_a = list(resized_a.tobytes())
            avg = sum(pixels_a) / 64.0
            a_bits = 0
            for i, val in enumerate(pixels_a):
                if val > avg:
                    a_bits |= 1 << i

            return f"{d_bits:016x}{a_bits:016x}"
    except Exception:
        return None


def hash_distance(h1: str, h2: str) -> int:
    """
    Calculates the Hamming distance between two 128-bit composite perceptual hashes.
    A distance <= 10 indicates high visual similarity / identical promo banners.
    """
    if not h1 or not h2 or len(h1) < 32 or len(h2) < 32:
        return 999
    try:
        d1, a1 = int(h1[:16], 16), int(h1[16:32], 16)
        d2, a2 = int(h2[:16], 16), int(h2[16:32], 16)
        return bin(d1 ^ d2).count("1") + bin(a1 ^ a2).count("1")
    except Exception:
        return 999


def match_promo_signature(
    phash: str,
    known_signatures: List[Dict[str, Any]],
    default_threshold: int = 10
) -> Tuple[bool, Optional[str]]:
    """
    Compares a panel's hash against a list of known promotional signatures.
    Returns (is_match, matched_label).
    """
    if not phash or not known_signatures:
        return False, None

    for sig in known_signatures:
        sig_hash = sig.get("phash", "")
        threshold = sig.get("match_threshold", default_threshold)
        dist = hash_distance(phash, sig_hash)
        if dist <= threshold:
            label = sig.get("label") or f"Promo #{sig.get('id', 0)}"
            return True, label

    return False, None


def filter_chapter_panels(
    panel_bytes_list: List[bytes],
    known_signatures: Optional[List[Dict[str, Any]]] = None,
    default_threshold: int = 10
) -> Tuple[List[bytes], int]:
    """
    Scans a chapter's downloaded panels and removes those matching registered promo/ad hashes.
    Returns (filtered_panels, removed_count).
    """
    if not known_signatures or not panel_bytes_list:
        return panel_bytes_list, 0

    clean_panels: List[bytes] = []
    removed_count = 0

    for idx, panel_bytes in enumerate(panel_bytes_list):
        phash = compute_perceptual_hash(panel_bytes)
        if phash:
            is_promo, label = match_promo_signature(phash, known_signatures, default_threshold)
            if is_promo:
                removed_count += 1
                continue

        clean_panels.append(panel_bytes)

    # Safety safeguard: Never empty an entire chapter if all panels matched
    if not clean_panels and panel_bytes_list:
        return panel_bytes_list, 0

    return clean_panels, removed_count
