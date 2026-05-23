import unittest
from pathlib import Path
from app.services.assets_service import list_zone_files
from app.routes.assets import assets
from fastapi import HTTPException

class TestAssetsService(unittest.TestCase):
    def test_valid_zone_luna(self):
        # The 'luna' zone is expected to exist and have files
        data = list_zone_files("luna")
        self.assertIn("archivos", data)
        self.assertGreater(len(data["archivos"]), 0)
        for file_info in data["archivos"]:
            self.assertIn("nombre", file_info)
            self.assertIn("url", file_info)
            self.assertIn("tamano_bytes", file_info)
            self.assertIn("checksum", file_info)

    def test_nonexistent_zone(self):
        # A nonexistent zone should return an empty list under the 'archivos' key
        data = list_zone_files("nonexistent_zone_xyz")
        self.assertEqual(data, {"archivos": []})

    def test_file_as_zone(self):
        # A path pointing to a file (not a directory) should return empty list of files instead of throwing NotADirectoryError
        data = list_zone_files("audio/test.mp3")
        self.assertEqual(data, {"archivos": []})

    def test_path_traversal_parent(self):
        # Path traversal attempting to access parent directory should be blocked and return empty list
        data = list_zone_files("..")
        self.assertEqual(data, {"archivos": []})

    def test_path_traversal_sibling(self):
        # Path traversal trying to access a sibling directory outside ASSETS_DIR
        data = list_zone_files("../routes")
        self.assertEqual(data, {"archivos": []})

class TestAssetsRoute(unittest.TestCase):
    def test_route_valid_zone(self):
        # The endpoint should return data for a valid zone
        data = assets("luna")
        self.assertIn("archivos", data)
        self.assertGreater(len(data["archivos"]), 0)

    def test_route_invalid_zone_raises_404(self):
        # The endpoint should raise an HTTPException with status 404 for an invalid zone
        with self.assertRaises(HTTPException) as context:
            assets("nonexistent_zone_xyz")
        self.assertEqual(context.exception.status_code, 404)
        self.assertEqual(context.exception.detail, "Zona no encontrada o vacía")

    def test_route_file_as_zone_raises_404(self):
        # The endpoint should raise an HTTPException with status 404 if a file is requested as a zone
        with self.assertRaises(HTTPException) as context:
            assets("audio/test.mp3")
        self.assertEqual(context.exception.status_code, 404)

if __name__ == "__main__":
    unittest.main()
