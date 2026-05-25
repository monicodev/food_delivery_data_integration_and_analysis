import unittest
import sqlite3
import os
import tempfile

try:
    from src.engine.classifier import TextClassifier
    from src.engine.classifier_orchestrator import ClassifierOrchestrator
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


@unittest.skipIf(not HAS_SENTENCE_TRANSFORMERS, "sentence-transformers not installed")
class TestClassificationPipeline(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        self.cursor.execute("CREATE TABLE food_taxonomy (category_uidentifier VARCHAR, name VARCHAR, parent VARCHAR, family VARCHAR)")
        self.cursor.execute("CREATE TABLE menu_items (id INTEGER, name VARCHAR, description TEXT)")
        self.cursor.execute("CREATE TABLE classifications (id INTEGER PRIMARY KEY AUTOINCREMENT, menu_item_id INTEGER, taxonomy_id VARCHAR, confidence FLOAT)")

        taxonomy_data = [
            ('pizza-001', 'Pizza', 'Main Course', 'Italian'),
            ('burger-001', 'Burgers', 'Main Course', 'American'),
            ('drink-001', 'Soft Drinks', 'Beverages', 'Cold')
        ]
        self.cursor.executemany("INSERT INTO food_taxonomy VALUES (?, ?, ?, ?)", taxonomy_data)

        menu_items = [
            (1, 'Pepperoni Pizza', 'Delicious spicy pepperoni with melted cheese'),
            (2, 'Cheeseburger', 'Classic beef burger with cheddar'),
            (3, 'Coca Cola', 'Refreshing carbonated drink')
        ]
        self.cursor.executemany("INSERT INTO menu_items (id, name, description) VALUES (?, ?, ?)", menu_items)

        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        os.remove(self.db_path)

    def test_classifier_logic(self):
        classifier = TextClassifier()
        taxonomy_ids = ['pizza-001', 'burger-001', 'drink-001']
        taxonomy_texts = ['Pizza Main Course Italian', 'Burgers Main Course American', 'Soft Drinks Beverages Cold']
        embeddings = classifier.encode(taxonomy_texts)

        cat_id, confidence = classifier.classify('Pepperoni Pizza with cheese', embeddings, taxonomy_ids)
        self.assertEqual(cat_id, 'pizza-001')
        self.assertGreater(confidence, 0.5)

    def test_orchestrator_integration(self):
        orchestrator = ClassifierOrchestrator(self.db_path)
        orchestrator.run_classification()

        self.cursor.execute("SELECT menu_item_id, taxonomy_id, confidence FROM classifications")
        results = self.cursor.fetchall()

        self.assertEqual(len(results), 3)

        found_pizza = False
        for row in results:
            if row[0] == 1 and row[1] == 'pizza-001':
                found_pizza = True
                break
        self.assertTrue(found_pizza)


if __name__ == '__main__':
    unittest.main()
