import os
from io import BytesIO
from typing import List, Optional, Tuple
from PIL import Image

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# Disable DecompressionBombError for long strips
Image.MAX_IMAGE_PIXELS = None

DEFAULT_ASPECT_RATIO = 1.414  # Standard portrait aspect ratio (close to 3:4 and ISO 1:√2)


def find_gutter_cut_points_numpy(
    im_gray: Image.Image,
    target_height: int,
    variance_threshold: float = 6.0
) -> List[int]:
    """
    Locates natural comic gutters (horizontal bands of uniform color/whitespace)
    using row-wise standard deviation across the image width.
    """
    arr = np.array(im_gray)
    h, w = arr.shape
    row_std = arr.std(axis=1)

    cuts = [0]
    curr_y = 0

    while curr_y < h:
        remaining = h - curr_y
        # If remaining height is close to target_height, keep it as the final slice
        if remaining <= int(target_height * 1.25):
            cuts.append(h)
            break

        min_cut = curr_y + int(target_height * 0.70)
        max_cut = min(h, curr_y + int(target_height * 1.30))
        window_std = row_std[min_cut:max_cut]

        # Detect rows below the variance threshold (uniform gutters)
        gutters = np.where(window_std < variance_threshold)[0]
        if len(gutters) > 0:
            # Group into contiguous chunks of gutter rows
            diffs = np.diff(gutters)
            split_points = np.where(diffs > 1)[0] + 1
            chunks = np.split(gutters, split_points)

            # Choose the widest gutter chunk
            best_chunk = max(chunks, key=lambda c: len(c))
            cut_offset = int(np.median(best_chunk))
            cut_y = min_cut + cut_offset
        else:
            # Fallback: slice at the row with the absolute lowest variance (least visual detail)
            cut_y = min_cut + int(np.argmin(window_std))

        # Guarantee forward progress
        if cut_y <= curr_y:
            cut_y = min(h, curr_y + target_height)

        cuts.append(cut_y)
        curr_y = cut_y

    return cuts


def find_gutter_cut_points_pillow(
    im_gray: Image.Image,
    target_height: int,
    step_sample: int = 4
) -> List[int]:
    """
    Pure Pillow fallback when NumPy is unavailable. Samples horizontal rows to find
    bands with minimal pixel variation.
    """
    w, h = im_gray.size
    cuts = [0]
    curr_y = 0

    while curr_y < h:
        remaining = h - curr_y
        if remaining <= int(target_height * 1.25):
            cuts.append(h)
            break

        min_cut = curr_y + int(target_height * 0.70)
        max_cut = min(h, curr_y + int(target_height * 1.30))

        best_y = curr_y + target_height
        best_diff = float("inf")

        # Sample rows in search window
        for y in range(min_cut, max_cut, step_sample):
            # Sample row pixels
            box = (0, y, w, y + 1)
            row_crop = im_gray.crop(box)
            extrema = row_crop.getextrema()
            diff = extrema[1] - extrema[0]
            if diff < best_diff:
                best_diff = diff
                best_y = y
                if diff <= 2:  # Found near-perfect uniform row
                    break

        cuts.append(best_y)
        curr_y = best_y

    return cuts


def slice_panel_image(
    raw_bytes: bytes,
    target_aspect_ratio: float = DEFAULT_ASPECT_RATIO,
    jpeg_quality: int = 75,
    min_strip_aspect: float = 1.85
) -> List[bytes]:
    """
    Splits tall vertical webtoon strips into readable pages.
    - If panel aspect ratio is below min_strip_aspect, returns raw_bytes unaltered.
    - If panel is a vertical strip, cuts along natural panel gutters.
    """
    try:
        with Image.open(BytesIO(raw_bytes)) as im:
            w, h = im.size
            current_aspect = h / float(w)

            # Not an ultra-tall ribbon; leave as is
            if current_aspect < min_strip_aspect:
                return [raw_bytes]

            target_height = int(w * target_aspect_ratio)

            # Convert to RGB (handle transparency)
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                im_rgba = im.convert("RGBA")
                bg = Image.new("RGB", im_rgba.size, (255, 255, 255))
                bg.paste(im_rgba, mask=im_rgba.split()[3])
                rgb_im = bg
            elif im.mode != "RGB":
                rgb_im = im.convert("RGB")
            else:
                rgb_im = im

            # Convert to grayscale for gutter analysis
            gray_im = rgb_im.convert("L")

            if HAS_NUMPY:
                cuts = find_gutter_cut_points_numpy(gray_im, target_height)
            else:
                cuts = find_gutter_cut_points_pillow(gray_im, target_height)

            if len(cuts) <= 2 and cuts[-1] == h:
                # Could not find multiple cuts, return original
                return [raw_bytes]

            sliced_pages: List[bytes] = []
            for i in range(len(cuts) - 1):
                y1 = cuts[i]
                y2 = cuts[i + 1]
                if y2 <= y1:
                    continue

                crop_box = (0, y1, w, y2)
                page_img = rgb_im.crop(crop_box)

                out_buf = BytesIO()
                page_img.save(out_buf, format="JPEG", quality=jpeg_quality, optimize=True)
                sliced_pages.append(out_buf.getvalue())

            return sliced_pages if sliced_pages else [raw_bytes]
    except Exception:
        # On any processing error, gracefully return original bytes
        return [raw_bytes]


def slice_chapter_panels(
    panel_bytes_list: List[bytes],
    target_aspect_ratio: float = DEFAULT_ASPECT_RATIO,
    jpeg_quality: int = 75
) -> List[bytes]:
    """
    Processes an entire chapter's panel list, slicing any tall ribbons into pages
    while preserving original single/double-page spreads.
    """
    output_pages: List[bytes] = []
    for raw_bytes in panel_bytes_list:
        pages = slice_panel_image(
            raw_bytes=raw_bytes,
            target_aspect_ratio=target_aspect_ratio,
            jpeg_quality=jpeg_quality
        )
        output_pages.extend(pages)
    return output_pages
