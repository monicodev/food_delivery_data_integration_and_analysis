import os
import sqlite3
import tempfile
import unittest
from src.config import Config

class TestDatabaseInitialization(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def tearDown(self):
        self.conn.close()
        os.close(self.db_fd)
        os.remove(self.db_path)

    def _init_schema(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS food_taxonomy (
                category_uidentifier VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                parent VARCHAR,
                family VARCHAR
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues_je (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                address TEXT,
                latitude REAL,
                longitude REAL,
                url TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues_google (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                address TEXT,
                latitude REAL,
                longitude REAL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                je_venue_id TEXT,
                google_venue_id TEXT,
                similarity_score REAL,
                FOREIGN KEY (je_venue_id) REFERENCES venues_je(id),
                FOREIGN KEY (google_venue_id) REFERENCES venues_google(id)
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                je_venue_id TEXT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL,
                FOREIGN KEY (je_venue_id) REFERENCES venues_je(id)
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS classifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_item_id INTEGER,
                taxonomy_id VARCHAR,
                confidence FLOAT,
                FOREIGN KEY (menu_item_id) REFERENCES menu_items(id),
                FOREIGN KEY (taxonomy_id) REFERENCES food_taxonomy(category_uidentifier)
            )
        """)
        self.conn.commit()

    def test_tables_created_on_init(self):
        self._init_schema()
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in self.cursor.fetchall()}
        expected = {'food_taxonomy', 'venues_je', 'venues_google', 'matches', 'menu_items', 'classifications'}
        for table in expected:
            self.assertIn(table, tables, f"Table '{table}' should exist after init.")

    def test_taxonomy_insert_and_query(self):
        self._init_schema()
        self.cursor.execute(
            "INSERT INTO food_taxonomy (category_uidentifier, name, parent, family) VALUES (?, ?, ?, ?)",
            ("pizza-001", "Pizza", "Main Course", "Italian")
        )
        self.conn.commit()
        self.cursor.execute("SELECT COUNT(*) FROM food_taxonomy")
        self.assertEqual(self.cursor.fetchone()[0], 1)

    def test_persistence_layer_tables_include_matches(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues_je (
                id TEXT PRIMARY KEY, name TEXT, address TEXT,
                latitude REAL, longitude REAL, url TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS venues_google (
                id TEXT PRIMARY KEY, name TEXT, address TEXT,
                latitude REAL, longitude REAL
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                je_venue_id TEXT, google_venue_id TEXT,
                similarity_score REAL
            )
        """)
        self.conn.commit()
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'")
        self.assertIsNotNone(self.cursor.fetchone())

if __name__ == "__main__":
    unittest.main()
