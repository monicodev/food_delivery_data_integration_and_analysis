import json
import asyncio
from src.scraper.crawler import ScraperEngine


# --- Mock classes (must be defined before usage) ---

class MockScript:
    def __init__(self, data):
        self._data = data

    async def inner_text(self):
        return json.dumps(self._data)


class MockPage:
    def __init__(self, scripts_data: list):
        self._scripts = [MockScript(d) for d in scripts_data]

    async def query_selector_all(self, selector):
        return self._scripts


def _run_extract(page) -> list:
    return asyncio.run(ScraperEngine._extract_json_ld(page))


# --- Test data ---

BREADCRUMB = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home"},
        {"@type": "ListItem", "position": 2, "name": "Restaurants"},
        {"@type": "ListItem", "position": 3, "name": "Edo"},
    ],
}

RESTAURANT = {
    "@context": "https://schema.org",
    "@type": "Restaurant",
    "name": "Edo Barcelona",
    "servesCuisine": ["Japanese", "Sushi"],
    "address": {
        "@type": "PostalAddress",
        "streetAddress": "Calle General Mitre 136",
        "addressLocality": "Barcelona",
        "postalCode": "08006",
    },
    "geo": {"@type": "GeoCoordinates", "latitude": 41.3952, "longitude": 2.1453},
    "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4.2, "ratingCount": 312},
}

MENU = {
    "@context": "https://schema.org",
    "@type": "Menu",
    "name": "Carta",
    "hasMenuSection": [
        {
            "@type": "MenuSection",
            "name": "Sushi Rolls",
            "hasMenuItem": [
                {
                    "@type": "MenuItem",
                    "name": "California Roll",
                    "description": "Crab, avocado, cucumber",
                    "offers": {"@type": "Offer", "price": "12.50", "priceCurrency": "EUR"},
                },
                {
                    "@type": "MenuItem",
                    "name": "Salmon Roll",
                    "description": "Fresh salmon with rice",
                    "offers": {"@type": "Offer", "price": "10.00", "priceCurrency": "EUR"},
                },
            ],
        },
        {
            "@type": "MenuSection",
            "name": "Starters",
            "hasMenuItem": [
                {
                    "@type": "MenuItem",
                    "name": "Edamame",
                    "description": "Steamed soy beans with salt",
                    "offers": {"@type": "Offer", "price": "4.50", "priceCurrency": "EUR"},
                }
            ],
        },
    ],
}

ORGANIZATION = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "Just Eat",
}

GRAPH_WITH_RESTAURANT = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebSite", "name": "Site", "url": "https://example.com"},
        {
            "@type": "Restaurant",
            "name": "Edo Graph",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "Carrer Graph 42",
                "addressLocality": "Barcelona",
                "postalCode": "08008",
            },
            "servesCuisine": "Japanese",
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": 3.8, "ratingCount": 50},
        },
    ],
}

GRAPH_WITH_MENU = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebSite", "name": "Test", "url": "https://example.com"},
        {
            "@type": "Menu",
            "name": "Main Menu",
            "hasMenuSection": {
                "@type": "MenuSection",
                "name": "Drinks",
                "hasMenuItem": {
                    "@type": "MenuItem",
                    "name": "Green Tea",
                    "description": "Traditional Japanese green tea",
                    "offers": {"@type": "Offer", "price": "2.50", "priceCurrency": "EUR"},
                },
            },
        },
    ],
}

RESTAURANT_WITH_HASMENU = {
    "@context": "https://schema.org",
    "@type": "Restaurant",
    "name": "Test Place",
    "hasMenu": {
        "@type": "Menu",
        "hasMenuSection": {
            "@type": "MenuSection",
            "name": "Lunch",
            "hasMenuItem": {
                "@type": "MenuItem",
                "name": "Pizza",
                "description": "Margherita",
                "offers": {"@type": "Offer", "price": "8.00"},
            },
        },
    },
}


# --- _extract_json_ld tests ---

class TestExtractJsonLd:
    def test_returns_all_scripts(self):
        page = MockPage([BREADCRUMB, RESTAURANT, MENU, ORGANIZATION])
        result = _run_extract(page)
        assert len(result) == 4

    def test_flattens_graph(self):
        page = MockPage([GRAPH_WITH_RESTAURANT])
        result = _run_extract(page)
        assert len(result) == 3

    def test_returns_empty_when_no_scripts(self):
        page = MockPage([])
        result = _run_extract(page)
        assert result == []

    def test_handles_list_scripts(self):
        page = MockPage([[BREADCRUMB, ORGANIZATION]])
        result = _run_extract(page)
        assert len(result) == 2

    def test_handles_graph_with_menu(self):
        page = MockPage([GRAPH_WITH_MENU])
        result = _run_extract(page)
        assert len(result) == 3


# --- _extract_venue_info tests ---

