import unittest
import os
import json
import sqlite3
import tempfile
from src.scraper.models import (
    VenueSchema, MenuItemSchema, MenuSectionSchema,
    MenuSchema, AddressSchema, RatingSchema
)
from src.scraper.persistence import PersistenceLayer


class TestScraperModels(unittest.TestCase):
    def test_menu_item_roundtrip(self):
        item = MenuItemSchema(name="Test Burger", description="Juicy", price=9.99)
        d = item.model_dump()
        self.assertEqual(d["name"], "Test Burger")
        self.assertEqual(d["price"], 9.99)

    def test_venue_schema_rich_structure(self):
        item = MenuItemSchema(name="Sushi Roll", price=12.0)
        section = MenuSectionSchema(name="Starters", items=[item])
        menu = MenuSchema(sections=[section])
        venue = VenueSchema(
            id="test-001",
            name="Test Restaurant",
            uniqueName="test-restaurant",
            address=AddressSchema(
                city="Barcelona",
                firstLine="Carrer Example 123",
                postalCode="08001",
                location={"type": "Point", "coordinates": [2.17, 41.39]}
            ),
            rating=RatingSchema(count=50, starRating=4.5),
            cuisines=["japanese", "sushi"],
            url="https://just-eat.es/test",
            menus={"hash1": menu}
        )

        d = venue.model_dump()
        self.assertEqual(d["name"], "Test Restaurant")
        self.assertEqual(d["address"]["city"], "Barcelona")
        self.assertEqual(d["rating"]["starRating"], 4.5)
        self.assertEqual(d["cuisines"], ["japanese", "sushi"])
        self.assertIn("hash1", d["menus"])
        self.assertEqual(d["menus"]["hash1"]["sections"][0]["items"][0]["name"], "Sushi Roll")

    def test_venue_no_menus(self):
        venue = VenueSchema(id="empty", name="Empty Place", url="http://example.com")
        d = venue.model_dump()
        self.assertEqual(d["name"], "Empty Place")
        self.assertEqual(len(d["menus"]), 0)


class TestPersistenceHelpers(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        self.output_dir = os.path.join(self.tmp_dir, "output")
        self.persist = PersistenceLayer(self.db_path, self.output_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir)

    def test_flatten_menu_items(self):
        items_a = [
            MenuItemSchema(name="Burger", price=9.99),
            MenuItemSchema(name="Fries", price=3.49)
        ]
        items_b = [MenuItemSchema(name="Soda", price=1.99)]
        section_a = MenuSectionSchema(name="Main", items=items_a)
        section_b = MenuSectionSchema(name="Drinks", items=items_b)
        menu = MenuSchema(sections=[section_a, section_b])
        venue = VenueSchema(id="v1", name="Test", url="x", menus={"m1": menu})

        flat = self.persist._flatten_menu_items(venue)
        self.assertEqual(len(flat), 3)
        names = [i.name for i in flat]
        self.assertIn("Burger", names)
        self.assertIn("Fries", names)
        self.assertIn("Soda", names)

    def test_get_address_string_full(self):
        addr = AddressSchema(city="BCN", firstLine="Calle 1", postalCode="08001")
        venue = VenueSchema(id="v1", name="Test", url="x", address=addr)
        result = self.persist._get_address_string(venue)
        self.assertIn("Calle 1", result)
        self.assertIn("BCN", result)

    def test_get_address_string_empty(self):
        venue = VenueSchema(id="v1", name="Test", url="x")
        result = self.persist._get_address_string(venue)
        self.assertEqual(result, "")

    def test_get_coordinates_from_location(self):
        addr = AddressSchema(location={"type": "Point", "coordinates": [2.17, 41.39]})
        venue = VenueSchema(id="v1", name="Test", url="x", address=addr)
        lat, lon = self.persist._get_coordinates(venue)
        self.assertAlmostEqual(lat, 41.39)
        self.assertAlmostEqual(lon, 2.17)

    def test_get_coordinates_missing(self):
        venue = VenueSchema(
            id="v1", name="Test", url="x",
            address=AddressSchema(location={"type": "Point", "coordinates": [None, None]})
        )
        lat, lon = self.persist._get_coordinates(venue)
        self.assertIsNone(lat)
        self.assertIsNone(lon)

    def test_save_to_sqlite_persists_flattened_items(self):
        items = [
            MenuItemSchema(name="Pizza", description="Cheesy", price=8.0),
            MenuItemSchema(name="Pasta", price=10.0)
        ]
        section = MenuSectionSchema(name="Food", items=items)
        menu = MenuSchema(sections=[section])
        venue = VenueSchema(id="v-test", name="Test Venue", url="http://x.com", menus={"m1": menu})

        self.persist.save_to_sqlite(venue)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM venues_je WHERE id='v-test'")
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("SELECT COUNT(*) FROM menu_items WHERE je_venue_id='v-test'")
        self.assertEqual(cursor.fetchone()[0], 2)
        conn.close()

    def test_save_to_json_contains_nested_structure(self):
        item = MenuItemSchema(name="Taco", price=5.0)
        section = MenuSectionSchema(name="Mexican", items=[item])
        menu = MenuSchema(sections=[section])
        venue = VenueSchema(id="v-json", name="JSON Venue", url="http://y.com", menus={"m1": menu})

        path = self.persist.save_to_json(venue)
        with open(path, 'r') as f:
            data = json.load(f)

        self.assertEqual(data["id"], "v-json")
        self.assertIn("menus", data)
        self.assertIn("address", data)
        self.assertIn("rating", data)
        self.assertIn("cuisines", data)


if __name__ == "__main__":
    unittest.main()
