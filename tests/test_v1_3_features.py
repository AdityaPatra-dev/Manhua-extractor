import os
import sys
import unittest
import shutil
import tempfile
import asyncio
from io import BytesIO
from PIL import Image, ImageDraw

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.downloader import (
    get_staging_dir,
    cleanup_staging_dir,
    download_panels_stream
)
from core.slicer import (
    slice_panel_image,
    slice_chapter_panels,
    find_gutter_cut_points_pillow
)
import core.slicer as slicer_mod


class TestV13Features(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="manhua_test_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_staging_dir_generation(self):
        """Verify deterministic staging path generation."""
        s1 = get_staging_dir(self.test_dir, "solo-leveling", 1.0)
        s2 = get_staging_dir(self.test_dir, "solo-leveling", 1.0)
        s3 = get_staging_dir(self.test_dir, "solo-leveling", 2.0)

        self.assertEqual(s1, s2)
        self.assertNotEqual(s1, s3)
        self.assertTrue(".staging" in s1)
        self.assertTrue("solo_leveling_ch_1" in s1)

    def test_staging_cache_and_resume(self):
        """Verify panel caching in staging dir and resumption."""
        staging_dir = get_staging_dir(self.test_dir, "test_series", 1.0)
        os.makedirs(staging_dir, exist_ok=True)

        # Create 2 synthetic JPEG images in staging cache
        img = Image.new("RGB", (200, 300), color=(255, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        cached_bytes = buf.getvalue()

        panel0_path = os.path.join(staging_dir, "panel_0000.jpg")
        with open(panel0_path, "wb") as f:
            f.write(cached_bytes)

        # Now run download_panels_stream where panel 0 should be pulled from cache
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # URL is dummy; panel 0 exists in staging so it won't hit network!
            results = loop.run_until_complete(
                download_panels_stream(
                    image_urls=["http://dummy.invalid/page0.jpg"],
                    referer="http://dummy.invalid",
                    staging_dir=staging_dir
                )
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0], cached_bytes)
        finally:
            loop.close()

        # Test cleanup
        self.assertTrue(os.path.exists(staging_dir))
        cleanup_staging_dir(staging_dir)
        self.assertFalse(os.path.exists(staging_dir))

    def test_smart_slicer_standard_image(self):
        """Standard aspect ratio images (not tall strips) should not be sliced."""
        img = Image.new("RGB", (800, 1000), color=(200, 200, 200))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        slices = slice_panel_image(raw_bytes, target_aspect_ratio=1.4)
        self.assertEqual(len(slices), 1)
        self.assertEqual(slices[0], raw_bytes)

    def test_smart_slicer_tall_strip_with_gutters(self):
        """Tall webtoon strip with white gutters should be cleanly sliced at gutter lines."""
        # Create an 800 x 6000 strip with 3 comic panels separated by 100px white gutters
        strip = Image.new("RGB", (800, 6000), color=(255, 255, 255))
        draw = ImageDraw.Draw(strip)

        # Panel 1: y = [100 to 1800]
        draw.rectangle([50, 100, 750, 1800], fill=(50, 50, 150))
        # Gutter: y = [1801 to 2100] (white)
        # Panel 2: y = [2101 to 3800]
        draw.rectangle([50, 2101, 750, 3800], fill=(150, 50, 50))
        # Gutter: y = [3801 to 4100] (white)
        # Panel 3: y = [4101 to 5800]
        draw.rectangle([50, 4101, 750, 5800], fill=(50, 150, 50))

        buf = BytesIO()
        strip.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        # Slice with NumPy enabled
        slices = slice_panel_image(raw_bytes, target_aspect_ratio=1.4)
        self.assertGreater(len(slices), 2)
        print(f"NumPy slicer created {len(slices)} pages from tall strip.")

        # Test pure Pillow fallback
        old_numpy_state = slicer_mod.HAS_NUMPY
        try:
            slicer_mod.HAS_NUMPY = False
            slices_pillow = slice_panel_image(raw_bytes, target_aspect_ratio=1.4)
            self.assertGreater(len(slices_pillow), 2)
            print(f"Pure Pillow slicer created {len(slices_pillow)} pages from tall strip.")
        finally:
            slicer_mod.HAS_NUMPY = old_numpy_state

        # Test batch chapter slicer
        all_sliced = slice_chapter_panels([raw_bytes], target_aspect_ratio=1.4)
        self.assertEqual(len(all_sliced), len(slices))


if __name__ == "__main__":
    unittest.main()
