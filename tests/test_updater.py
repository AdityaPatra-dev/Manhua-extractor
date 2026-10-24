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
        self.assertFalse(is_version_newer("1.0.9", "1.0.9"))
        self.assertFalse(is_version_newer("v1.0.9", "1.0.9"))
        
        # Newer patch
        self.assertTrue(is_version_newer("1.0.10", "1.0.9"))
        self.assertTrue(is_version_newer("v1.0.10", "1.0.9"))
        
        # Newer minor / major
        self.assertTrue(is_version_newer("1.1.0", "1.0.9"))
        self.assertTrue(is_version_newer("2.0.0", "1.0.9"))
        
        # Older versions
        self.assertFalse(is_version_newer("1.0.8", "1.0.9"))
        self.assertFalse(is_version_newer("0.9.9", "1.0.9"))

    @patch("urllib.request.urlopen")
    def test_get_latest_release_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_payload = {
            "tag_name": "v1.3.0",
            "name": "Release v1.3.0",
            "body": "Awesome new features",
            "published_at": "2026-10-25T00:00:00Z",
            "html_url": "https://github.com/AdityaPatra-dev/Manhua-extractor/releases/tag/v1.3.0",
            "assets": [
                {
                    "name": "app-release.apk",
                    "browser_download_url": "https://github.com/downloads/app-release.apk",
                    "size": 35000000,
                },
                {
                    "name": "app-debug.apk",
                    "browser_download_url": "https://github.com/downloads/app-debug.apk",
                    "size": 37000000,
                },
            ],
        }
        mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        info = get_latest_release(force=True)
        self.assertEqual(info["status"], "success")
        self.assertEqual(info["latest_version"], "1.3.0")
        self.assertTrue(info["has_update"])
        self.assertEqual(info["apk_url"], "https://github.com/downloads/app-release.apk")
        self.assertEqual(info["apk_name"], "app-release.apk")
        self.assertEqual(info["apk_size"], 35000000)

    def test_simulate_mode(self):
        info = get_latest_release(simulate=True)
        self.assertEqual(info["status"], "success")
        self.assertEqual(info["latest_version"], "1.3.0")
        self.assertTrue(info["has_update"])
        self.assertTrue(info["simulated"])


if __name__ == "__main__":
    unittest.main()
