import json
import os
import tempfile
import unittest
from scripts.merge_venues import merge_venues


class TestMergeVenues(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def _write_venue(self, subdir: str, filename: str, data: dict):
        os.makedirs(os.path.join(self.tmp_dir, subdir), exist_ok=True)
        path = os.path.join(self.tmp_dir, subdir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        return path

    def test_merges_multiple_venues(self):
        self._write_venue("venues", "v1.json", {"id": "v1", "name": "Place A"})
        self._write_venue("venues", "v2.json", {"id": "v2", "name": "Place B"})
        output = os.path.join(self.tmp_dir, "merged.json")
        merge_venues(os.path.join(self.tmp_dir, "venues"), output)
        with open(output, 'r') as f:
            data = json.load(f)
        self.assertIn("v1", data)
        self.assertIn("v2", data)
        self.assertEqual(data["v1"]["name"], "Place A")

    def test_skips_non_json_files(self):
        self._write_venue("venues", "v1.json", {"id": "v1", "name": "Place A"})
        with open(os.path.join(self.tmp_dir, "venues", "notes.txt"), 'w') as f:
            f.write("not json")
        output = os.path.join(self.tmp_dir, "merged.json")
        merge_venues(os.path.join(self.tmp_dir, "venues"), output)
        with open(output, 'r') as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_skips_corrupt_json(self):
        os.makedirs(os.path.join(self.tmp_dir, "venues"), exist_ok=True)
        with open(os.path.join(self.tmp_dir, "venues", "bad.json"), 'w', encoding='utf-8') as f:
            f.write("{not valid json}")
        self._write_venue("venues", "v1.json", {"id": "v1", "name": "Place A"})
        output = os.path.join(self.tmp_dir, "merged.json")
        merge_venues(os.path.join(self.tmp_dir, "venues"), output)
        with open(output, 'r') as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)

    def test_empty_dir_creates_no_output(self):
        os.makedirs(os.path.join(self.tmp_dir, "empty"), exist_ok=True)
        output = os.path.join(self.tmp_dir, "merged.json")
        merge_venues(os.path.join(self.tmp_dir, "empty"), output)
        self.assertFalse(os.path.exists(output))

    def test_missing_dir_does_not_crash(self):
        output = os.path.join(self.tmp_dir, "merged.json")
        merge_venues(os.path.join(self.tmp_dir, "nonexistent"), output)
        self.assertFalse(os.path.exists(output))


if __name__ == "__main__":
    unittest.main()
