import unittest
import tempfile
import os
import json
import sqlite3
from src.engine.matcher import Matcher
from src.engine.er_engine import EREngine


class TestMatcherUnmatchedExport(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE venues_je "
                     "(id TEXT PRIMARY KEY, name TEXT, address TEXT, latitude REAL, longitude REAL, url TEXT)")
        conn.execute("CREATE TABLE menu_items "
                     "(id INTEGER PRIMARY KEY AUTOINCREMENT, je_venue_id TEXT, name TEXT, description TEXT, price REAL)")
        conn.execute("CREATE TABLE venues_google "
                     "(id TEXT PRIMARY KEY, name TEXT, address TEXT, latitude REAL, longitude REAL)")
        conn.execute("CREATE TABLE matches "
                     "(id INTEGER PRIMARY KEY AUTOINCREMENT, je_venue_id TEXT, google_venue_id TEXT, similarity_score REAL)")
        conn.commit()
        conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def _make_je_venues(self, count=3):
        venues = {}
        for i in range(count):
            vid = f"je_{i}"
            venues[vid] = {
                "name": f"Restaurant {i}",
                "address": {"firstLine": f"Street {i}", "city": "Barcelona",
                            "location": {"type": "Point", "coordinates": [2.17, 41.39]}}
            }
        return venues

    def _make_google_venues(self, count=3):
        return [
            {"id": f"g_{i}", "name": f"Restaurant {i}", "address": f"Street {i}, Barcelona",
             "latitude": 41.39, "longitude": 2.17}
            for i in range(count)
        ]

    def test_export_unmatched_json_creates_file(self):
        output_path = os.path.join(self.tmp_dir, "unmatched.json")
        matcher = Matcher(db_path=self.db_path)

        self.assertFalse(os.path.exists(output_path))
        matcher._export_unmatched_json(["je_0", "je_2"], output_path=output_path)
        self.assertTrue(os.path.exists(output_path))

        with open(output_path, 'r') as f:
            data = json.load(f)
        self.assertEqual(data["count"], 2)
        self.assertIn("je_0", data["unmatched_je_venue_ids"])

    def test_export_unmatched_json_empty_list(self):
        output_path = os.path.join(self.tmp_dir, "unmatched.json")
        matcher = Matcher(db_path=self.db_path)
        matcher._export_unmatched_json([], output_path=output_path)

        with open(output_path, 'r') as f:
            data = json.load(f)
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["unmatched_je_venue_ids"], [])

    def test_run_matching_exports_matches_and_unmatched(self):
        je_path = os.path.join(self.tmp_dir, "je.json")
        google_path = os.path.join(self.tmp_dir, "google.json")

        with open(je_path, 'w') as f:
            json.dump(self._make_je_venues(3), f)
        with open(google_path, 'w') as f:
            json.dump(self._make_google_venues(2), f)

        output_matches = os.path.join(self.tmp_dir, "matches.json")
        output_unmatched = os.path.join(self.tmp_dir, "unmatched.json")

        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path=google_path,
            je_venues_path=je_path
        )

        matches = [
            {"je_venue_id": "je_0", "google_venue_id": "g_0", "similarity_score": 0.95},
            {"je_venue_id": "je_1", "google_venue_id": "g_1", "similarity_score": 0.85}
        ]
        matcher._export_matches_json(matches, output_path=output_matches)
        matcher._export_unmatched_json(["je_2"], output_path=output_unmatched)

        self.assertTrue(os.path.exists(output_matches))
        self.assertTrue(os.path.exists(output_unmatched))

        with open(output_matches, 'r') as f:
            mdata = json.load(f)
        self.assertEqual(len(mdata), 2)

        with open(output_unmatched, 'r') as f:
            udata = json.load(f)
        self.assertEqual(udata["count"], 1)
        self.assertEqual(udata["unmatched_je_venue_ids"], ["je_2"])


if __name__ == "__main__":
    unittest.main()
