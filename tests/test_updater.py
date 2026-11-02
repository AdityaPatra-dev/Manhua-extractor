import unittest
from unittest.mock import patch, MagicMock
import io
import json
from core.app_updater import (
    parse_version,
    is_version_newer,
    get_latest_release,
    CURRENT_APP_VERSION,
)


class TestUpdater(unittest.TestCase):

    def test_parse_version(self):
        self.assertEqual(parse_version("1.0.9"), (1, 0, 9))
        self.assertEqual(parse_version("v1.0.9"), (1, 0, 9))
        self.assertEqual(parse_version("v1.0.10"), (1, 0, 10))
        self.assertEqual(parse_version("2.0.0-beta.1"), (2, 0, 0, 1))
        self.assertEqual(parse_version(""), (0,))
        self.assertEqual(parse_version(None), (0,))

    def test_is_version_newer(self):
        # Equal versions
        self.assertFalse(is_version_newer("1.3.0", "1.3.0"))
        self.assertFalse(is_version_newer("v1.3.0", "1.3.0"))
        
        # Newer patch
        self.assertTrue(is_version_newer("1.3.1", "1.3.0"))
        self.assertTrue(is_version_newer("v1.3.1", "1.3.0"))
        
        # Newer minor / major
        self.assertTrue(is_version_newer("1.4.0", "1.3.0"))
        self.assertTrue(is_version_newer("2.0.0", "1.3.0"))
        
        # Older versions
        self.assertFalse(is_version_newer("1.2.6", "1.3.0"))
        self.assertFalse(is_version_newer("0.9.9", "1.3.0"))

    @patch("urllib.request.urlopen")
    def test_get_latest_release_abi_split_arm64(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_payload = {
            "tag_name": "v1.3.1",
            "name": "Release v1.3.1",
            "body": "Awesome new features",
            "published_at": "2026-11-02T00:00:00Z",
            "html_url": "https://github.com/AdityaPatra-dev/Manhua-extractor/releases/tag/v1.3.1",
            "assets": [
                {
                    "name": "app-arm64-v8a-release.apk",
                    "browser_download_url": "https://github.com/downloads/app-arm64-v8a-release.apk",
                    "size": 25000000,
                },
                {
                    "name": "app-armeabi-v7a-release.apk",
                    "browser_download_url": "https://github.com/downloads/app-armeabi-v7a-release.apk",
                    "size": 24000000,
                },
                {
                    "name": "app-universal-release.apk",
                    "browser_download_url": "https://github.com/downloads/app-universal-release.apk",
                    "size": 34000000,
                },
                {
                    "name": "app-release.apk",
                    "browser_download_url": "https://github.com/downloads/app-release.apk",
                    "size": 34000000,
                },
            ],
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Request with arm64-v8a device ABI
        info = get_latest_release(force=True, abi="arm64-v8a")
        self.assertEqual(info["status"], "success")
        self.assertEqual(info["latest_version"], "1.3.1")
        self.assertTrue(info["has_update"])
        self.assertEqual(info["apk_name"], "app-arm64-v8a-release.apk")
        self.assertEqual(info["apk_url"], "https://github.com/downloads/app-arm64-v8a-release.apk")
        self.assertEqual(info["apk_size"], 25000000)
        self.assertEqual(info["apk_abi"], "arm64-v8a")
        self.assertTrue(info["is_abi_specific"])
        self.assertGreater(info["data_savings_percent"], 0)

        # Request with armeabi-v7a device ABI
        info_v7 = get_latest_release(force=True, abi="armeabi-v7a")
        self.assertEqual(info_v7["apk_name"], "app-armeabi-v7a-release.apk")
        self.assertEqual(info_v7["apk_abi"], "armeabi-v7a")

        # Request with unknown or no ABI falls back to universal
        info_univ = get_latest_release(force=True, abi=None)
        self.assertIn(info_univ["apk_abi"], ("universal", "unknown"))

    def test_simulate_mode(self):
        info = get_latest_release(simulate=True, abi="arm64-v8a")
        self.assertEqual(info["status"], "success")
        self.assertEqual(info["latest_version"], "1.3.1")
        self.assertTrue(info["has_update"])
        self.assertTrue(info["simulated"])
        self.assertEqual(info["apk_abi"], "arm64-v8a")
        self.assertTrue(info["is_abi_specific"])
        self.assertGreater(info["data_savings_percent"], 20)


if __name__ == "__main__":
    unittest.main()
