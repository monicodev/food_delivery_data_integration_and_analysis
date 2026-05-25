import unittest
import tempfile
import json
import os
from src.scraper.crawler import ScraperEngine


class TestCrawlerUtilities(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def test_extract_venue_id_from_restaurant_url(self):
        url = "https://www.just-eat.es/restaurants-edo/menu"
        vid = ScraperEngine._extract_venue_id(url)
        self.assertEqual(vid, "edo")

    def test_extract_venue_id_with_hyphens(self):
        url = "https://www.just-eat.es/restaurants-boston-alfonsxii/menu"
        vid = ScraperEngine._extract_venue_id(url)
        self.assertEqual(vid, "boston-alfonsxii")

    def test_extract_venue_id_fallback(self):
        url = "https://www.just-eat.co.uk/venue-123"
        vid = ScraperEngine._extract_venue_id(url)
        self.assertEqual(vid, "venue-123")

    def test_parse_price_dot_decimal(self):
        self.assertEqual(ScraperEngine._parse_price("9.99"), 9.99)
        self.assertEqual(ScraperEngine._parse_price("€12.50"), 12.50)
        self.assertEqual(ScraperEngine._parse_price("$5"), 5.0)

    def test_parse_price_european_comma(self):
        self.assertEqual(ScraperEngine._parse_price("12,50"), 12.50)
        self.assertEqual(ScraperEngine._parse_price("€12,50"), 12.50)

    def test_parse_price_empty_string(self):
        self.assertEqual(ScraperEngine._parse_price(""), 0.0)

    def test_parse_price_no_number(self):
        self.assertEqual(ScraperEngine._parse_price("Free"), 0.0)

    def test_load_urls_from_dict(self):
        urls_file = os.path.join(self.tmp_dir, "urls_dict.json")
        data = {"631": "https://www.just-eat.es/restaurants-edo/menu"}
        with open(urls_file, 'w') as f:
            json.dump(data, f)
        engine = ScraperEngine(urls_file, ":memory:", self.tmp_dir, use_mock=True)
        import asyncio
        result = asyncio.run(engine.load_urls())
        self.assertEqual(result, data)

    def test_load_urls_from_list(self):
        urls_file = os.path.join(self.tmp_dir, "urls_list.json")
        data = ["https://www.just-eat.es/restaurants-edo/menu"]
        with open(urls_file, 'w') as f:
            json.dump(data, f)
        engine = ScraperEngine(urls_file, ":memory:", self.tmp_dir, use_mock=True)
        import asyncio
        result = asyncio.run(engine.load_urls())
        self.assertEqual(result, {"0": data[0]})

    def test_load_urls_missing_file(self):
        engine = ScraperEngine("/nonexistent.json", ":memory:", self.tmp_dir, use_mock=True)
        import asyncio
        result = asyncio.run(engine.load_urls())
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
