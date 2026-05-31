import unittest
import tempfile
import os
import sqlite3

from src.engine.classifier_orchestrator import ClassifierOrchestrator


class TestClassifierReclassification(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        self.cursor.execute(
            "CREATE TABLE food_taxonomy (category_uidentifier VARCHAR, name VARCHAR, parent VARCHAR, family VARCHAR)")
        self.cursor.execute(
            "CREATE TABLE menu_items (id INTEGER PRIMARY KEY AUTOINCREMENT, je_venue_id VARCHAR, name VARCHAR, description TEXT, price FLOAT)")
        self.cursor.execute(
            "CREATE TABLE classifications (id INTEGER PRIMARY KEY AUTOINCREMENT, menu_item_id INTEGER, taxonomy_id VARCHAR, confidence FLOAT)")

        self.cursor.executemany("INSERT INTO food_taxonomy VALUES (?, ?, ?, ?)", [
            ('pizza-001', 'Pizza', 'Main Course', 'Italian'),
            ('burger-001', 'Burgers', 'Main Course', 'American'),
        ])
        self.cursor.executemany("INSERT INTO menu_items (id, je_venue_id, name, description) VALUES (?, ?, ?, ?)", [
            (1, 'je_1', 'Pepperoni Pizza', 'Spicy pepperoni with cheese'),
            (2, 'je_1', 'Cheeseburger', 'Classic beef burger'),
        ])
        self.cursor.execute(
            "INSERT INTO classifications (menu_item_id, taxonomy_id, confidence) VALUES (?, ?, ?)",
            (1, 'pizza-001', 0.95))
        self.conn.commit()
        self.conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def _make_orchestrator(self):
        return ClassifierOrchestrator(self.db_path)

    def test_load_unclassified_only_when_not_forced(self):
        orch = self._make_orchestrator()
        items = orch._load_unclassified_items(force_reclassify=False)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], 2)

    def test_load_all_items_when_forced(self):
        orch = self._make_orchestrator()
        items = orch._load_unclassified_items(force_reclassify=True)
        self.assertEqual(len(items), 2)

    def test_force_reclassify_clears_existing(self):
        orch = self._make_orchestrator()
        orch.run_classification(export_json=False, force_reclassify=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM classifications")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertGreater(count, 0)

    def test_evaluate_returns_metrics_structure(self):
        orch = self._make_orchestrator()
        result = orch.evaluate({99: "nonexistent"})
        self.assertIsInstance(result, dict)
        self.assertIn("total_items", result)
        self.assertIn("classified_items", result)

    def test_evaluate_empty_ground_truth(self):
        orch = self._make_orchestrator()
        result = orch.evaluate({})
        self.assertIn("error", result)

    def test_evaluate_with_classifications(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO classifications (menu_item_id, taxonomy_id, confidence) VALUES (?, ?, ?)",
            (1, 'pizza-001', 0.95))
        cursor.execute(
            "INSERT INTO classifications (menu_item_id, taxonomy_id, confidence) VALUES (?, ?, ?)",
            (2, 'burger-001', 0.85))
        conn.commit()
        conn.close()

        orch = self._make_orchestrator()
        result = orch.evaluate({1: "Pizza", 2: "Burgers"})
        self.assertNotIn("error", result)
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["classified_items"], 2)


if __name__ == "__main__":
    unittest.main()
