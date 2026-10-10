from io import BytesIO
from typing import Optional, Tuple
from PIL import Image

# Prevent DecompressionBombError on ultra-tall vertical webtoon strips
Image.MAX_IMAGE_PIXELS = None

def optimize_panel_image(
    raw_bytes: bytes,
    max_width: Optional[int] = 1080,
    jpeg_quality: int = 75
) -> Optional[bytes]:
    """
    Safely process, resize, and convert a panel image to clean RGB JPEG bytes.
    - Handles RGBA / LA transparency by compositing over pure white background.
    - Prevents black background artifacts.
    - Bilinear downscales if width > max_width to keep mobile/Termux RAM and storage lightweight.
    """
    try:
        with Image.open(BytesIO(raw_bytes)) as im:
            # Handle transparency safely
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                im_rgba = im.convert("RGBA")
                bg = Image.new("RGB", im_rgba.size, (255, 255, 255))
                bg.paste(im_rgba, mask=im_rgba.split()[3])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")

            # Downsample if wider than max_width
            if max_width and im.width > max_width:
                ratio = max_width / float(im.width)
                new_height = int(float(im.height) * float(ratio))
                im = im.resize((max_width, new_height), Image.Resampling.BILINEAR)

            out_buf = BytesIO()
            im.save(out_buf, format="JPEG", quality=jpeg_quality, optimize=True)
            return out_buf.getvalue()
    except Exception:
        return None

