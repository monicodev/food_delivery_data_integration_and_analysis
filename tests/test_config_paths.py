import unittest
import os
from src.config import Config


class TestConfigPaths(unittest.TestCase):
    def test_config_paths_are_absolute(self):
        self.assertTrue(os.path.isabs(Config.DB_PATH))
        self.assertTrue(os.path.isabs(Config.JUST_EAT_URLS_PATH))
        self.assertTrue(os.path.isabs(Config.GOOGLE_VENUES_PATH))
        self.assertTrue(os.path.isabs(Config.TAXONOMY_EXCEL_PATH))
        self.assertTrue(os.path.isabs(Config.OUTPUT_DIR))
        self.assertTrue(os.path.isabs(Config.VENUES_OUTPUT_DIR))
        self.assertTrue(os.path.isabs(Config.IMAGES_OUTPUT_DIR))
        self.assertTrue(os.path.isabs(Config.GOOGLE_IMAGES_DIR))
        self.assertTrue(os.path.isabs(Config.JUST_EAT_VENUES_PATH))

    def test_config_added_paths_exist(self):
        self.assertIn(Config.PROJECT_ROOT, Config.DB_PATH.parents)

    def test_config_scraper_timeout_has_default(self):
        self.assertGreater(Config.SCRAPER_NAVIGATION_TIMEOUT, 0)
        self.assertLessEqual(Config.SCRAPER_NAVIGATION_TIMEOUT, 120000)

    def test_config_max_redirects_has_default(self):
        self.assertGreater(Config.SCRAPER_MAX_REDIRECTS, 0)
        self.assertLessEqual(Config.SCRAPER_MAX_REDIRECTS, 20)

    def test_config_er_lambda_geo_default(self):
        self.assertGreater(Config.ER_LAMBDA_GEO, 0)
        self.assertLess(Config.ER_LAMBDA_GEO, 0.01)

    def test_config_er_weights_sum_to_one(self):
        total = Config.ER_WEIGHT_NAME + Config.ER_WEIGHT_GEO
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_config_known_cities_is_list(self):
        self.assertIsInstance(Config.KNOWN_CITIES, list)
        self.assertGreater(len(Config.KNOWN_CITIES), 5)
        self.assertIn("Barcelona", Config.KNOWN_CITIES)

    def test_config_food_categories_is_list(self):
        self.assertIsInstance(Config.FOOD_CATEGORIES, list)
        self.assertGreater(len(Config.FOOD_CATEGORIES), 10)
        self.assertIn("pizza", Config.FOOD_CATEGORIES)

    def test_config_classifier_model_name(self):
        self.assertIsInstance(Config.CLASSIFIER_MODEL_NAME, str)
        self.assertGreater(len(Config.CLASSIFIER_MODEL_NAME), 0)


if __name__ == "__main__":
    unittest.main()
