import json
import os
import re
import asyncio
import random
import logging
from typing import List, Optional, Dict, TYPE_CHECKING
from src.scraper.models import VenueSchema, MenuItemSchema, MenuSectionSchema, MenuSchema, AddressSchema, RatingSchema

if TYPE_CHECKING:
    from playwright.async_api import Page
from src.scraper.persistence import PersistenceLayer
from src.config import Config

logger = logging.getLogger(__name__)


class ScraperEngine:
    def __init__(self, urls_path: str, db_path: str, output_dir: str, use_mock: bool = False,
                 rate_limit_delay: int = None, max_retries: int = None, retry_base_delay: int = None,
                 navigation_timeout: int = None, max_redirects: int = None, locale: str = None):
        self.urls_path = urls_path
        self.db_path = db_path
        self.output_dir = output_dir
        self.use_mock = use_mock
        self.persistence = PersistenceLayer(db_path, output_dir)
        self.rate_limit_delay = rate_limit_delay or Config.SCRAPER_RATE_LIMIT_DELAY
        self.max_retries = max_retries or Config.SCRAPER_MAX_RETRIES
        self.retry_base_delay = retry_base_delay or Config.SCRAPER_RETRY_BASE_DELAY
        self.navigation_timeout = navigation_timeout or Config.SCRAPER_NAVIGATION_TIMEOUT
        self.max_redirects = max_redirects or Config.SCRAPER_MAX_REDIRECTS
        self.locale = locale or Config.SCRAPER_LOCALE
        self.stats = {"total": 0, "success": 0, "failed": 0, "redirect_loops": 0}

    async def load_urls(self) -> Dict[str, str]:
        if not os.path.exists(self.urls_path):
            return {}
        with open(self.urls_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {str(i): url for i, url in enumerate(data)}

    @staticmethod
    def _extract_venue_id(url: str) -> str:
        match = re.search(r'/restaurants[-/]?(.+?)(?:/menu|/|$)', url)
        if match:
            return match.group(1)
        match = re.search(r'/menu/(.+?)(?:/|$)', url)
        if match:
            return match.group(1)
        segments = [s for s in url.split('/') if s]
        return segments[-1] if segments else url

    @staticmethod
    def _parse_price(price_text: str, locale: str = "auto") -> float:
        """Parse a price string with locale-aware decimal/thousands handling.

        Locale options:
          "eu" — comma as decimal separator, dot as thousands separator (1.050,50 → 1050.50)
          "us" — dot as decimal separator (10.50 → 10.50)
          "auto" — heuristic detection based on separator positions
        """
        if not price_text:
            return 0.0
        clean = price_text.strip()
        clean = clean.replace('€', '').replace('$', '').replace('£', '').strip()
        dot_count = clean.count('.')
        comma_count = clean.count(',')

        if locale == "eu":
            clean = clean.replace('.', '')
            clean = clean.replace(',', '.')
        elif locale == "us":
            clean = clean.replace(',', '')
        else:
            # auto-detect locale from separator positions
            if dot_count > 0 and comma_count > 0:
                last_dot = clean.rfind('.')
                last_comma = clean.rfind(',')
                if last_comma > last_dot:
                    clean = clean.replace('.', '')
                    clean = clean.replace(',', '.')
                else:
                    clean = clean.replace(',', '')
            elif comma_count == 1 and dot_count == 0:
                clean = clean.replace(',', '.')
            elif comma_count > 1 and dot_count == 0:
                clean = clean.replace(',', '')
            elif dot_count == 1 and comma_count == 0:
                pass  # standard decimal, no change needed
            elif dot_count > 1 and comma_count == 0:
                clean = clean.replace('.', '')

        numeric_match = re.search(r'(\d+(?:\.\d+)?)', clean)
        if numeric_match:
            return float(numeric_match.group(1))
        return 0.0

    @staticmethod
    async def _handle_cookie_consent(page: "Page") -> bool:
        try:
            consent_selectors = [
                'button:has-text("Accept All")',
                'button:has-text("Accept all")',
                'button:has-text("Accept cookies")',
                'button:has-text("Accept")',
                'button:has-text("Allow All")',
                'button:has-text("Allow all")',
                'button:has-text("Agree")',
                'button:has-text("Got it")',
                'button:has-text("Continue")',
                '[aria-label*="cookie"] button',
                '[aria-label*="consent"] button',
                '#cookie-consent button',
                '.cookie-banner button',
                '.cc-btn',
                '.fc-button',
            ]
            for selector in consent_selectors:
                try:
                    btn = await page.query_selector(selector)
                    if btn:
                        await btn.click(timeout=3000)
                        await page.wait_for_timeout(500)
                        logger.info("Cookie consent accepted via '%s'", selector)
                        return True
                except Exception as e:
                    logger.debug("Cookie selector '%s' failed: %s", selector, e)
                    continue
            return False
        except Exception as e:
            logger.debug("Cookie consent handling failed: %s", e)
            return False

    async def _check_redirect_loop(self, url: str, redirect_history: list) -> bool:
        if url in redirect_history:
            logger.warning("Redirect loop detected for %s", url)
            return True
        redirect_history.append(url)
        return len(redirect_history) > self.max_redirects

    @staticmethod
    def _extract_menu_from_json_ld(data: dict) -> Optional[Dict[str, "MenuSchema"]]:
        """Extract menu data from schema.org JSON-LD structured data.
        Looks for hasMenu → Menu → hasMenuSection → MenuSection → hasMenuItem → MenuItem."""
        from src.scraper.models import MenuSchema, MenuSectionSchema, MenuItemSchema
        menus: Dict[str, MenuSchema] = {}
        menu_containers = []

        raw_menu = data.get("hasMenu")
        if raw_menu:
            menu_containers.append(raw_menu)
        sub_menus = data.get("subMenus") or []
        if isinstance(sub_menus, list):
            menu_containers.extend(sub_menus)

        for menu_entry in menu_containers:
            if isinstance(menu_entry, dict):
                sections_raw = menu_entry.get("hasMenuSection") or menu_entry.get("menuSection") or []
                if isinstance(sections_raw, dict):
                    sections_raw = [sections_raw]
                sections = []
                for sec in sections_raw:
                    if not isinstance(sec, dict):
                        continue
                    sec_name = sec.get("name", "Menu")
                    items_raw = sec.get("hasMenuItem") or sec.get("menuItem") or []
                    if isinstance(items_raw, dict):
                        items_raw = [items_raw]
                    items = []
                    for item in items_raw:
                        if not isinstance(item, dict):
                            continue
                        item_name = item.get("name", "")
                        if not item_name:
                            continue
                        item_desc = item.get("description", "")
                        offers = item.get("offers") or {}
                        if isinstance(offers, list):
                            offers = offers[0] if offers else {}
                        price_raw = offers.get("price", "0") if isinstance(offers, dict) else "0"
                        price = float(price_raw) if price_raw else 0.0
                        items.append(MenuItemSchema(
                            name=item_name,
                            description=item_desc,
                            price=price,
                        ))
                    if items:
                        sections.append(MenuSectionSchema(
                            name=sec_name,
                            items=items,
                        ))
                if sections:
                    menu_key = f"jsonld_menu_{len(menus)}"
                    menus[menu_key] = MenuSchema(sections=sections)
        return menus if menus else None

    @staticmethod
    async def _extract_json_ld(page: "Page") -> Optional[dict]:
        try:
            ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
            for script in ld_scripts:
                text = await script.inner_text()
                data = json.loads(text)
                if isinstance(data, dict) and 'name' in data:
                    return data
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'name' in item:
                            return item
        except Exception as e:
            logger.debug("JSON-LD extraction failed: %s", e)
            pass
        return None

    async def scrape_url(self, url: str, page: "Page", venue_id: Optional[str] = None,
                         redirect_history: Optional[list] = None) -> Optional[VenueSchema]:
        if self.use_mock:
            return self._mock_scrape(url, venue_id)

        if redirect_history is None:
            redirect_history = []
        if await self._check_redirect_loop(url, redirect_history):
            logger.error("Aborting due to redirect loop for %s", url)
            self.stats["redirect_loops"] = self.stats.get("redirect_loops", 0) + 1
            return None

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                if attempt > 1:
                    delay = self.retry_base_delay * (2 ** (attempt - 2)) + random.uniform(0, 2)
                    logger.info("Retry %d/%d for %s (waiting %.1fs)", attempt, self.max_retries, url, delay)
                    await asyncio.sleep(delay)

                await page.goto(url, wait_until="networkidle", timeout=self.navigation_timeout)
                await page.wait_for_timeout(2000)

                current_url = page.url
                if current_url != url:
                    logger.info("Redirected to %s", current_url)
                    if await self._check_redirect_loop(current_url, redirect_history):
                        logger.error("Aborting due to redirect loop after navigation")
                        return None
                await self._handle_cookie_consent(page)

                if not venue_id:
                    venue_id = self._extract_venue_id(url)

                name = "Unknown Restaurant"
                address_data = AddressSchema()
                rating_data = RatingSchema()
                cuisines = []
                logo_url = None
                menus: Dict[str, MenuSchema] = {}

                json_ld = await self._extract_json_ld(page)
                if json_ld:
                    json_name = json_ld.get('name')
                    if json_name:
                        name = json_name
                    jsonld_menus = self._extract_menu_from_json_ld(json_ld)
                    if jsonld_menus:
                        logger.info("Extracted menu data from JSON-LD for %s", name)
                        menus = jsonld_menus

                if name == "Unknown Restaurant":
                    for tag in ['h1', 'h2', '[data-testid="restaurant-name"]', '[class*="restaurant-name"]']:
                        try:
                            el = await page.query_selector(tag)
                            if el:
                                text = (await el.inner_text()).strip()
                                if text:
                                    name = text
                                    break
                        except Exception as e:
                            logger.debug("Name selector '%s' failed: %s", tag, e)
                            continue

                for selector in ['[data-testid="address"]', '[class*="address"]', '[class*="location"]',
                                 '[itemprop="address"]']:
                    try:
                        el = await page.query_selector(selector)
                        if el:
                            address_text = (await el.inner_text()).strip()
                            if address_text:
                                address_data.firstLine = address_text
                                break
                    except Exception as e:
                        logger.debug("Address selector '%s' failed: %s", selector, e)
                        continue

                # Only use CSS fallback if JSON-LD did not provide menus
                if not menus:
                    section_selectors = [
                        '[data-testid*="menu-section"]', '[class*="menu-section"]',
                        '[class*="category"]', '[class*="menu"]'
                    ]
                    item_selectors = [
                        '[data-testid*="menu-item"]', '[class*="menu-item"]',
                        '[class*="product"]', '[itemprop="menuItem"]'
                    ]
                    name_sel = ['.name', '.title', '[data-testid*="item-name"]', 'h3', 'h4', '[itemprop="name"]']
                    desc_sel = ['.description', '.desc', '[data-testid*="description"]', '[itemprop="description"]', 'p']
                    price_sel = ['.price', '[class*="price"]', '[data-testid*="price"]', '[itemprop="price"]']

                    sections_found = await page.query_selector_all(', '.join(section_selectors))
                    if not sections_found:
                        item_containers = await page.query_selector_all(', '.join(item_selectors))
                        if item_containers:
                            section_items = []
                            for container in item_containers:
                                try:
                                    item_name = None
                                    for s in name_sel:
                                        item_name = await container.query_selector(s)
                                        if item_name:
                                            break
                                    item_desc = None
                                    for s in desc_sel:
                                        item_desc = await container.query_selector(s)
                                        if item_desc:
                                            break
                                    item_price = None
                                    for s in price_sel:
                                        item_price = await container.query_selector(s)
                                        if item_price:
                                            break
                                    if item_name:
                                        item_image = None
                                        try:
                                            img_el = await container.query_selector('img')
                                            if img_el:
                                                item_image = await img_el.get_attribute('src')
                                        except Exception:
                                            pass
                                        section_items.append(MenuItemSchema(
                                            name=(await item_name.inner_text()).strip(),
                                            description=(await item_desc.inner_text()).strip() if item_desc else "",
                                            price=self._parse_price((await item_price.inner_text()).strip(), self.locale) if item_price else 0.0,
                                            image=item_image
                                        ))
                                except Exception as e:
                                    logger.debug("Menu item parsing failed: %s", e)
                                    continue
                            if section_items:
                                menus["scraped"] = MenuSchema(sections=[MenuSectionSchema(name="Menu", items=section_items)])
                    else:
                        for section_el in sections_found:
                            try:
                                section_name_el = await section_el.query_selector(':scope > h2, :scope > h3, :scope > .name, :scope > .title, :scope > [data-testid*="section-name"]')
                                section_name = (await section_name_el.inner_text()).strip() if section_name_el else "Menu"
                                section_items = []
                                items_in_section = await section_el.query_selector_all(', '.join(item_selectors))
                                for item_el in items_in_section:
                                    try:
                                        item_name = None
                                        for s in name_sel:
                                            item_name = await item_el.query_selector(s)
                                            if item_name:
                                                break
                                        if not item_name:
                                            item_name = await item_el.query_selector(':scope > *, :scope > div')
                                        if item_name:
                                            name_text = (await item_name.inner_text()).strip()
                                            item_desc = None
                                            for s in desc_sel:
                                                item_desc = await item_el.query_selector(s)
                                                if item_desc:
                                                    break
                                            item_price = None
                                            for s in price_sel:
                                                item_price = await item_el.query_selector(s)
                                                if item_price:
                                                    break
                                            item_image = None
                                            try:
                                                img_el = await item_el.query_selector('img')
                                                if img_el:
                                                    item_image = await img_el.get_attribute('src')
                                            except Exception:
                                                pass
                                            section_items.append(MenuItemSchema(
                                                name=name_text,
                                                description=(await item_desc.inner_text()).strip() if item_desc else "",
                                                price=self._parse_price((await item_price.inner_text()).strip(), self.locale) if item_price else 0.0,
                                                image=item_image
                                            ))
                                    except Exception as e:
                                        logger.debug("Section item parsing failed: %s", e)
                                        continue
                                if section_items:
                                    section = MenuSectionSchema(name=section_name, items=section_items)
                                    menu_id = f"section_{len(menus)}"
                                    if menu_id not in menus:
                                        menus[menu_id] = MenuSchema(sections=[section])
                                    else:
                                        menus[menu_id].sections.append(section)
                            except Exception:
                                continue

                return VenueSchema(
                    id=venue_id,
                    name=name,
                    address=address_data,
                    rating=rating_data,
                    cuisines=cuisines,
                    logoUrl=logo_url,
                    url=url,
                    menus=menus
                )

            except Exception as e:
                last_error = e
                logger.warning("Attempt %d/%d failed for %s: %s", attempt, self.max_retries, url, e)
                continue

        logger.error("All %d attempts failed for %s: %s", self.max_retries, url, last_error)
        return None

    def _mock_scrape(self, url: str, venue_id: Optional[str] = None) -> VenueSchema:
        if not venue_id:
            venue_id = self._extract_venue_id(url)

        mock_sections = [
            MenuSectionSchema(
                name="Starters",
                items=[
                    MenuItemSchema(name="Burger", description="Delicious beef burger", price=9.99),
                    MenuItemSchema(name="Fries", description="Crispy fries", price=3.49)
                ]
            ),
            MenuSectionSchema(
                name="Desserts",
                items=[
                    MenuItemSchema(name="Ice Cream", description="Vanilla ice cream", price=4.99),
                    MenuItemSchema(name="Brownie", description="Chocolate brownie", price=5.49)
                ]
            )
        ]
        menu_hash = "mock_menu_hash_001"
        menus = {
            menu_hash: MenuSchema(
                menuGroupId="MOCK_GROUP_001",
                type=["delivery"],
                sections=mock_sections
            )
        }

        return VenueSchema(
            id=venue_id,
            name=f"Mock Restaurant {venue_id}",
            uniqueName=f"mock-restaurant-{venue_id}",
            address=AddressSchema(
                city="Barcelona",
                firstLine="123 Carrer de Example",
                postalCode="08001",
                location={"type": "Point", "coordinates": [2.1686, 41.3874]}
            ),
            rating=RatingSchema(count=100, starRating=4.0),
            logoUrl=None,
            cuisines=["example-cuisine"],
            url=url,
            menus=menus
        )

    async def run(self, urls: Optional[List[str]] = None):
        if urls is None:
            urls_by_id = await self.load_urls()
        else:
            urls_by_id = {str(i): u for i, u in enumerate(urls)}

        if not urls_by_id:
            logger.info("No URLs found to scrape.")
            return

        if self.use_mock:
            for venue_id, url in urls_by_id.items():
                logger.info("Mock scraping [%s]: %s", venue_id, url)
                venue_data = self._mock_scrape(url, venue_id)
                if venue_data:
                    try:
                        self.persistence.save_to_json(venue_data)
                        self.persistence.save_to_sqlite(venue_data)
                        logger.info("Successfully processed %s", venue_data.id)
                    except Exception as e:
                        logger.error("Failed to persist data for %s: %s", url, e)
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright is not installed. Cannot run live scraping.")
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            user_agents = [
                Config.SCRAPER_USER_AGENT,
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]

            viewports = [
                {"width": 1920, "height": 1080},
                {"width": 1366, "height": 768},
                {"width": 1440, "height": 900},
                {"width": 1536, "height": 864},
            ]

            for idx, (venue_id, url) in enumerate(urls_by_id.items()):
                self.stats["total"] += 1
                logger.info("Scraping [%d/%d]: %s", idx + 1, len(urls_by_id), url)
                context = await browser.new_context(
                    user_agent=random.choice(user_agents),
                    viewport=random.choice(viewports),
                    locale="en-GB",
                    timezone_id="Europe/London",
                    geolocation={"latitude": 51.5074, "longitude": -0.1278},
                    permissions=["geolocation"]
                )
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en'] });
                """)
                page = await context.new_page()
                scrape_ok = False
                persist_ok = False
                try:
                    venue_data = await self.scrape_url(url, page, venue_id=venue_id)
                    if venue_data:
                        scrape_ok = True
                        try:
                            self.persistence.save_to_json(venue_data)
                            self.persistence.save_to_sqlite(venue_data)
                            logger.info("Successfully processed %s", venue_data.id)
                            persist_ok = True
                        except Exception as e:
                            logger.error("Failed to persist data for %s: %s", url, e)
                finally:
                    if scrape_ok and persist_ok:
                        self.stats["success"] += 1
                    else:
                        self.stats["failed"] += 1
                    await page.close()
                    await context.close()

                if idx < len(urls_by_id) - 1:
                    delay = self.rate_limit_delay + random.uniform(0, 2)
                    await asyncio.sleep(delay)

            await browser.close()

        # Log aggregate stats
        total = self.stats.get("total", 0)
        success = self.stats.get("success", 0)
        failed = self.stats.get("failed", 0)
        if total:
            logger.info("Scrape stats: %d total, %d success (%.1f%%), %d failed", total, success, success/total*100, failed)


if __name__ == "__main__":
    scraper = ScraperEngine(
        urls_path=str(Config.JUST_EAT_URLS_PATH),
        db_path=str(Config.DB_PATH),
        output_dir=str(Config.VENUES_OUTPUT_DIR),
        use_mock=Config.SCRAPER_USE_MOCK
    )

    async def _run():
        await scraper.run()
    asyncio.run(_run())
