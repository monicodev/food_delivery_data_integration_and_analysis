import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables first so LOG_LEVEL / LOG_FILE are picked up
load_dotenv()


def _discover_project_root() -> Path:
    """Walk up from this file's directory to find the project root.
    Looks for pyproject.toml, .git, or known markers."""
    current = Path(__file__).resolve().parent.parent
    for _ in range(10):
        markers = [current / "pyproject.toml", current / ".git"]
        if any(m.exists() for m in markers):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path(__file__).resolve().parent.parent.parent


def _setup_logging():
    _log_level = os.getenv("LOG_LEVEL", "INFO")
    _log_file = os.getenv("LOG_FILE", "")

    _formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _root = logging.getLogger()
    _root.setLevel(getattr(logging, _log_level.upper(), logging.INFO))

    # Always log to stderr
    _sh = logging.StreamHandler(sys.stderr)
    _sh.setFormatter(_formatter)
    _root.addHandler(_sh)

    # Log to file (default: PROJECT_ROOT/data/logs/app.log)
    _log_path = Path(_log_file) if _log_file else (_discover_project_root() / "data" / "logs" / "app.log")
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _fh = logging.FileHandler(str(_log_path))
    _fh.setFormatter(_formatter)
    _root.addHandler(_fh)


_setup_logging()


def _discover_project_root() -> Path:
    """Walk up from this file's directory to find the project root.
    Looks for pyproject.toml, .git, or known markers."""
    current = Path(__file__).resolve().parent.parent
    for _ in range(10):
        markers = [current / "pyproject.toml", current / ".git"]
        if any(m.exists() for m in markers):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path(__file__).resolve().parent.parent.parent


