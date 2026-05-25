import unittest
from src.engine.er_engine import EREngine

class TestEREngine(unittest.TestCase):
    def setUp(self):
        # Using default weights from spec/design as requested in prompt instructions
        self.engine = EREngine(weight_name=0.6, weight_geo=0.4)

    def test_high_score_match(self):
        """Test that a near-identical pair returns a high score."""
        name1, lat1, lon1 = "Burger King London", 51.5074, -0.1278
        name2, lat2, lon2 = "Burger King", 51.5075, -0.1279
        
        score = self.engine.compute_total_score(name1, lat1, lon1, name2, lat2, lon2)
        self.assertGreaterEqual(score, 0.84)

    def test_low_score_mismatch(self):
        """Test that a non-matching pair returns a low score."""
        # Name matches partially but location is very far
        name1, lat1, lon1 = "Burger King", 51.5074, -0.1278
        name2, lat2, lon2 = "Taco Bell", 52.0000, -1.0000
        
        score = self.engine.compute_total_score(name1, lat1, lon1, name2, lat2, lon2)
        self.assertLess(score, 0.4)

    def test_null_handling(self):
        """Test that missing coordinates are handled gracefully (partial score)."""
        # If geo is missing, we should still get the weighted name score: 0.6 * 1.0 + 0.4 * 0.0 = 0.6
        score = self.engine.compute_total_score("Burger King", None, -0.1278, "Burger King", 51.5074, -0.1278)
        self.assertAlmostEqual(score, 0.6)


if __name__ == "__main__":
    unittest.main()
