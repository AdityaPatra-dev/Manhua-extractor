import os
import shutil
import tempfile
import subprocess
from io import BytesIO
from typing import Optional, Dict, Any, List
from PIL import Image
import requests

DEFAULT_UPSCALER_URL = "http://localhost:5000/upscale"


def is_upscaler_api_available(endpoint: str = DEFAULT_UPSCALER_URL, timeout: float = 3.0) -> bool:
    """Check if an external Waifu2x or Real-ESRGAN HTTP microservice is running."""
    try:
        # Check health or root endpoint
        base = endpoint.split("/upscale")[0]
        r = requests.get(f"{base}/health" if "/upscale" in endpoint else endpoint, timeout=timeout)
        return r.status_code in (200, 404, 405)
    except Exception:
        return False


def get_available_upscalers() -> Dict[str, bool]:
    """Detect local CLI binaries and microservice availability."""
    return {
        "waifu2x_cli": shutil.which("waifu2x-ncnn-vulkan") is not None,
        "realesrgan_cli": shutil.which("realesrgan-ncnn-vulkan") is not None,
        "api": is_upscaler_api_available()
    }


def upscale_with_api(raw_bytes: bytes, endpoint: str = DEFAULT_UPSCALER_URL, scale: int = 2, timeout: float = 30.0) -> Optional[bytes]:
    """Sends image bytes to an AI upscaler HTTP microservice (Waifu2x / Real-ESRGAN)."""
    try:
        files = {"image": ("panel.jpg", raw_bytes, "image/jpeg")}
        data = {"scale": str(scale), "noise": "1"}
        r = requests.post(endpoint, files=files, data=data, timeout=timeout)
        if r.status_code == 200 and len(r.content) > 1024:
            return r.content
    except Exception:
        pass
    return None


def upscale_with_cli(raw_bytes: bytes, binary_name: str, scale: int = 2) -> Optional[bytes]:
    """Runs a local ncnn-vulkan CLI binary on the image bytes."""
    binary_path = shutil.which(binary_name)
    if not binary_path:
        return None

    with tempfile.TemporaryDirectory(prefix="manhua_upscale_") as tmpdir:
        in_path = os.path.join(tmpdir, "input.png")
        out_path = os.path.join(tmpdir, "output.png")
        try:
            with open(in_path, "wb") as f:
                f.write(raw_bytes)

            cmd = [binary_path, "-i", in_path, "-o", out_path, "-s", str(scale)]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if res.returncode == 0 and os.path.exists(out_path):
                with open(out_path, "rb") as f:
                    return f.read()
        except Exception:
            pass
    return None


def upscale_with_lanczos(raw_bytes: bytes, scale: int = 2) -> bytes:
    """High-quality Lanczos-4 supersampling fallback when no neural hardware is active."""
    with Image.open(BytesIO(raw_bytes)) as im:
        new_w = int(im.width * scale)
        new_h = int(im.height * scale)
        upscaled = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
        out_buf = BytesIO()
        upscaled.save(out_buf, format="JPEG", quality=90, optimize=True)
        return out_buf.getvalue()


def upscale_panel(
    raw_bytes: bytes,
    scale: int = 2,
    engine: str = "auto",
    endpoint: Optional[str] = None
) -> bytes:
    """
    Upscale a comic panel using AI Super-Resolution (Microservice or CLI) or Lanczos.
    Returns upscaled image bytes.
    """
    if scale <= 1 or not raw_bytes:
        return raw_bytes

    target_endpoint = endpoint or DEFAULT_UPSCALER_URL

    if engine == "api" or (engine == "auto" and endpoint):
        res = upscale_with_api(raw_bytes, endpoint=target_endpoint, scale=scale)
        if res:
            return res

    if engine in ("waifu2x", "auto"):
        res = upscale_with_cli(raw_bytes, "waifu2x-ncnn-vulkan", scale=scale)
        if res:
            return res

    if engine in ("realesrgan", "auto"):
        res = upscale_with_cli(raw_bytes, "realesrgan-ncnn-vulkan", scale=scale)
        if res:
            return res

    # If engine explicitly requires lanczos or fallback
    if engine in ("lanczos", "auto"):
        return upscale_with_lanczos(raw_bytes, scale=scale)

    return raw_bytes
