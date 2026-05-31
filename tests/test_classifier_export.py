import unittest
import os
import json
import sqlite3
import tempfile
from unittest.mock import patch, MagicMock


class TestClassifierExport(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        self.cursor.execute("""
            CREATE TABLE food_taxonomy (
                category_uidentifier VARCHAR PRIMARY KEY,
                name VARCHAR, parent VARCHAR, family VARCHAR
            )
        """)
        self.cursor.execute("""
            CREATE TABLE menu_items (
                id INTEGER PRIMARY KEY,
                je_venue_id TEXT, name TEXT, description TEXT, price REAL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_item_id INTEGER, taxonomy_id VARCHAR, confidence FLOAT
            )
        """)

        self.cursor.executemany(
            "INSERT INTO food_taxonomy VALUES (?, ?, ?, ?)",
            [
                ("pizza-001", "Pizza", "Main Course", "Italian"),
                ("burger-001", "Burgers", "Main Course", "American"),
            ]
        )
        self.cursor.executemany(
            "INSERT INTO menu_items (id, je_venue_id, name, description) VALUES (?, ?, ?, ?)",
            [
                (1, "v1", "Pepperoni Pizza", "Spicy pepperoni"),
                (2, "v1", "Cheeseburger", "Beef with cheddar"),
            ]
        )
        self.cursor.executemany(
            "INSERT INTO classifications (menu_item_id, taxonomy_id, confidence) VALUES (?, ?, ?)",
            [
                (1, "pizza-001", 0.92),
                (2, "burger-001", 0.85),
            ]
        )
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        os.close(self.db_fd)
        os.remove(self.db_path)

    def test_export_classifications_json(self):
        from src.engine.classifier_orchestrator import ClassifierOrchestrator

        with patch.object(ClassifierOrchestrator, '_load_taxonomy', return_value=[]):
            with patch.object(ClassifierOrchestrator, '_load_unclassified_items', return_value=[]):
                orch = ClassifierOrchestrator(self.db_path)

                output_path = os.path.join(tempfile.mkdtemp(), "classifications.json")
                orch._export_classifications_json(output_path)

                self.assertTrue(os.path.exists(output_path))
                with open(output_path, 'r') as f:
                    data = json.load(f)

                self.assertEqual(len(data), 2)
                self.assertEqual(data[0]["item_name"], "Pepperoni Pizza")
                self.assertEqual(data[0]["category_name"], "Pizza")
                self.assertEqual(data[0]["category_parent"], "Main Course")
                self.assertEqual(data[0]["category_family"], "Italian")
                self.assertIn("confidence", data[0])

    def test_taxonomy_load(self):
        from src.engine.classifier_orchestrator import ClassifierOrchestrator

        with patch.object(ClassifierOrchestrator, '_load_unclassified_items', return_value=[]):
            orch = ClassifierOrchestrator(self.db_path)
            taxonomy = orch._load_taxonomy()

            self.assertEqual(len(taxonomy), 2)
            ids = [t["id"] for t in taxonomy]
            self.assertIn("pizza-001", ids)
            self.assertIn("burger-001", ids)
            self.assertEqual(taxonomy[0]["text"], "Pizza")

    def test_unclassified_items_query(self):
        from src.engine.classifier_orchestrator import ClassifierOrchestrator

        conn2 = sqlite3.connect(self.db_path)
        conn2.execute("DELETE FROM classifications")
        conn2.commit()
        conn2.close()

        with patch.object(ClassifierOrchestrator, '_load_taxonomy', return_value=[]):
            orch = ClassifierOrchestrator(self.db_path)
            items = orch._load_unclassified_items()
            self.assertEqual(len(items), 2)


if __name__ == "__main__":
    unittest.main()
