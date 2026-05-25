import unittest
from src.scraper.crawler import ScraperEngine


class TestParsePriceLocale(unittest.TestCase):
    """Test the improved locale-aware _parse_price implementation."""

    def setUp(self):
        self.parse = ScraperEngine._parse_price

    def test_us_format_comma_thousands(self):
        assert self.parse("1,234.56") == 1234.56

    def test_european_format_dot_thousands(self):
        assert self.parse("1.234,56") == 1234.56

    def test_simple_dot_decimal(self):
        assert self.parse("12.50") == 12.50

    def test_simple_comma_decimal(self):
        assert self.parse("12,50") == 12.50

    def test_integer_price(self):
        assert self.parse("15") == 15.0

    def test_price_with_euro_sign(self):
        assert self.parse("€12.99") == 12.99

    def test_price_with_dollar_sign(self):
        assert self.parse("9.99$") == 9.99

    def test_empty_string(self):
        assert self.parse("") == 0.0

    def test_none_price(self):
        assert self.parse(None) == 0.0

    def test_no_number_in_string(self):
        assert self.parse("free") == 0.0

    def test_trailing_text(self):
        assert self.parse("€ 10.50 EUR") == 10.50

    def test_european_with_leading_currency(self):
        assert self.parse("€ 1.234,56") == 1234.56

    def test_us_with_trailing_text(self):
        assert self.parse("$1,234.56 USD") == 1234.56

    def test_multiple_dots_european(self):
        assert self.parse("1.234.567,89") == 1234567.89

    def test_many_commas_us(self):
        assert self.parse("1,234,567.89") == 1234567.89

    def test_spanish_format_with_trailing_euro(self):
        assert self.parse("1.234,56 €") == 1234.56

    def test_spanish_format_large_with_euro_prefix(self):
        assert self.parse("€ 1.234.567,89") == 1234567.89

    def test_multiple_dots_no_commas(self):
        assert self.parse("1.234.567") == 1234567.0


if __name__ == "__main__":
    unittest.main()