class TestExtractVenueInfo:
    def test_extracts_all_fields(self):
        info = ScraperEngine._extract_venue_info([BREADCRUMB, RESTAURANT, ORGANIZATION])
        assert info["name"] == "Edo Barcelona"
        assert info["address"]["firstLine"] == "Calle General Mitre 136"
        assert info["address"]["city"] == "Barcelona"
        assert info["address"]["postalCode"] == "08006"
        assert info["address"]["location"]["coordinates"] == [2.1453, 41.3952]
        assert info["rating"]["starRating"] == 4.2
        assert info["rating"]["count"] == 312
        assert info["cuisines"] == ["Japanese", "Sushi"]

    def test_cuisines_string_converted_to_list(self):
        rest = dict(RESTAURANT)
        rest["servesCuisine"] = "Italian"
        info = ScraperEngine._extract_venue_info([rest])
        assert info["cuisines"] == ["Italian"]

    def test_returns_defaults_when_no_restaurant(self):
        info = ScraperEngine._extract_venue_info([BREADCRUMB, ORGANIZATION])
        assert info["name"] is None
        assert info["address"] is None
        assert info["rating"] is None

    def test_empty_list(self):
        info = ScraperEngine._extract_venue_info([])
        assert info["name"] is None

    def test_extracts_logo_url(self):
        rest = dict(RESTAURANT)
        rest["logo"] = "https://example.com/logo.png"
        info = ScraperEngine._extract_venue_info([rest])
        assert info["logo_url"] == "https://example.com/logo.png"

    def test_extracts_rating_count_from_reviewCount(self):
        """Just Eat uses reviewCount, not ratingCount — must handle both."""
        rest = dict(RESTAURANT)
        rest["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": 4.5,
            "reviewCount": 1596,
        }
        info = ScraperEngine._extract_venue_info([rest])
        assert info["rating"]["starRating"] == 4.5
        assert info["rating"]["count"] == 1596


# --- _extract_menu_from_json_ld tests ---

class TestExtractMenuFromJsonLd:
    def test_extracts_menu_sections_and_items(self):
        menus = ScraperEngine._extract_menu_from_json_ld([BREADCRUMB, MENU, ORGANIZATION])
        assert menus is not None
        assert len(menus) == 2
        assert menus[0].name == "Sushi Rolls"
        assert menus[0].items[0].name == "California Roll"
        assert menus[0].items[0].price == 12.50
        assert menus[1].name == "Starters"
        assert menus[1].items[0].name == "Edamame"

    def test_extracts_menu_from_restaurant_hasMenu(self):
        menus = ScraperEngine._extract_menu_from_json_ld([RESTAURANT_WITH_HASMENU])
        assert menus is not None
        item = menus[0].items[0]
        assert item.name == "Pizza"
        assert item.price == 8.0

    def test_returns_none_when_no_menu(self):
        menus = ScraperEngine._extract_menu_from_json_ld([BREADCRUMB, ORGANIZATION])
        assert menus is None or menus == []

    def test_empty_list(self):
        assert ScraperEngine._extract_menu_from_json_ld([]) is None or []


# --- Integration tests (full pipeline through _extract_json_ld) ---

class TestIntegration:
    def test_full_extraction_from_multiple_scripts(self):
        """Simulates real Just Eat page: Breadcrumb + Restaurant + Menu + Org."""
        page = MockPage([BREADCRUMB, RESTAURANT, MENU, ORGANIZATION])
        scripts = _run_extract(page)

        venue_info = ScraperEngine._extract_venue_info(scripts)
        assert venue_info["name"] == "Edo Barcelona"
        assert venue_info["address"]["firstLine"] == "Calle General Mitre 136"
        assert venue_info["rating"]["starRating"] == 4.2
        assert venue_info["cuisines"] == ["Japanese", "Sushi"]

        menus = ScraperEngine._extract_menu_from_json_ld(scripts)
        assert menus is not None
        assert len(menus) == 2

    def test_extraction_from_graph(self):
        """When data is inside @graph arrays, _extract_json_ld flattens them."""
        page = MockPage([GRAPH_WITH_RESTAURANT, GRAPH_WITH_MENU])
        scripts = _run_extract(page)

        venue_info = ScraperEngine._extract_venue_info(scripts)
        assert venue_info["name"] == "Edo Graph"
        assert venue_info["address"]["firstLine"] == "Carrer Graph 42"

        menus = ScraperEngine._extract_menu_from_json_ld(scripts)
        assert menus is not None
        item = menus[0].items[0]
        assert item.name == "Green Tea"
        assert item.price == 2.50

    def test_extraction_with_hasMenu_in_restaurant_block(self):
        """When menu is embedded in Restaurant's hasMenu field."""
        page = MockPage([RESTAURANT_WITH_HASMENU])
        scripts = _run_extract(page)

        venue_info = ScraperEngine._extract_venue_info(scripts)
        assert venue_info["name"] == "Test Place"

        menus = ScraperEngine._extract_menu_from_json_ld(scripts)
        assert menus is not None
        assert menus[0].items[0].name == "Pizza"