def _int_env(key: str, default: int) -> int:
    """Read an integer from an env var with type-safety."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        logger.warning("Invalid %s=%r, falling back to %d", key, val, default)
        return default


def _float_env(key: str, default: float) -> float:
    """Read a float from an env var with type-safety."""
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        logger.warning("Invalid %s=%r, falling back to %f", key, val, default)
        return default


def _list_env(key: str, default: list) -> list:
    """Read a comma-separated list from an env var."""
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    return [item.strip() for item in val.split(",") if item.strip()]


class Config:
    """
    Centralized configuration for the Food Delivery Data Integration pipeline.
    Uses environment variables with sensible defaults.
    """
    PROJECT_ROOT = _discover_project_root()

    # Database Configuration
    DATABASE_DIR = PROJECT_ROOT / "data"
    DB_NAME = os.getenv("DATABASE_NAME", "food_delivery.db")
    DB_PATH = DATABASE_DIR / DB_NAME
    DATABASE_URL = f"sqlite:///{DB_PATH}"

    # Source Data Paths
    SOURCE_DIR = PROJECT_ROOT / "source"
    JUST_EAT_URLS_PATH = SOURCE_DIR / "just_eat_urls.json"
    GOOGLE_VENUES_PATH = SOURCE_DIR / "google_venues.json"
    TAXONOMY_EXCEL_PATH = SOURCE_DIR / "food_categories.xlsx"

    # Output Paths
    OUTPUT_DIR = SOURCE_DIR / "output"
    VENUES_OUTPUT_DIR = OUTPUT_DIR / "venues"
    IMAGES_OUTPUT_DIR = OUTPUT_DIR / "images"
    GOOGLE_IMAGES_DIR = SOURCE_DIR / "google_images"
    JUST_EAT_VENUES_PATH = SOURCE_DIR / "just_eat_venues.json"

    # Scraper Configuration
    SCRAPER_USE_MOCK = os.getenv("SCRAPER_USE_MOCK", "False").lower() == "true"
    SCRAPER_USER_AGENT = os.getenv("SCRAPER_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    SCRAPER_RATE_LIMIT_DELAY = _int_env("SCRAPER_RATE_LIMIT_DELAY", 3)
    SCRAPER_MAX_RETRIES = _int_env("SCRAPER_MAX_RETRIES", 3)
    SCRAPER_RETRY_BASE_DELAY = _int_env("SCRAPER_RETRY_BASE_DELAY", 5)
    SCRAPER_NAVIGATION_TIMEOUT = _int_env("SCRAPER_NAVIGATION_TIMEOUT", 60000)
    SCRAPER_MAX_REDIRECTS = _int_env("SCRAPER_MAX_REDIRECTS", 5)

    # API Configuration
    API_HOST = os.getenv("API_HOST", "localhost")
    API_PORT = _int_env("API_PORT", 8000)
    API_URL = f"http://{API_HOST}:{API_PORT}"
    API_CORS_ORIGINS = os.getenv("API_CORS_ORIGINS", f"http://{API_HOST}:{API_PORT},http://localhost:{API_PORT}").split(",")

    # Dashboard Configuration
    DASHBOARD_API_BASE_URL = API_URL

    # Entity Resolution Engine Configuration
    ER_WEIGHT_NAME = _float_env("ER_WEIGHT_NAME", 0.6)
    ER_WEIGHT_GEO = _float_env("ER_WEIGHT_GEO", 0.4)
    ER_LAMBDA_GEO = _float_env("ER_LAMBDA_GEO", 0.00035)
    ER_DEFAULT_THRESHOLD = _float_env("ER_DEFAULT_THRESHOLD", 0.70)
    KNOWN_CITIES = _list_env("KNOWN_CITIES", [
        "Barcelona", "Madrid", "Valencia", "Seville", "Bilbao",
        "Malaga", "Zaragoza", "Palma", "Las Palmas", "Alicante",
        "Murcia", "Granada", "Vigo", "Gijon", "Hospitalet de Llobregat",
        "London", "Paris", "Berlin", "Rome", "Milan", "Lisbon",
        "Porto", "Amsterdam", "Brussels", "Vienna", "Dublin",
        "Manchester", "Birmingham", "Liverpool", "Glasgow", "Edinburgh",
    ])

    # Text Classifier Configuration
    CLASSIFIER_MODEL_NAME = os.getenv("CLASSIFIER_MODEL_NAME", "all-MiniLM-L6-v2")
    CLASSIFIER_CONFIDENCE_THRESHOLD = _float_env("CLASSIFIER_CONFIDENCE_THRESHOLD", 0.5)

    # Image Processor Configuration
    IMAGE_BATCH_SIZE = _int_env("IMAGE_BATCH_SIZE", 10)
    IMAGE_MIN_WIDTH = _int_env("IMAGE_MIN_WIDTH", 50)
    IMAGE_MIN_HEIGHT = _int_env("IMAGE_MIN_HEIGHT", 50)
    IMAGE_MAX_BATCH_SIZE = _int_env("IMAGE_MAX_BATCH_SIZE", 32)
    FOOD_CATEGORIES = _list_env("FOOD_CATEGORIES", [
        "pizza", "burger", "sushi", "pasta", "salad",
        "sandwich", "taco", "hot dog", "soup", "steak",
        "fried chicken", "ramen", "dumplings", "donut",
        "ice cream", "cake", "cookie", "pancake", "waffle",
        "french fries", "nachos", "burrito", "quesadilla",
        "falafel", "hummus", "kebab", "curry", "rice bowl",
        "seafood", "grilled fish", "shrimp", "lobster",
        "roasted chicken", "bbq ribs", "bacon", "omelette",
        "cheese plate", "fruit salad", "smoothie", "coffee",
        "tea", "juice", "beer", "wine", "cocktail",
        "bread", "croissant", "bagel", "muffin", "pie",
    ])

    # Scraper Locale (auto, eu, us)
    SCRAPER_LOCALE = os.getenv("SCRAPER_LOCALE", "auto")

    @classmethod
    def ensure_dirs(cls):
        """Ensure all required directories exist. Call explicitly from entry points."""
        os.makedirs(cls.DATABASE_DIR, exist_ok=True)
        os.makedirs(cls.SOURCE_DIR, exist_ok=True)
        os.makedirs(cls.OUTPUT_DIR, exist_ok=True)
        os.makedirs(cls.VENUES_OUTPUT_DIR, exist_ok=True)
        os.makedirs(cls.IMAGES_OUTPUT_DIR, exist_ok=True)
