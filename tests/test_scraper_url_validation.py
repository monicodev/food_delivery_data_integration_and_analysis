import unittest
from src.scraper.main import _validate_url


class TestURLValidation(unittest.TestCase):
    def test_valid_https_url(self):
        self.assertTrue(_validate_url("https://www.just-eat.es/restaurants-madrid/menu/foo"))

    def test_valid_http_url(self):
        self.assertTrue(_validate_url("http://www.just-eat.es/restaurants/foo"))

    def test_empty_string(self):
        self.assertFalse(_validate_url(""))

    def test_none(self):
        self.assertFalse(_validate_url(None))

    def test_no_protocol(self):
        self.assertFalse(_validate_url("just-eat.es/restaurants/foo"))

    def test_random_text(self):
        self.assertFalse(_validate_url("not a url at all"))

    def test_whitespace_only(self):
        self.assertFalse(_validate_url("   "))


if __name__ == "__main__":
    unittest.main()
