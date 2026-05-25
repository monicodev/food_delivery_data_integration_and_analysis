import unittest
from src.scraper.crawler import ScraperEngine


class TestPriceParsingLocale(unittest.TestCase):
    def setUp(self):
        self.engine = ScraperEngine.__new__(ScraperEngine)

    def _parse(self, text: str, locale: str = "auto") -> float:
        return ScraperEngine._parse_price(text, locale)

    # --- US locale tests ---

    def test_us_simple_decimal(self):
        self.assertEqual(self._parse("10.50", "us"), 10.50)

    def test_us_comma_thousands(self):
        self.assertEqual(self._parse("1,050.50", "us"), 1050.50)

    def test_us_integer(self):
        self.assertEqual(self._parse("25", "us"), 25.0)

    def test_us_no_thousands(self):
        self.assertEqual(self._parse("1050.50", "us"), 1050.50)

    # --- EU locale tests ---

    def test_eu_comma_decimal(self):
        self.assertEqual(self._parse("10,50", "eu"), 10.50)

    def test_eu_dot_thousands(self):
        self.assertEqual(self._parse("1.050,50", "eu"), 1050.50)

    def test_eu_large_number(self):
        self.assertEqual(self._parse("10.500", "eu"), 10500.0)

    def test_eu_three_digit_decimal(self):
        self.assertEqual(self._parse("10,505", "eu"), 10.505)

    # --- Auto locale (heuristic) ---

    def test_auto_standard_decimal(self):
        self.assertEqual(self._parse("10.50"), 10.50)

    def test_auto_comma_decimal(self):
        self.assertEqual(self._parse("10,50"), 10.50)

    def test_auto_eu_thousands(self):
        self.assertEqual(self._parse("1.050,50"), 1050.50)

    def test_auto_us_thousands(self):
        self.assertEqual(self._parse("1,050.50"), 1050.50)

    # --- Edge cases ---

    def test_empty_string(self):
        self.assertEqual(self._parse(""), 0.0)

    def test_none_string(self):
        self.assertEqual(self._parse(None), 0.0)

    def test_no_number(self):
        self.assertEqual(self._parse("Free"), 0.0)
        self.assertEqual(self._parse("N/A"), 0.0)

    def test_with_currency_symbol(self):
        self.assertEqual(self._parse("€10.50"), 10.50)
        self.assertEqual(self._parse("$10.50"), 10.50)
        self.assertEqual(self._parse("£10.50"), 10.50)

    def test_whitespace(self):
        self.assertEqual(self._parse("  10.50  "), 10.50)

    def test_many_dots_auto_detects_as_decimal(self):
        self.assertEqual(self._parse("10.500"), 10.5)

    def test_single_dot_preserved(self):
        self.assertEqual(self._parse("10.50"), 10.50)

    def test_multiple_commas_auto(self):
        self.assertEqual(self._parse("1,000,000"), 1000000.0)

    def test_spanish_format_with_euro_trailing(self):
        self.assertEqual(self._parse("10,50 €"), 10.50)

    def test_spanish_format_large_with_euro_prefix(self):
        self.assertEqual(self._parse("€ 1.050,50"), 1050.50)

    def test_trailing_text(self):
        self.assertEqual(self._parse("10.50 EUR"), 10.50)

    def test_us_comma_large_trailing(self):
        self.assertEqual(self._parse("1,050 USD", "us"), 1050.0)

    def test_eu_locale_with_ambiguous_dots(self):
        self.assertEqual(self._parse("10.500", "eu"), 10500.0)

    def test_us_locale_with_ambiguous_commas(self):
        self.assertEqual(self._parse("10,500", "us"), 10500.0)
