import os
import tempfile
import unittest
from fastapi.testclient import TestClient

from app import app
from database.db import (
    init_db,
    get_or_create_series,
    create_folder,
    rename_folder,
    delete_folder,
    add_series_to_folder,
    remove_series_from_folder,
    get_all_folders_with_items,
    get_folder_by_id,
    get_all_series,
    update_library_order,
    update_folder_items_order
)


class TestLibraryFolders(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        init_db(self.db_path)

        # Create two sample series
        self.s1 = get_or_create_series(
            slug="manga-one",
            title="Manga One",
            engine="madara",
            db_path=self.db_path
        )
        self.s2 = get_or_create_series(
            slug="manga-two",
            title="Manga Two",
            engine="hitomi",
            db_path=self.db_path
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_create_and_get_folder(self):
        folder_id = create_folder(
            name="Favorites",
            color="#ef4444",
            series_ids=[self.s1, self.s2],
            db_path=self.db_path
        )
        self.assertGreater(folder_id, 0)

        folder = get_folder_by_id(folder_id, db_path=self.db_path)
        self.assertIsNotNone(folder)
        self.assertEqual(folder["name"], "Favorites")
        self.assertEqual(folder["item_count"], 2)
        self.assertEqual({s["id"] for s in folder["series"]}, {self.s1, self.s2})

        all_folders = get_all_folders_with_items(db_path=self.db_path)
        self.assertEqual(len(all_folders), 1)
        self.assertEqual(all_folders[0]["id"], folder_id)
        self.assertEqual(len(all_folders[0]["preview_covers"]), 2)

    def test_rename_folder(self):
        folder_id = create_folder(name="Old Name", db_path=self.db_path)
        ok = rename_folder(folder_id, "New Name", db_path=self.db_path)
        self.assertTrue(ok)
        folder = get_folder_by_id(folder_id, db_path=self.db_path)
        self.assertEqual(folder["name"], "New Name")

    def test_add_and_remove_series_from_folder(self):
        folder_id = create_folder(name="Action", db_path=self.db_path)
        self.assertTrue(add_series_to_folder(folder_id, self.s1, db_path=self.db_path))

        folder = get_folder_by_id(folder_id, db_path=self.db_path)
        self.assertEqual(folder["item_count"], 1)

        # Remove item -> since it's the last item, folder auto-dissolves
        self.assertTrue(remove_series_from_folder(folder_id, self.s1, auto_delete_empty=True, db_path=self.db_path))
        self.assertIsNone(get_folder_by_id(folder_id, db_path=self.db_path))

    def test_delete_folder_preserves_series(self):
        folder_id = create_folder(name="To Read", series_ids=[self.s1], db_path=self.db_path)
        self.assertTrue(delete_folder(folder_id, db_path=self.db_path))

        # Folder gone
        self.assertIsNone(get_folder_by_id(folder_id, db_path=self.db_path))

        # Series still exists in database!
        from database.db import get_series_by_id
        self.assertIsNotNone(get_series_by_id(self.s1, db_path=self.db_path))

    def test_api_endpoints(self):
        client = TestClient(app)
        res = client.get("/api/library")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("folders", data)

        # Create folder via API
        res = client.post("/api/library/folders", json={"name": "API Folder", "series_ids": []})
        self.assertEqual(res.status_code, 200)
        f_data = res.json()
        self.assertTrue(f_data["success"])
        f_id = f_data["folder"]["id"]

        # Rename via API
        res = client.patch(f"/api/library/folders/{f_id}", json={"name": "Renamed API Folder"})
        self.assertEqual(res.status_code, 200)

        # Delete via API
        res = client.delete(f"/api/library/folders/{f_id}")
        self.assertEqual(res.status_code, 200)

        # Test library reorder endpoint
        res = client.post("/api/library/reorder", json={"items": [{"type": "series", "id": 1}]})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

        # Test folder items reorder endpoint
        res = client.post("/api/library/folders/999/reorder", json={"series_ids": [1, 2]})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

    def test_update_library_and_folder_order_db(self):
        folder_id = create_folder(
            name="Ordering Test",
            color="#3b82f6",
            series_ids=[self.s1, self.s2],
            db_path=self.db_path
        )
        self.assertGreater(folder_id, 0)

        # Test updating library unified order
        items = [
            {"type": "series", "id": self.s2},
            {"type": "folder", "id": folder_id},
            {"type": "series", "id": self.s1}
        ]
        ok = update_library_order(items, db_path=self.db_path)
        self.assertTrue(ok)

        # Verify series are sorted by sort_order
        all_s = get_all_series(db_path=self.db_path)
        s_map = {s["id"]: s["sort_order"] for s in all_s}
        self.assertEqual(s_map[self.s2], 0)
        self.assertEqual(s_map[self.s1], 2)

        # Verify folder sort_order
        f = get_folder_by_id(folder_id, db_path=self.db_path)
        self.assertEqual(f["sort_order"], 1)

        # Test reordering items inside folder
        ok_folder = update_folder_items_order(folder_id, [self.s2, self.s1], db_path=self.db_path)
        self.assertTrue(ok_folder)
        f_updated = get_folder_by_id(folder_id, db_path=self.db_path)
        self.assertEqual(f_updated["series"][0]["id"], self.s2)
        self.assertEqual(f_updated["series"][1]["id"], self.s1)


if __name__ == "__main__":
    unittest.main()
