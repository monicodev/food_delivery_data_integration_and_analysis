import unittest
import tempfile
import os

HAS_HTTX = False
try:
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.api.main import app, get_db
    from src.database.init_db import Base, VenueJE, Match
    HAS_HTTX = True
except Exception:
    TestClient = None


@unittest.skipIf(not HAS_HTTX, "httpx not installed (required for TestClient)")
class TestAPIVenuesEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(bind=self.engine)
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        session = TestingSessionLocal()
        session.add_all([
            VenueJE(id="je_1", name="Restaurant A", latitude=41.39, longitude=2.17),
            VenueJE(id="je_2", name="Restaurant B", latitude=41.40, longitude=2.18),
            VenueJE(id="je_3", name="Restaurant C", latitude=None, longitude=None),
        ])
        session.add(Match(je_venue_id="je_1", google_venue_id="g_1", similarity_score=0.95))
        session.commit()
        session.close()

        def override_get_db():
            db = TestingSessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)
        app.dependency_overrides.clear()

    def test_venues_endpoint_returns_all_venues(self):
        response = self.client.get("/analytics/venues")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)

    def test_venues_endpoint_matched_flag(self):
        response = self.client.get("/analytics/venues")
        data = response.json()
        matched = [v for v in data if v["is_matched"]]
        unmatched = [v for v in data if not v["is_matched"]]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["id"], "je_1")
        self.assertEqual(len(unmatched), 2)

    def test_venues_endpoint_coordinates(self):
        response = self.client.get("/analytics/venues")
        data = response.json()
        venue_a = next(v for v in data if v["id"] == "je_1")
        self.assertEqual(venue_a["latitude"], 41.39)
        self.assertEqual(venue_a["longitude"], 2.17)

        venue_c = next(v for v in data if v["id"] == "je_3")
        self.assertIsNone(venue_c["latitude"])
        self.assertIsNone(venue_c["longitude"])

    def test_venues_endpoint_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("database", data)


if __name__ == "__main__":
    unittest.main()
