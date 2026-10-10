import os
import sys
import io
import zipfile
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from core.optimizer import optimize_panel_image

from core.compiler import compile_cbz, detect_image_extension
from core.upscaler import (
    upscale_with_lanczos,
    upscale_panel,
    get_available_upscalers,
    is_upscaler_api_available
)


class TestV21Features(unittest.TestCase):
    def setUp(self):
        # Create a sample test image (100x200 RGB)
        self.im = Image.new("RGB", (100, 200), (200, 50, 50))
        buf = io.BytesIO()
        self.im.save(buf, format="JPEG", quality=80)
        self.sample_jpeg = buf.getvalue()

    def test_webp_panel_optimization(self):
        """WebP optimization must produce valid WebP bytes."""
        webp_bytes = optimize_panel_image(
            self.sample_jpeg,
            image_format="WEBP",
            webp_quality=80
        )
        self.assertIsNotNone(webp_bytes)
        self.assertTrue(len(webp_bytes) > 0)
        self.assertEqual(detect_image_extension(webp_bytes), "webp")

        # Verify Pillow can open the resulting bytes
        with Image.open(io.BytesIO(webp_bytes)) as decoded:
            self.assertEqual(decoded.format, "WEBP")
            self.assertEqual(decoded.width, 100)
            self.assertEqual(decoded.height, 200)

    def test_detect_image_extension(self):
        """Helper should reliably detect webp, png, and jpeg from header bytes."""
        # Test WebP
        webp_buf = io.BytesIO()
        self.im.save(webp_buf, format="WEBP")
        self.assertEqual(detect_image_extension(webp_buf.getvalue()), "webp")

        # Test PNG
        png_buf = io.BytesIO()
        self.im.save(png_buf, format="PNG")
        self.assertEqual(detect_image_extension(png_buf.getvalue()), "png")

        # Test JPEG
        self.assertEqual(detect_image_extension(self.sample_jpeg), "jpg")

    def test_cbz_with_webp_panels(self):
        """CBZ compilation must preserve .webp page extensions inside archive."""
        webp_bytes = optimize_panel_image(self.sample_jpeg, image_format="WEBP")
        with tempfile.TemporaryDirectory() as tmpdir:
            cbz_path = os.path.join(tmpdir, "test_webp.cbz")
            res = compile_cbz([webp_bytes, webp_bytes], cbz_path, series_title="WebP Manga", chapter_num=1.0)
            self.assertTrue(res)
            self.assertTrue(os.path.exists(cbz_path))

            with zipfile.ZipFile(cbz_path, "r") as zf:
                namelist = zf.namelist()
                self.assertIn("page_001.webp", namelist)
                self.assertIn("page_002.webp", namelist)
                self.assertIn("ComicInfo.xml", namelist)

    def test_lanczos_upscaling(self):
        """Lanczos-4 upscaling should double width and height."""
        upscaled_bytes = upscale_with_lanczos(self.sample_jpeg, scale=2)
        self.assertIsNotNone(upscaled_bytes)
        with Image.open(io.BytesIO(upscaled_bytes)) as decoded:
            self.assertEqual(decoded.width, 200)
            self.assertEqual(decoded.height, 400)

    def test_upscale_panel_dispatcher(self):
        """upscale_panel in auto mode should fall back gracefully to lanczos."""
        res_bytes = upscale_panel(self.sample_jpeg, scale=2, engine="auto")
        self.assertIsNotNone(res_bytes)
        with Image.open(io.BytesIO(res_bytes)) as decoded:
            self.assertEqual(decoded.width, 200)
            self.assertEqual(decoded.height, 400)

    def test_upscaler_availability(self):
        """get_available_upscalers returns dictionary with expected keys."""
        avail = get_available_upscalers()
        self.assertIn("waifu2x_cli", avail)
        self.assertIn("realesrgan_cli", avail)
        self.assertIn("api", avail)


if __name__ == "__main__":
    unittest.main()
