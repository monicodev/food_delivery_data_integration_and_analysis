import unittest
import json
import os
import tempfile
import sqlite3
from src.engine.matcher import Matcher


class TestMatcherJEVenueLoading(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self.je_json_path = os.path.join(self.tmp_dir, "je_venues.json")
        self.google_json_path = os.path.join(self.tmp_dir, "google_venues.json")

        self.je_data = {
            "631": {
                "name": "Edo",
                "address": {
                    "city": "Barcelona",
                    "firstLine": "Calle General Mitre 136",
                    "postalCode": "08006",
                    "location": {
                        "type": "Point",
                        "coordinates": [2.13865, 41.403098]
                    }
                }
            },
            "848": {
                "name": "Boston",
                "address": {
                    "city": "Barcelona",
                    "firstLine": "Calle Alfonso XII",
                    "postalCode": "08006",
                    "location": {
                        "type": "Point",
                        "coordinates": [2.1500, 41.4000]
                    }
                }
            }
        }
        with open(self.je_json_path, 'w') as f:
            json.dump(self.je_data, f)

        self.google_data = [
            {"googlePlaceId": "g-001", "name": "Edo Restaurant", "rawAddress": "Carrer de Paris, Barcelona",
             "latitude": 41.403, "longitude": 2.139},
            {"googlePlaceId": "g-002", "name": "Boston Tapas", "rawAddress": "Carrer Mallorca, Barcelona",
             "latitude": 41.401, "longitude": 2.151},
        ]
        with open(self.google_json_path, 'w') as f:
            json.dump(self.google_data, f)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def _init_test_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS venues_je (id TEXT PRIMARY KEY, name TEXT, address TEXT, latitude REAL, longitude REAL, url TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS menu_items (id INTEGER PRIMARY KEY AUTOINCREMENT, je_venue_id TEXT, name TEXT, description TEXT, price REAL)")
        conn.commit()
        conn.close()

    def test_load_je_venues_parses_nested_coordinates(self):
        self._init_test_db()
        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path=self.google_json_path,
            je_venues_path=self.je_json_path
        )
        venues = matcher.load_je_venues()
        self.assertEqual(len(venues), 2)

        edo = [v for v in venues if v["id"] == "631"][0]
        self.assertEqual(edo["name"], "Edo")
        self.assertEqual(edo["latitude"], 41.403098)
        self.assertEqual(edo["longitude"], 2.13865)

    def test_load_google_venues(self):
        self._init_test_db()
        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path=self.google_json_path,
            je_venues_path=self.je_json_path
        )
        venues = matcher.load_google_venues()
        self.assertEqual(len(venues), 2)
        self.assertEqual(venues[0]["id"], "g-001")

    def test_run_matching_populates_venues_google_and_matches(self):
        self._init_test_db()
        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path=self.google_json_path,
            je_venues_path=self.je_json_path,
            weight_name=0.6,
            weight_geo=0.4
        )
        matcher.run_matching(threshold=0.0)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM venues_google")
        google_count = cursor.fetchone()[0]
        self.assertEqual(google_count, 2, "venues_google should be populated")

        cursor.execute("SELECT COUNT(*) FROM matches")
        match_count = cursor.fetchone()[0]
        self.assertGreater(match_count, 0, "matches should be populated")

        conn.close()

    def test_run_matching_empty_venues_returns_gracefully(self):
        empty_je = os.path.join(self.tmp_dir, "empty_je.json")
        with open(empty_je, 'w') as f:
            json.dump({}, f)

        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path=self.google_json_path,
            je_venues_path=empty_je
        )
        matcher.run_matching()

    def test_run_matching_deduplicates_best_match(self):
        self._init_test_db()
        same_spot = {"googlePlaceId": "g-003", "name": "Edo Barcelona", "rawAddress": "",
                      "latitude": 41.403, "longitude": 2.139}
        self.google_data.append(same_spot)
        with open(self.google_json_path, 'w') as f:
            json.dump(self.google_data, f)

        matcher = Matcher(
            db_path=self.db_path,
            google_venues_path=self.google_json_path,
            je_venues_path=self.je_json_path
        )
        matcher.run_matching(threshold=0.0)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT je_venue_id, COUNT(*) as cnt FROM matches GROUP BY je_venue_id")
        for row in cursor.fetchall():
            self.assertEqual(row[1], 1, f"JE venue {row[0]} has {row[1]} matches, expected 1")
        conn.close()


if __name__ == "__main__":
    unittest.main()
