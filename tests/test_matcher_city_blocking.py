import unittest
import json
import os
import tempfile
import sqlite3
from src.engine.matcher import Matcher


class TestMatcherCityBlocking(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def _init_db(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE venues_je (id TEXT PRIMARY KEY, name TEXT, address TEXT, latitude REAL, longitude REAL, url TEXT)")
        conn.execute("CREATE TABLE venues_google (id TEXT PRIMARY KEY, name TEXT, address TEXT, latitude REAL, longitude REAL)")
        conn.execute("CREATE TABLE menu_items (id INTEGER PRIMARY KEY AUTOINCREMENT, je_venue_id TEXT, name TEXT, description TEXT, price REAL)")
        conn.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY AUTOINCREMENT, je_venue_id TEXT, google_venue_id TEXT, similarity_score REAL)")
        conn.commit()
        conn.close()

    def test_detect_city_barcelona(self):
        result = Matcher._detect_city("Carrer de Paris, 08004 Barcelona, Spain")
        assert result == "Barcelona"

    def test_detect_city_madrid(self):
        result = Matcher._detect_city("Calle Mayor, 28013 Madrid, Spain")
        assert result == "Madrid"

    def test_detect_city_unknown(self):
        result = Matcher._detect_city("123 Main St, New York, USA")
        assert result == "unknown"

    def test_detect_city_empty(self):
        result = Matcher._detect_city("")
        assert result == "unknown"

    def test_detect_city_none(self):
        result = Matcher._detect_city(None)
        assert result == "unknown"

    def test_detect_city_case_insensitive(self):
        result = Matcher._detect_city("calle examples, barcelona, spain")
        assert result == "Barcelona"

    def test_group_by_city_partitions_venues(self):
        db_path = os.path.join(self.tmp_dir, "test.db")
        self._init_db(db_path)

        je_data = {"je1": {"name": "Place A", "address": {"city": "Barcelona", "firstLine": "Street 1",
                   "location": {"coordinates": [2.0, 41.0]}}}}
        je_path = os.path.join(self.tmp_dir, "je.json")
        with open(je_path, 'w') as f:
            json.dump(je_data, f)

        google_data = [
            {"googlePlaceId": "g1", "name": "Place A Google", "rawAddress": "Barcelona, Spain",
             "latitude": 41.0, "longitude": 2.0},
            {"googlePlaceId": "g2", "name": "Place B Google", "rawAddress": "Madrid, Spain",
             "latitude": 40.0, "longitude": -3.0},
        ]
        google_path = os.path.join(self.tmp_dir, "google.json")
        with open(google_path, 'w') as f:
            json.dump(google_data, f)

        matcher = Matcher(db_path=db_path, google_venues_path=google_path, je_venues_path=je_path)

        google_venues = matcher.load_google_venues()
        groups = matcher._group_by_city(google_venues)

        assert "Barcelona" in groups
        assert "Madrid" in groups
        assert len(groups["Barcelona"]) == 1
        assert len(groups["Madrid"]) == 1

    def test_matcher_uses_city_blocking(self):
        db_path = os.path.join(self.tmp_dir, "test.db")
        self._init_db(db_path)

        je_data = {"je1": {"name": "Place Alpha", "address": {"city": "Barcelona", "firstLine": "Street 1",
                   "location": {"coordinates": [2.0, 41.0]}}}}
        je_path = os.path.join(self.tmp_dir, "je.json")
        with open(je_path, 'w') as f:
            json.dump(je_data, f)

        google_data = [
            {"googlePlaceId": "g1", "name": "Place Alpha", "rawAddress": "Barcelona, Spain",
             "latitude": 41.0, "longitude": 2.0},
        ]
        google_path = os.path.join(self.tmp_dir, "google.json")
        with open(google_path, 'w') as f:
            json.dump(google_data, f)

        matcher = Matcher(db_path=db_path, google_venues_path=google_path, je_venues_path=je_path,
                          weight_name=0.6, weight_geo=0.4)
        matcher.run_matching(threshold=0.0)

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        conn.close()
        assert count > 0, "City-blocked matching should still find matches"


if __name__ == "__main__":
    unittest.main()
