import unittest
import tempfile
import os
import sqlite3
from unittest.mock import patch

HAS_DEPS = False
try:
    import torch
    import numpy as np
    from src.engine.image_processor import ImageProcessor, FOOD_CATEGORIES
    HAS_DEPS = True
except ImportError:
    ImageProcessor = None
    FOOD_CATEGORIES = []


@unittest.skipIf(not HAS_DEPS, "cv2/transformers/torch not installed")
class TestImageProcessorEvaluation(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self.img_root = os.path.join(self.tmp_dir, "images")
        os.makedirs(self.img_root, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS food_taxonomy "
                     "(category_uidentifier VARCHAR PRIMARY KEY, name VARCHAR, parent VARCHAR, family VARCHAR)")
        conn.execute("INSERT OR IGNORE INTO food_taxonomy VALUES ('pizza-001', 'Pizza', 'Main', 'Italian')")
        conn.execute("INSERT OR IGNORE INTO food_taxonomy VALUES ('burger-001', 'Burgers', 'Main', 'American')")
        conn.commit()
        conn.close()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def test_load_categories_from_taxonomy(self):
        processor = ImageProcessor(db_path=self.db_path, image_root=self.img_root)
        cats = processor._load_categories_from_taxonomy()
        self.assertIsNotNone(cats)
        self.assertIn("pizza", cats)
        self.assertIn("burgers", cats)

    def test_load_categories_fallback_when_no_db(self):
        processor = ImageProcessor(db_path="/nonexistent/test.db", image_root=self.img_root)
        self.assertEqual(processor.food_categories, FOOD_CATEGORIES)

    @patch("src.engine.image_processor.ImageProcessor._batch_process_images")
    def test_evaluate_no_ground_truth_runs_benchmark(self, mock_batch):
        mock_batch.return_value = None
        processor = ImageProcessor(db_path=self.db_path, image_root=self.img_root)
        result = processor.evaluate(ground_truth=None)
        self.assertIn("error", result)

    @patch("src.engine.image_processor.ImageProcessor._batch_process_images")
    def test_evaluate_with_ground_truth_no_images(self, mock_batch):
        mock_batch.return_value = None
        processor = ImageProcessor(db_path=self.db_path, image_root=self.img_root)
        result = processor.evaluate(ground_truth={"nonexistent_cid": "pizza"})
        self.assertIn("error", result)

    def test_build_predictions_structure(self):
        probs = torch.tensor([0.6, 0.3, 0.1])
        cats = ["pizza", "burger", "sushi"]
        preds = ImageProcessor._build_predictions(probs, cats, top_k=3)
        self.assertEqual(len(preds), 3)
        self.assertEqual(preds[0]["category"], "pizza")
        self.assertEqual(preds[0]["confidence"], 0.6)
        self.assertIn("category", preds[0])
        self.assertIn("confidence", preds[0])

    def test_build_predictions_top_k_less_than_categories(self):
        probs = torch.tensor([0.6, 0.3, 0.1, 0.0])
        cats = ["a", "b", "c", "d"]
        preds = ImageProcessor._build_predictions(probs, cats, top_k=2)
        self.assertEqual(len(preds), 2)

    def test_download_images_no_api_key(self):
        processor = ImageProcessor(db_path=self.db_path, image_root=self.img_root)
        result = processor.download_images("test_cid", ["ref1", "ref2"], api_key="")
        self.assertEqual(result, [])

    def test_benchmark_latency_no_images(self):
        processor = ImageProcessor(db_path=self.db_path, image_root=self.img_root)
        result = processor._benchmark_latency(sample_limit=5)
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
