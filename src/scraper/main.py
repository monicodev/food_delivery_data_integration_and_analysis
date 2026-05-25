import argparse
import asyncio
import sys
import re
import logging
from src.config import Config
from src.scraper.crawler import ScraperEngine

logger = logging.getLogger(__name__)


def _validate_url(url: str) -> bool:
    """Basic URL validation — checks format and optionally just-eat domain."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not re.match(r'^https?://[^\s/$.?#].[^\s]*$', url, re.IGNORECASE):
        return False
    return True


async def main():
    parser = argparse.ArgumentParser(description="Just Eat Web Scraper")
    parser.add_argument("--url", type=str, help="Specific URL to scrape")
    parser.add_argument("--mock", action="store_true", help="Use mock data for testing")
    parser.add_argument("--db", type=str, default=str(Config.DB_PATH), help="Path to SQLite database")
    parser.add_argument("--output", type=str, default=str(Config.VENUES_OUTPUT_DIR), help="Output directory for JSON files")
    parser.add_argument("--urls-file", type=str, default=str(Config.JUST_EAT_URLS_PATH), help="Path to URLs JSON file")
    parser.add_argument("--rate-limit", type=int, default=Config.SCRAPER_RATE_LIMIT_DELAY, help="Delay between requests in seconds")
    parser.add_argument("--max-retries", type=int, default=Config.SCRAPER_MAX_RETRIES, help="Max retry attempts per URL")
    parser.add_argument("--retry-delay", type=int, default=Config.SCRAPER_RETRY_BASE_DELAY, help="Base delay for retry backoff")
    parser.add_argument("--locale", type=str, default=Config.SCRAPER_LOCALE, choices=["auto", "eu", "us"],
                        help="Locale for price parsing (auto, eu, us)")

    args = parser.parse_args()
    Config.ensure_dirs()

    if not args.mock:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright is not installed. Run --mock for offline mode or install playwright.")
            sys.exit(1)

    if args.url:
        if not _validate_url(args.url):
            logger.error("Invalid URL provided: %s", args.url)
            sys.exit(1)

    # Initialize the engine
    engine = ScraperEngine(
        urls_path=args.urls_file,
        db_path=args.db,
        output_dir=args.output,
        use_mock=args.mock,
        rate_limit_delay=args.rate_limit,
        max_retries=args.max_retries,
        retry_base_delay=args.retry_delay,
        locale=args.locale
    )

    if args.url:
        # Run for a single URL
        await engine.run(urls=[args.url])
    else:
        # Run for all URLs in the file
        await engine.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScraper stopped by user.")
        sys.exit(0)
