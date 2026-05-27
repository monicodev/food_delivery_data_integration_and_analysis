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
    def _extract_menu_from_json_ld(jsonld_list: List[dict]) -> Optional[List["MenuSectionSchema"]]:
        """Extract menu data from JSON-LD structured data across all scripts.

        Searches all JSON-LD blocks for @type: "Menu" (or blocks containing
        hasMenu/hasMenuSection). Extracts menu sections and items, flattening
        all sections into a single list.
        """
        from src.scraper.models import MenuSectionSchema, MenuItemSchema
        all_sections: List[MenuSectionSchema] = []
        menu_containers: List[dict] = []

        for entry in jsonld_list:
            if not isinstance(entry, dict):
                continue

            etype = entry.get("@type", "")
            if isinstance(etype, list):
                is_menu = "Menu" in etype
            else:
                is_menu = etype == "Menu"

            if is_menu:
                menu_containers.append(entry)
            else:
                raw = entry.get("hasMenu")
                if raw is not None:
                    if isinstance(raw, dict):
                        menu_containers.append(raw)
                    elif isinstance(raw, list):
                        menu_containers.extend(raw)
                subs = entry.get("subMenus") or []
                if isinstance(subs, list):
                    menu_containers.extend(s for s in subs if isinstance(s, dict))

        for menu_entry in menu_containers:
            if not isinstance(menu_entry, dict):
                continue

            sections_raw = menu_entry.get("hasMenuSection") or menu_entry.get("menuSection") or []
            if isinstance(sections_raw, dict):
                sections_raw = [sections_raw]
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
                    all_sections.append(MenuSectionSchema(
                        name=sec_name,
                        items=items,
                    ))
        return all_sections if all_sections else None

    @staticmethod
    async def _extract_json_ld(page: "Page") -> List[dict]:
        """Extract ALL JSON-LD scripts from the page, flattening @graph arrays.

        Returns a flat list of all individual JSON-LD objects found across
        all <script type="application/ld+json"> tags, including items nested
        inside @graph arrays.
        """
        results: List[dict] = []
        try:
            ld_scripts = await page.query_selector_all('script[type="application/ld+json"]')
            for script in ld_scripts:
                text = await script.inner_text()
                data = json.loads(text)
                if isinstance(data, dict):
                    graph = data.pop("@graph", None)
                    if graph is not None and isinstance(graph, list):
                        for item in graph:
                            if isinstance(item, dict):
                                results.append(item)
                    results.append(data)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            results.append(item)
        except Exception as e:
            logger.debug("JSON-LD extraction failed: %s", e)
        return results

    @staticmethod
    def _extract_venue_info(jsonld_list: List[dict]) -> dict:
        """Extract venue metadata from JSON-LD blocks with @type: Restaurant/FoodEstablishment.

        Searches the flat list of JSON-LD objects for a restaurant block and
        returns name, address, rating, cuisines, and logo URL.
        """
        venue = {
            "name": None,
            "address": None,
            "rating": None,
            "cuisines": None,
            "logo_url": None,
        }
        for entry in jsonld_list:
            if not isinstance(entry, dict):
                continue
            etype = entry.get("@type", "")
            if isinstance(etype, list):
                if "Restaurant" not in etype and "FoodEstablishment" not in etype:
                    continue
            elif etype not in ("Restaurant", "FoodEstablishment"):
                continue

            if venue["name"] is None:
                venue["name"] = entry.get("name")

            addr = entry.get("address")
            if isinstance(addr, dict) and venue["address"] is None:
                geo = entry.get("geo") or addr.get("geo") or {}
                coords = [0.0, 0.0]
                if isinstance(geo, dict):
                    lat = geo.get("latitude", 0)
                    lng = geo.get("longitude", 0)
                    try:
                        coords = [float(lng), float(lat)]
                    except (ValueError, TypeError):
                        coords = [0.0, 0.0]
                venue["address"] = {
                    "firstLine": addr.get("streetAddress", ""),
                    "city": addr.get("addressLocality", ""),
                    "postalCode": addr.get("postalCode", ""),
                    "location": {"type": "Point", "coordinates": coords},
                }

            rating = entry.get("aggregateRating")
            if isinstance(rating, dict) and venue["rating"] is None:
                try:
                    star = float(rating.get("ratingValue", 0))
                except (ValueError, TypeError):
                    star = 0.0
                try:
                    count = int(rating.get("reviewCount") or rating.get("ratingCount", 0))
                except (ValueError, TypeError):
                    count = 0
                venue["rating"] = {"starRating": star, "count": count}

            cuisines = entry.get("servesCuisine")
            if cuisines and venue["cuisines"] is None:
                if isinstance(cuisines, str):
                    venue["cuisines"] = [cuisines]
                elif isinstance(cuisines, list):
                    venue["cuisines"] = [c for c in cuisines if isinstance(c, str)]

            if venue["logo_url"] is None:
                venue["logo_url"] = entry.get("logo") or entry.get("image")

            if all(v is not None for v in venue.values()):
                break

        return venue

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
                menus: List[MenuSectionSchema] = []

                jsonld_list = await self._extract_json_ld(page)

                if jsonld_list:
                    venue_info = self._extract_venue_info(jsonld_list)
                    if venue_info.get("name"):
                        name = venue_info["name"]
                        logger.info("Found name from JSON-LD Restaurant block: %s", name)
                    if venue_info.get("address"):
                        address_data = AddressSchema(**venue_info["address"])
                        logger.info("Found address from JSON-LD: %s", venue_info["address"]["firstLine"])
                    if venue_info.get("rating"):
                        rating_data = RatingSchema(**venue_info["rating"])
                    if venue_info.get("cuisines"):
                        cuisines = venue_info["cuisines"]
                    if venue_info.get("logo_url"):
                        logo_url = venue_info["logo_url"]

                    jsonld_menus = self._extract_menu_from_json_ld(jsonld_list)
                    if jsonld_menus:
                        logger.info("Extracted menu data from JSON-LD for %s (%d menus)", name, len(jsonld_menus))
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

                # CSS fallback for address: only if JSON-LD did not provide it
                if not address_data.firstLine:
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
                    try:
                        menu_container = await page.query_selector('[data-qa="menu-list"]')
                    except Exception:
                        menu_container = None

                    if menu_container is not None:
                        # --- Popular items carousel ---
                        try:
                            popular_el = await menu_container.query_selector('[data-qa="popular-items"]')
                            if popular_el:
                                pop_items_els = await popular_el.query_selector_all('[data-qa="popular-item"]')
                                pop_items = []
                                for el in pop_items_els:
                                    try:
                                        name_el = await el.query_selector('span[id^="name-"]')
                                        if not name_el:
                                            name_el = await el.query_selector('[data-qa="item-name"]')
                                        price_el = await el.query_selector('span[id^="price-"]')
                                        if not price_el:
                                            price_el = await el.query_selector('[data-qa="item-price"]')
                                        cat_el = await el.query_selector('[data-qa="popular-item-category"]')
                                        if name_el:
                                            pop_items.append(MenuItemSchema(
                                                name=(await name_el.inner_text()).strip(),
                                                price=self._parse_price((await price_el.inner_text()).strip(), self.locale) if price_el else 0.0,
                                                description=(await cat_el.inner_text()).strip() if cat_el else ""
                                            ))
                                    except Exception:
                                        continue
                                if pop_items:
                                    menus.append(MenuSectionSchema(name="Popular", items=pop_items))
                        except Exception:
                            pass

                        # --- Category sections (with lazy-load scroll trigger) ---
                        try:
                            cat_els = await menu_container.query_selector_all('[data-qa="item-category"]')
                            section_counter = 0
                            item_counter = 0
                            for cat_el in cat_els:
                                try:
                                    await cat_el.scroll_into_view_if_needed()
                                    await page.wait_for_timeout(300)

                                    name_el = await cat_el.query_selector('[data-qa="heading"]')
                                    section_name = (await name_el.inner_text()).strip() if name_el else "Menu"

                                    list_el = await cat_el.query_selector('ul[data-qa="item-category-list"]')
                                    if not list_el:
                                        list_el = await cat_el.query_selector('ul')
                                    if not list_el:
                                        continue

                                    item_els = await list_el.query_selector_all('li[data-item-id]')
                                    section_items = []
                                    for item_el in item_els:
                                        try:
                                            item_name_el = await item_el.query_selector('[data-qa="item-name"]')
                                            if not item_name_el:
                                                continue

                                            desc_text = ""
                                            try:
                                                text_els = await item_el.query_selector_all('[data-qa="text"]')
                                                parts = []
                                                for te in text_els:
                                                    in_price = await te.evaluate('(el) => !!el.closest("[data-qa=item-price]")')
                                                    in_name = await te.evaluate('(el) => !!el.closest("[data-qa=item-name]")')
                                                    if not in_price and not in_name:
                                                        text = (await te.inner_text()).strip()
                                                        if text:
                                                            parts.append(text)
                                                desc_text = "\n".join(parts)
                                            except Exception:
                                                pass

                                            price_el = await item_el.query_selector('[data-qa="item-price"]')
                                            price_text = (await price_el.inner_text()).strip() if price_el else "0"

                                            section_items.append(MenuItemSchema(
                                                id=f"item-{item_counter}",
                                                name=(await item_name_el.inner_text()).strip(),
                                                description=desc_text,
                                                price=self._parse_price(price_text, self.locale),
                                            ))
                                            item_counter += 1
                                        except Exception:
                                            continue

                                    if section_items:
                                        menus.append(MenuSectionSchema(
                                            id=f"section-{section_counter}",
                                            name=section_name,
                                            items=section_items
                                        ))
                                        section_counter += 1
                                except Exception:
                                    continue
                        except Exception:
                            pass

                    # --- Generic fallback (if structured approach found nothing) ---
                    if not menus:
                        section_selectors = [
                            '[data-testid*="menu-section"]', '[class*="menu-section"]',
                            '[class*="category"]', '[class*="menu"]'
                        ]
                        item_selectors = [
                            '[data-testid*="menu-item"]', '[data-qa*="menu-item"]',
                            '[class*="menu-item"]', '[class*="product"]',
                            '[itemprop="menuItem"]'
                        ]
                        name_sel = ['.name', '.title', '[data-testid*="item-name"]',
                                    '[data-qa*="item-name"]', 'h3', 'h4', '[itemprop="name"]']
                        desc_sel = ['.description', '.desc', '[data-testid*="description"]',
                                    '[data-qa*="description"]', '[itemprop="description"]', 'p']
                        price_sel = ['.price', '[class*="price"]', '[data-testid*="price"]',
                                     '[data-qa*="price"]', '[itemprop="price"]']

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
                                            section_items.append(MenuItemSchema(
                                                name=(await item_name.inner_text()).strip(),
                                                description=(await item_desc.inner_text()).strip() if item_desc else "",
                                                price=self._parse_price((await item_price.inner_text()).strip(), self.locale) if item_price else 0.0,
                                            ))
                                    except Exception as e:
                                        logger.debug("Menu item parsing failed: %s", e)
                                        continue
                                if section_items:
                                    menus.append(MenuSectionSchema(name="Menu", items=section_items))
                        else:
                            for section_el in sections_found:
                                try:
                                    section_name_el = await section_el.query_selector(':scope > h2, :scope > h3, :scope > .name, :scope > .title, :scope > [data-testid*="section-name"], :scope > [data-qa*="section-name"]')
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
                                                section_items.append(MenuItemSchema(
                                                    name=name_text,
                                                    description=(await item_desc.inner_text()).strip() if item_desc else "",
                                                    price=self._parse_price((await item_price.inner_text()).strip(), self.locale) if item_price else 0.0,
                                                ))
                                        except Exception as e:
                                            logger.debug("Section item parsing failed: %s", e)
                                            continue
                                    if section_items:
                                        menus.append(MenuSectionSchema(name=section_name, items=section_items))
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

        return VenueSchema(
            id=venue_id,
            name=f"Mock Restaurant {venue_id}",
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
            menus=mock_sections
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
