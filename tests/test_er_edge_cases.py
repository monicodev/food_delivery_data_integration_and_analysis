import unittest
import tempfile
import os
import json
import sqlite3
from src.engine.er_engine import EREngine
from src.engine.matcher import Matcher


class TestEREngineEdgeCases(unittest.TestCase):
    def setUp(self):
        self.engine = EREngine(weight_name=0.6, weight_geo=0.4)

    def test_identical_strings_score_one(self):
        score = self.engine.calculate_name_similarity("Burger King", "Burger King")
        self.assertAlmostEqual(score, 1.0)

    def test_empty_strings_score_zero(self):
        score = self.engine.calculate_name_similarity("", "Burger King")
        self.assertEqual(score, 0.0)
        score = self.engine.calculate_name_similarity("Burger King", "")
        self.assertEqual(score, 0.0)

    def test_suffix_stripping_improves_match(self):
        # 'Ltd' and 'Inc' are in the suffix list; 'Restaurant' is kept as a descriptor
        score_with = self.engine.calculate_name_similarity("Pizza Hut Ltd", "Pizza Hut Inc")
        self.assertGreater(score_with, 0.8)
        # Suffix vs no-suffix should still be a strong partial match
        score_partial = self.engine.calculate_name_similarity("Pizza Hut Restaurant", "Pizza Hut")
        self.assertGreater(score_partial, 0.5)

    def test_unicode_normalization(self):
        # Accented chars decompose and combine: Café → Cafe
        score = self.engine.calculate_name_similarity("Café", "Cafe")
        self.assertAlmostEqual(score, 1.0)

    def test_non_ascii_preserved(self):
        # Non-Latin scripts are preserved (not stripped to empty)
        processed = self.engine._preprocess_name("麦当劳")
        self.assertIn("麦当劳", processed)
        self.assertEqual(processed, "麦当劳")

    def test_haversine_same_point(self):
        d = self.engine.calculate_haversine_distance(41.39, 2.17, 41.39, 2.17)
        self.assertAlmostEqual(d, 0.0)

    def test_haversine_known_distance(self):
        d = self.engine.calculate_haversine_distance(41.39, 2.17, 41.40, 2.18)
        self.assertGreater(d, 0)
        self.assertLess(d, 2000)

    def test_geo_similarity_close_points(self):
        score = self.engine.calculate_geo_similarity(41.39, 2.17, 41.40, 2.18)
        # ~1.2km apart with lambda=0.00035 => e^(-0.42) ≈ 0.66
        self.assertGreater(score, 0.5)
        self.assertLess(score, 0.8)

    def test_geo_similarity_far_points(self):
        score = self.engine.calculate_geo_similarity(41.39, 2.17, 48.85, 2.35)
        self.assertLess(score, 0.01)

    def test_geo_none_coordinates(self):
        score = self.engine.calculate_geo_similarity(None, 2.17, 41.39, 2.17)
        self.assertEqual(score, 0.0)
        score = self.engine.calculate_geo_similarity(41.39, None, 41.39, 2.17)
        self.assertEqual(score, 0.0)

    def test_preprocess_removes_punctuation(self):
        processed = self.engine._preprocess_name("McDonald's #123!")
        self.assertNotIn("!", processed)
        self.assertNotIn("#", processed)
        self.assertNotIn("'", processed)

    def test_weighted_total_within_bounds(self):
        score = self.engine.compute_total_score(
            "Burger King", 51.5074, -0.1278,
            "Burger King", 51.5075, -0.1279
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestMatcherMissingData(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE venues_je (id TEXT PRIMARY KEY, name TEXT, address TEXT, latitude REAL, longitude REAL, url TEXT)")
        conn.execute("CREATE TABLE menu_items (id INTEGER PRIMARY KEY AUTOINCREMENT, je_venue_id TEXT, name TEXT, description TEXT, price REAL)")
        conn.commit()
        conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def test_missing_google_venues_file_returns_empty(self):
        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path="/nonexistent/file.json",
            je_venues_path="/nonexistent/je.json"
        )
        result = matcher.load_google_venues()
        self.assertEqual(result, [])

    def test_missing_je_venues_file_returns_empty(self):
        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path="/nonexistent/file.json",
            je_venues_path="/nonexistent/je.json"
        )
        result = matcher.load_je_venues()
        self.assertEqual(result, [])

    def test_run_matching_with_missing_files_aborts(self):
        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path="/nonexistent/file.json",
            je_venues_path="/nonexistent/je.json"
        )
        matcher.run_matching()

    def test_google_venue_missing_name_skipped(self):
        data = [
            {"id": "g-001", "name": "Place A", "address": "Street 1", "latitude": 41.0, "longitude": 2.0},
            {"id": "g-002", "address": "Street 2", "latitude": 42.0, "longitude": 3.0}
        ]
        path = os.path.join(self.tmp_dir, "google_no_name.json")
        with open(path, 'w') as f:
            json.dump(data, f)
        matcher = Matcher(db_path=self.db_path, google_venues_path=path, je_venues_path="/nonexistent.json")
        venues = matcher.load_google_venues()
        self.assertEqual(len(venues), 1)
        self.assertEqual(venues[0]["id"], "g-001")

    def test_google_venue_missing_id_generates_uuid(self):
        data = [
            {"name": "NoID Place", "address": "Street 1", "latitude": 41.0, "longitude": 2.0}
        ]
        path = os.path.join(self.tmp_dir, "google_no_id.json")
        with open(path, 'w') as f:
            json.dump(data, f)
        matcher = Matcher(db_path=self.db_path, google_venues_path=path, je_venues_path="/nonexistent.json")
        venues = matcher.load_google_venues()
        self.assertEqual(len(venues), 1)
        self.assertNotEqual(venues[0]["id"], "unknown")
        self.assertNotEqual(venues[0]["id"], "")

    def test_google_venue_both_id_formats(self):
        data = [
            {"id": "g-001", "name": "Place A", "address": "Street 1", "latitude": 41.0, "longitude": 2.0},
            {"googlePlaceId": "g-002", "name": "Place B", "rawAddress": "Street 2", "latitude": 42.0, "longitude": 3.0}
        ]
        path = os.path.join(self.tmp_dir, "google_both.json")
        with open(path, 'w') as f:
            json.dump(data, f)

        matcher = Matcher(db_path=self.db_path, google_venues_path=path, je_venues_path="/nonexistent.json")
        venues = matcher.load_google_venues()
        self.assertEqual(len(venues), 2)
        self.assertEqual(venues[0]["id"], "g-001")
        self.assertEqual(venues[1]["id"], "g-002")
        self.assertEqual(venues[0]["address"], "Street 1")
        self.assertEqual(venues[1]["address"], "Street 2")


if __name__ == "__main__":
    unittest.main()
