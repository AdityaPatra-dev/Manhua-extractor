import unittest
import os
import shutil
import tempfile
import zipfile
from io import BytesIO
from PIL import Image

from core.optimizer import optimize_panel_image
from core.compiler import (
    compile_cbz,
    compile_pdf,
    save_raw_images,
    detect_file_format,
    get_chapter_page_count,
    get_chapter_page_bytes,
    detect_image_extension,
)
from core.slicer import (
    slice_panel_image,
    find_gutter_cut_points_numpy,
    find_gutter_cut_points_pillow
)


class TestCodecsAndFormats(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="manhua_test_codecs_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_dummy_image(self, width: int = 400, height: int = 600, mode: str = "RGB", color=(100, 150, 200), fmt: str = "JPEG") -> bytes:
        img = Image.new(mode, (width, height), color)
        buf = BytesIO()
        img.save(buf, format=fmt)
        return buf.getvalue()

    def test_jpeg_codec_optimization(self):
        """JPEG codec should compress and downscale if width > max_width."""
        raw = self._create_dummy_image(width=1600, height=2400, fmt="JPEG")
        optimized = optimize_panel_image(raw, max_width=800, jpeg_quality=75, image_format="JPEG")
        self.assertIsNotNone(optimized)
        self.assertLess(len(optimized), len(raw))

        with Image.open(BytesIO(optimized)) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertEqual(im.width, 800)
            self.assertEqual(im.height, 1200)

    def test_webp_codec_optimization(self):
        """WebP codec should produce clean WebP bytes with high compression efficiency."""
        raw = self._create_dummy_image(width=800, height=1200, fmt="PNG")
        optimized = optimize_panel_image(raw, max_width=800, image_format="WEBP", webp_quality=70)
        self.assertIsNotNone(optimized)

        with Image.open(BytesIO(optimized)) as im:
            self.assertEqual(im.format, "WEBP")
            self.assertEqual(im.width, 800)

    def test_png_rgba_transparency_handling(self):
        """RGBA PNG transparency must be composited over white background (no black box artifacts)."""
        # Create an RGBA image with transparent parts
        img = Image.new("RGBA", (200, 200), (0, 0, 0, 0)) # transparent
        buf = BytesIO()
        img.save(buf, format="PNG")
        raw_rgba = buf.getvalue()

        optimized = optimize_panel_image(raw_rgba, max_width=200, image_format="JPEG")
        self.assertIsNotNone(optimized)
        with Image.open(BytesIO(optimized)) as im:
            self.assertEqual(im.mode, "RGB")
            # Pixel should be white, not black
            pixel = im.getpixel((10, 10))
            self.assertEqual(pixel, (255, 255, 255))

    def test_corrupted_image_fallback(self):
        """Corrupted image bytes should fall back gracefully without crashing."""
        junk_bytes = b"NOT_A_REAL_IMAGE_BYTES_XYZ_12345678901234567890123456789012345678901234567890"
        res = optimize_panel_image(junk_bytes)
        # Should return raw bytes if length > 50 so data isn't destroyed
        self.assertEqual(res, junk_bytes)

    def test_detect_image_extension(self):
        """Header detection should correctly identify WebP, PNG, and JPEG."""
        jpeg_bytes = self._create_dummy_image(fmt="JPEG")
        png_bytes = self._create_dummy_image(fmt="PNG")
        webp_bytes = self._create_dummy_image(fmt="WEBP")

        self.assertEqual(detect_image_extension(jpeg_bytes), "jpg")
        self.assertEqual(detect_image_extension(png_bytes), "png")
        self.assertEqual(detect_image_extension(webp_bytes), "webp")

    def test_cbz_compilation_and_page_reading(self):
        """CBZ compilation must create a valid zip with ComicInfo.xml and readable pages."""
        pages = [
            self._create_dummy_image(color=(255, 0, 0), fmt="JPEG"),
            self._create_dummy_image(color=(0, 255, 0), fmt="WEBP"),
            self._create_dummy_image(color=(0, 0, 255), fmt="PNG")
        ]
        cbz_path = os.path.join(self.test_dir, "test_chapter.cbz")
        ok = compile_cbz(
            image_bytes_list=pages,
            output_path=cbz_path,
            series_title="Test Series",
            chapter_num=1.5
        )
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(cbz_path))
        self.assertEqual(detect_file_format(cbz_path), "cbz")
        self.assertEqual(get_chapter_page_count(cbz_path, "cbz"), 3)

        # Read page bytes
        page0 = get_chapter_page_bytes(cbz_path, "cbz", 0)
        self.assertIsNotNone(page0)
        self.assertEqual(page0, pages[0])

        # Validate ComicInfo.xml in zip
        with zipfile.ZipFile(cbz_path, "r") as zf:
            self.assertIn("ComicInfo.xml", zf.namelist())
            xml_text = zf.read("ComicInfo.xml").decode("utf-8")
            self.assertIn("<Series>Test Series</Series>", xml_text)
            self.assertIn("<Number>1.5</Number>", xml_text)

    def test_pdf_compilation_and_page_reading(self):
        """PDF compilation should create a valid multi-page PDF document."""
        pages = [
            self._create_dummy_image(color=(200, 100, 50), fmt="JPEG"),
            self._create_dummy_image(color=(50, 100, 200), fmt="JPEG")
        ]
        pdf_path = os.path.join(self.test_dir, "test_chapter.pdf")
        ok = compile_pdf(pages, pdf_path)
        self.assertTrue(ok)
        self.assertTrue(os.path.exists(pdf_path))
        self.assertEqual(detect_file_format(pdf_path), "pdf")
        self.assertEqual(get_chapter_page_count(pdf_path, "pdf"), 2)

    def test_raw_folder_saving_and_reading(self):
        """Folder compilation should save individual numbered panel files."""
        pages = [
            self._create_dummy_image(fmt="JPEG"),
            self._create_dummy_image(fmt="PNG")
        ]
        folder_path = os.path.join(self.test_dir, "test_folder_chapter")
        ok = save_raw_images(pages, folder_path)
        self.assertTrue(ok)
        self.assertTrue(os.path.isdir(folder_path))
        self.assertEqual(detect_file_format(folder_path), "folder")
        self.assertEqual(get_chapter_page_count(folder_path, "folder"), 2)

        p0 = get_chapter_page_bytes(folder_path, "folder", 0)
        self.assertIsNotNone(p0)

    def test_vertical_webtoon_slicing_numpy_and_pillow(self):
        """Tall vertical strips should be sliced into discrete pages cleanly."""
        # Create a tall strip (800x4000) with a white gap in the middle
        strip = Image.new("RGB", (800, 4000), (30, 40, 50))
        # Draw white gutter space between 1800 and 2200
        for y in range(1800, 2200):
            for x in range(800):
                strip.putpixel((x, y), (255, 255, 255))

        buf = BytesIO()
        strip.save(buf, format="JPEG")
        strip_bytes = buf.getvalue()

        # Test end-to-end strip slicer
        slices = slice_panel_image(strip_bytes)
        self.assertGreater(len(slices), 1)

        # Test both Pillow and NumPy gutter cut algorithms directly
        with Image.open(BytesIO(strip_bytes)).convert("L") as pil_gray:
            pillow_cuts = find_gutter_cut_points_pillow(pil_gray, target_height=1400)
            self.assertGreater(len(pillow_cuts), 0)

            numpy_cuts = find_gutter_cut_points_numpy(pil_gray, target_height=1400)
            self.assertGreater(len(numpy_cuts), 0)


if __name__ == "__main__":
    unittest.main()
