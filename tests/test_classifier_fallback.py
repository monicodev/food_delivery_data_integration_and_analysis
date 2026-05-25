import unittest
import sqlite3
import os
import tempfile
from src.engine.classifier_orchestrator import ClassifierOrchestrator


class TestClassifierFallback(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        self.cursor.execute("CREATE TABLE food_taxonomy (category_uidentifier VARCHAR, name VARCHAR, parent VARCHAR, family VARCHAR)")
        self.cursor.execute("CREATE TABLE menu_items (id INTEGER, name VARCHAR, description TEXT)")
        self.cursor.execute("CREATE TABLE classifications (id INTEGER PRIMARY KEY AUTOINCREMENT, menu_item_id INTEGER, taxonomy_id VARCHAR, confidence FLOAT)")

        self.cursor.executemany(
            "INSERT INTO food_taxonomy VALUES (?, ?, ?, ?)",
            [
                ("pizza-001", "Pizza", "Main Course", "Italian"),
                ("burger-001", "Burgers", "Main Course", "American"),
                ("drink-001", "Soft Drinks", "Beverages", "Cold"),
            ]
        )
        self.cursor.executemany(
            "INSERT INTO menu_items (id, name, description) VALUES (?, ?, ?)",
            [
                (1, "Pepperoni Pizza", "Delicious pepperoni pizza"),
                (2, "Coca Cola", "Refreshing drink"),
            ]
        )
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        os.remove(self.db_path)

    def test_keyword_fallback_matches_pizza(self):
        orch = ClassifierOrchestrator(self.db_path)
        taxonomy = orch._load_taxonomy()
        cat_id, confidence = orch._keyword_fallback_classify("Pepperoni Pizza with cheese", taxonomy)
        self.assertEqual(cat_id, "pizza-001")
        self.assertGreater(confidence, 0.0)

    def test_keyword_fallback_matches_drink(self):
        orch = ClassifierOrchestrator(self.db_path)
        taxonomy = orch._load_taxonomy()
        cat_id, confidence = orch._keyword_fallback_classify("Coca Cola drink", taxonomy)
        self.assertEqual(cat_id, "drink-001")
        self.assertGreater(confidence, 0.0)

    def test_keyword_fallback_returns_unknown_for_no_match(self):
        orch = ClassifierOrchestrator(self.db_path)
        taxonomy = orch._load_taxonomy()
        cat_id, confidence = orch._keyword_fallback_classify("xyz123 nothing matches", taxonomy)
        self.assertEqual(cat_id, "unknown")


if __name__ == "__main__":
    unittest.main()
