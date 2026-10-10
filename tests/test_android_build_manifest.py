import os
import unittest
import xml.etree.ElementTree as ET

class TestAndroidBuildManifest(unittest.TestCase):
    def setUp(self):
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.android_dir = os.path.join(self.repo_root, "android")

    def test_android_manifest_validity(self):
        manifest_path = os.path.join(self.android_dir, "app", "src", "main", "AndroidManifest.xml")
        self.assertTrue(os.path.exists(manifest_path), "AndroidManifest.xml must exist")
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        self.assertEqual(root.tag, "manifest")

        # Verify permissions
        permissions = [p.attrib.get("{http://schemas.android.com/apk/res/android}name") for p in root.findall("uses-permission")]
        self.assertIn("android.permission.INTERNET", permissions)
        self.assertIn("android.permission.WAKE_LOCK", permissions)
        self.assertIn("android.permission.FOREGROUND_SERVICE", permissions)

        # Verify components
        app_elem = root.find("application")
        self.assertIsNotNone(app_elem)
        activity_names = [a.attrib.get("{http://schemas.android.com/apk/res/android}name") for a in app_elem.findall("activity")]
        self.assertIn(".MainActivity", activity_names)

        service_names = [s.attrib.get("{http://schemas.android.com/apk/res/android}name") for s in app_elem.findall("service")]
        self.assertIn(".DownloadForegroundService", service_names)

        provider_names = [p.attrib.get("{http://schemas.android.com/apk/res/android}name") for p in app_elem.findall("provider")]
        self.assertIn("androidx.core.content.FileProvider", provider_names)

    def test_chaquopy_gradle_configuration(self):
        gradle_path = os.path.join(self.android_dir, "app", "build.gradle.kts")
        self.assertTrue(os.path.exists(gradle_path))
        with open(gradle_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("com.chaquo.python", content)
        self.assertIn("fastapi", content)
        self.assertIn("uvicorn", content)
        self.assertIn("pillow", content)
        self.assertIn("compileSdk = 34", content)

    def test_kotlin_source_files_exist(self):
        kt_dir = os.path.join(self.android_dir, "app", "src", "main", "java", "com", "manhua", "extractor")
        main_activity = os.path.join(kt_dir, "MainActivity.kt")
        service = os.path.join(kt_dir, "DownloadForegroundService.kt")
        file_utils = os.path.join(kt_dir, "FileUtils.kt")
        self.assertTrue(os.path.exists(main_activity), "MainActivity.kt must exist")
        self.assertTrue(os.path.exists(service), "DownloadForegroundService.kt must exist")
        self.assertTrue(os.path.exists(file_utils), "FileUtils.kt must exist")

    def test_github_actions_workflow_exists(self):
        wf_path = os.path.join(self.repo_root, ".github", "workflows", "build-android-apk.yml")
        self.assertTrue(os.path.exists(wf_path), "CI workflow must exist")
        with open(wf_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("assembleDebug", content)
        self.assertIn("upload-artifact", content)

if __name__ == "__main__":
    unittest.main()

