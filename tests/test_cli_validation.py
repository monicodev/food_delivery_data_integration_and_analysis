import unittest
from src.validators import validate_weights, validate_threshold


class TestCLIValidation(unittest.TestCase):
    def test_valid_weights_pass(self):
        validate_weights(0.6, 0.4)
        validate_weights(0.0, 1.0)
        validate_weights(1.0, 0.0)

    def test_weights_out_of_range_raises(self):
        with self.assertRaises(SystemExit):
            validate_weights(-0.1, 1.1)
        with self.assertRaises(SystemExit):
            validate_weights(2.0, 0.0)

    def test_weights_not_summing_to_one_raises(self):
        with self.assertRaises(SystemExit):
            validate_weights(0.3, 0.3)
        with self.assertRaises(SystemExit):
            validate_weights(0.8, 0.3)

    def test_threshold_in_range_passes(self):
        validate_threshold(0.0)
        validate_threshold(0.5)
        validate_threshold(1.0)

    def test_threshold_out_of_range_raises(self):
        with self.assertRaises(SystemExit):
            validate_threshold(-0.1)
        with self.assertRaises(SystemExit):
            validate_threshold(1.1)


if __name__ == "__main__":
    unittest.main()
