import os
import zipfile
from io import BytesIO
from typing import List, Optional
from PIL import Image
try:
    import img2pdf
except ImportError:
    img2pdf = None

def compile_pdf(image_bytes_list: List[bytes], output_path: str) -> bool:
    """Compile a list of JPEG image bytes into a single PDF document."""
    if not image_bytes_list:
        return False

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if img2pdf is not None:
        try:
            pdf_bytes = img2pdf.convert(image_bytes_list)
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
            return True
        except Exception:
            pass

    # Fallback to Pillow PDF assembly if img2pdf is unavailable or fails
    try:
        pil_images = [Image.open(BytesIO(b)) for b in image_bytes_list]
        if pil_images:
            pil_images[0].save(
                output_path,
                "PDF",
                resolution=100.0,
                save_all=True,
                append_images=pil_images[1:]
            )
            return True
    except Exception:
        return False
    return False

def detect_image_extension(img_bytes: bytes) -> str:
    """Detect appropriate file extension from image header bytes."""
    if len(img_bytes) >= 12 and img_bytes[:4] == b"RIFF" and img_bytes[8:12] == b"WEBP":
        return "webp"
    if len(img_bytes) >= 8 and img_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return "jpg"


def compile_cbz(
    image_bytes_list: List[bytes],
    output_path: str,
    series_title: Optional[str] = None,
    chapter_num: Optional[float] = None,
    source_url: Optional[str] = None,
    chapter_title: Optional[str] = None,
    metadata: Optional[dict] = None
) -> bool:
    """Compile images into a standard CBZ archive with rich ComicInfo.xml metadata."""
    if not image_bytes_list:
        return False

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    try:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Write page files
            for i, img_bytes in enumerate(image_bytes_list):
                ext = detect_image_extension(img_bytes)
                page_name = f"page_{i+1:03d}.{ext}"
                zf.writestr(page_name, img_bytes)

            # Generate ComicInfo.xml
            if metadata:
                from core.metadata import generate_rich_comicinfo
                comic_info = generate_rich_comicinfo(
                    metadata=metadata,
                    chapter_num=chapter_num or 1.0,
                    chapter_title=chapter_title,
                    page_count=len(image_bytes_list),
                    source_url=source_url
                )
            else:
                comic_info = f"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Series>{series_title or 'Unknown Series'}</Series>
  <Number>{chapter_num or 1}</Number>
  <PageCount>{len(image_bytes_list)}</PageCount>
  <Web>{source_url or ''}</Web>
</ComicInfo>
"""
            zf.writestr("ComicInfo.xml", comic_info.encode("utf-8"))
        return True
    except Exception:
        return False

def save_raw_images(image_bytes_list: List[bytes], folder_path: str) -> bool:
    """Save images into a raw chapter folder."""
    if not image_bytes_list:
        return False

    try:
        os.makedirs(folder_path, exist_ok=True)
        for i, img_bytes in enumerate(image_bytes_list):
            ext = detect_image_extension(img_bytes)
            file_name = os.path.join(folder_path, f"{i+1:03d}.{ext}")
            with open(file_name, "wb") as f:
                f.write(img_bytes)
        return True
    except Exception:
        return False


def get_chapter_page_count(file_path: str, file_format: str) -> int:
    """Return total number of pages in a compiled chapter (CBZ, Folder, or PDF)."""
    if not os.path.exists(file_path):
        return 0
    if file_format == "cbz":
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                return len([n for n in zf.namelist() if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
        except Exception:
            return 0
    elif file_format == "folder":
        try:
            return len([f for f in os.listdir(file_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
        except Exception:
            return 0
    elif file_format == "pdf":
        try:
            import pikepdf
            with pikepdf.Pdf.open(file_path) as pdf:
                return len(pdf.pages)
        except Exception:
            return 0
    return 0

def get_chapter_page_bytes(file_path: str, file_format: str, page_index: int) -> Optional[bytes]:
    """Retrieve raw image bytes for a specific 0-indexed page in a compiled chapter."""
    if not os.path.exists(file_path):
        return None
    if file_format == "cbz":
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = sorted([n for n in zf.namelist() if n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
                if 0 <= page_index < len(names):
                    return zf.read(names[page_index])
        except Exception:
            return None
    elif file_format == "folder":
        try:
            names = sorted([f for f in os.listdir(file_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])
            if 0 <= page_index < len(names):
                with open(os.path.join(file_path, names[page_index]), "rb") as f:
                    return f.read()
        except Exception:
            return None
    elif file_format == "pdf":
        try:
            import pikepdf
            with pikepdf.Pdf.open(file_path) as pdf:
                if 0 <= page_index < len(pdf.pages):
                    page = pdf.pages[page_index]
                    for name, raw_img in page.get_images().items():
                        pdf_img = pikepdf.PdfImage(raw_img)
                        buf = BytesIO()
                        pdf_img.as_pil_image().save(buf, format="JPEG")
                        return buf.getvalue()
        except Exception:
            return None
    return None

