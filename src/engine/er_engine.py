import math
import unicodedata
from typing import Optional
from rapidfuzz import fuzz
from src.config import Config


class EREngine:
    def __init__(self, weight_name: Optional[float] = None, weight_geo: Optional[float] = None,
                 lambda_geo: Optional[float] = None):
        """
        Initialize the ER Engine with weights and decay constant.
        Defaults from Config when arguments are not provided.

        :param weight_name: Weight for name similarity score.
        :param weight_geo: Weight for geospatial similarity score.
        :param lambda_geo: Decay constant for Haversine distance exponential decay.
        """
        self.weight_name = weight_name if weight_name is not None else Config.ER_WEIGHT_NAME
        self.weight_geo = weight_geo if weight_geo is not None else Config.ER_WEIGHT_GEO
        self.lambda_geo = lambda_geo if lambda_geo is not None else Config.ER_LAMBDA_GEO

    def _preprocess_name(self, name: str) -> str:
        """
        Pre-process the venue name for better matching accuracy.
        Includes Unicode normalization and removal of common business suffixes.
        """
        if not name:
            return ""
        
        # Normalize Unicode: NFKD decomposes accented chars (é → e + ◌́),
        # then strip combining diacritical marks while keeping non-Latin scripts.
        name = unicodedata.normalize('NFKD', name)
        name = "".join(c for c in name if not unicodedata.combining(c))
        
        # Lowercase and strip whitespace/special characters
        name = name.lower().strip()
        
        # Remove common business suffixes
        suffixes = [
            "ltd", "inc", "corp", "llc", "co", "limited", "corporation",
            "plc", "gmbh", "sarl", "sa", "ag", "sas", "agency",
        ]
        
        # Split by non-alphanumeric characters to identify suffixes more accurately
        words = name.split()
        if words and words[-1] in suffixes:
            words.pop()
        
        name = " ".join(words)
        
        # Remove punctuation
        name = "".join(char for char in name if char.isalnum() or char.isspace())
        
        return name.strip()

    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate normalized Levenshtein distance similarity using RapidFuzz.
        """
        processed1 = self._preprocess_name(name1)
        processed2 = self._preprocess_name(name2)
        
        if not processed1 or not processed2:
            return 0.0
            
        # fuzz.ratio returns a score from 0 to 100
        score = fuzz.ratio(processed1, processed2)
        return score / 100.0

    def calculate_haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great circle distance between two points on Earth in meters.
        """
        # Radius of Earth in meters
        R = 6371000.0

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2)**2 + \
            math.cos(phi1) * math.cos(phi2) * \
            math.sin(delta_lambda / 2)**2
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def calculate_geo_similarity(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate geospatial similarity score using exponential decay of distance.
        S_geo = e^{-lambda * d}
        """
        if any(x is None for x in (lat1, lon1, lat2, lon2)):
            return 0.0

        try:
            distance = self.calculate_haversine_distance(lat1, lon1, lat2, lon2)
            # S_geo = e^(-lambda * distance)
            score = math.exp(-self.lambda_geo * distance)
            return score
        except (ValueError, TypeError):
            return 0.0

    def compute_total_score(self, name1: str, lat1: float, lon1: float, 
                            name2: str, lat2: float, lon2: float) -> float:
        """
        Compute the weighted total similarity score.
        S_total = (w_name * S_name) + (w_geo * S_geo)
        """
        s_name = self.calculate_name_similarity(name1, name2)
        s_geo = self.calculate_geo_similarity(lat1, lon1, lat2, lon2)

        total_score = (self.weight_name * s_name) + (self.weight_geo * s_geo)
        return total_score
