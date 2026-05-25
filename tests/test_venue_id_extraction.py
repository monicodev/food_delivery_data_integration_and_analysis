import unittest
from src.scraper.crawler import ScraperEngine


class TestVenueIdExtraction(unittest.TestCase):
    """Test the improved _extract_venue_id with multiple URL patterns."""

    def setUp(self):
        self.extract = ScraperEngine._extract_venue_id

    def test_standard_restaurant_url(self):
        assert self.extract("https://www.just-eat.es/restaurants-edo/menu") == "edo"

    def test_restaurant_with_hyphens(self):
        assert self.extract("https://www.just-eat.es/restaurants-boston-alfonsxii/menu") == "boston-alfonsxii"

    def test_restaurant_without_menu_suffix(self):
        assert self.extract("https://www.just-eat.es/restaurants-edo") == "edo"

    def test_simple_id_fallback(self):
        assert self.extract("https://example.com/place/42") == "42"

    def test_short_url(self):
        assert self.extract("https://just-eat.es/restaurants-x/menu") == "x"

    def test_url_with_query_params(self):
        assert self.extract("https://www.just-eat.es/restaurants-edo/menu?param=1") == "edo"

    def test_empty_string(self):
        assert self.extract("") == ""


if __name__ == "__main__":
    unittest.main()
