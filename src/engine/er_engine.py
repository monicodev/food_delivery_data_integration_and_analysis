import math
import re
import unicodedata
from typing import Optional
from rapidfuzz import fuzz
from src.config import Config


class EREngine:
    # Common business/generic words filtered out before name comparison.
    # Prevents "Kaede" vs "Restaurante Kaede" from scoring low.
    STOP_WORDS = frozenset({
        # Business type
        "restaurant", "restaurante", "pizzeria", "pizzería",
        "bar", "cafe", "café", "tavern", "taberna", "grill", "parrilla",
        "bistro", "canteen", "cafeteria", "cafetería",
        # Common cuisine words (too generic to discriminate)
        "pizza", "sushi", "burger", "kebab", "taco", "pasta", "curry",
        "wok", "kebab", "kebap", "doner", "döner",
        # Legal forms
        "ltd", "inc", "corp", "llc", "co", "limited", "corporation",
        "plc", "gmbh", "sarl", "sarl", "sa", "ag", "sas",
        "sl", "s.l.", "s.l",
        # Articles & prepositions (English, Spanish, Catalan)
        "the", "la", "el", "los", "las", "del", "de", "en", "un", "una",
        "al", "por", "con", "y", "e", "i", "a", "o", "lo",
        # Generic descriptors
        "food", "comida", "house", "casa", "home", "hogar",
        "express", "expresso", "fast", "rapido", "rápido",
        "club", "service", "servicio",
        "shop", "tienda", "store", "place", "lugar",
        "point", "punto", "center", "centro",
    })

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

    def _remove_stop_words(self, name: str) -> str:
        return " ".join(w for w in name.split() if w not in self.STOP_WORDS)

    @staticmethod
    def clean_name(name: str) -> str:
        """Pre-process + remove stop words. Call once per venue, not per comparison."""
        if not name:
            return ""
        name = unicodedata.normalize('NFKD', name)
        name = "".join(c for c in name if not unicodedata.combining(c))
        name = name.lower().strip()
        suffixes = {"ltd", "inc", "corp", "llc", "co", "limited", "corporation",
                     "plc", "gmbh", "sarl", "sa", "ag", "sas", "agency"}
        words = name.split()
        if words and words[-1] in suffixes:
            words.pop()
        name = " ".join(words)
        name = "".join(char for char in name if char.isalnum() or char.isspace())
        name = name.strip()
        cleaned = " ".join(w for w in name.split() if w not in EREngine.STOP_WORDS)
        return cleaned if cleaned else name

    def _score_cleaned_names(self, clean1: str, clean2: str) -> float:
        if not clean1 or not clean2:
            return 0.0

        full = fuzz.ratio(clean1, clean2) / 100.0
        best = max(full, fuzz.token_sort_ratio(clean1, clean2) / 100.0)

        if best < 0.70:
            set_ = fuzz.token_set_ratio(clean1, clean2) / 100.0
            best = max(best, set_)

        return best

    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        return self._score_cleaned_names(self.clean_name(name1), self.clean_name(name2))

    def calculate_address_similarity(self, addr1: str, addr2: str) -> float:
        if not addr1 or not addr2:
            return 0.0

        def normalize(s):
            s = unicodedata.normalize("NFKD", s)
            s = "".join(c for c in s if not unicodedata.combining(c))
            s = s.lower().strip()
            return re.sub(r"[^a-z0-9\s]", "", s)

        a1 = normalize(addr1)
        a2 = normalize(addr2)

        tokens1 = a1.split()
        tokens2 = a2.split()

        nums1 = {t for t in tokens1 if t.isdigit()}
        nums2 = {t for t in tokens2 if t.isdigit()}
        numbers_match = bool(nums1 & nums2)

        street_stops = {
            "calle", "carrer", "street", "ronda", "avenue", "av", "avda",
            "camino", "plaza", "passeig", "paseo", "via", "vía", "carretera",
            "c", "cr", "cl", "de", "del", "la", "el", "los", "las", "lo",
            "en", "al", "san", "santa", "sant",
        }
        stops = self.STOP_WORDS | street_stops

        name1 = [t for t in tokens1 if t not in stops and not t.isdigit()]
        name2 = [t for t in tokens2 if t not in stops and not t.isdigit()]
        common = set(name1) & set(name2)

        if numbers_match and common:
            return 1.0
        if numbers_match:
            return 0.5
        if common:
            return 0.3 * (len(common) / max(len(name1), len(name2), 1))
        return 0.0

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

    def compute_total_score_cleaned(self, clean_name1: str, lat1: float, lon1: float,
                                     clean_name2: str, lat2: float, lon2: float,
                                     addr1: str = "", addr2: str = "") -> float:
        s_name = self._score_cleaned_names(clean_name1, clean_name2)
        s_geo = self.calculate_geo_similarity(lat1, lon1, lat2, lon2)

        total_score = (self.weight_name * s_name) + (self.weight_geo * s_geo)

        if addr1 and addr2:
            s_addr = self.calculate_address_similarity(addr1, addr2)
            if s_addr > 0.8:
                total_score = min(1.0, total_score + 0.15)
            elif s_addr > 0.4:
                total_score = min(1.0, total_score + 0.08)

        return total_score

    def compute_total_score(self, name1: str, lat1: float, lon1: float,
                            name2: str, lat2: float, lon2: float,
                            addr1: str = "", addr2: str = "") -> float:
        return self.compute_total_score_cleaned(
            self.clean_name(name1), lat1, lon1,
            self.clean_name(name2), lat2, lon2,
            addr1, addr2,
        )
