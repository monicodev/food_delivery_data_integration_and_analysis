import sqlite3
from src.config import Config

def setup_db(db_path=None):
    if db_path is None:
        db_path = str(Config.DB_PATH)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM venues_je")
    cursor.execute("DELETE FROM matches")

    cursor.execute("INSERT INTO venues_je (id, name, address, latitude, longitude, url) VALUES (?, ?, ?, ?, ?, ?)",
                   ("JE001", "Burger King", "123 Main Street, London", 51.5075, -0.1279, "http://justeat.com/bk"))

    cursor.execute("INSERT INTO venues_je (id, name, address, latitude, longitude, url) VALUES (?, ?, ?, ?, ?, ?)",
                   ("JE002", "Pizza Hut London", "456 High Street, London", 51.5140, -0.1310, "http://just_eat.com/ph"))

    cursor.execute("INSERT INTO venues_je (id, name, address, latitude, longitude, url) VALUES (?, ?, ?, ?, ?, ?)",
                   ("JE003", "Taco Bell City", "999 Far Road, London", 52.0000, -1.0000, "http://just_eat.com/tb"))

    conn.commit()
    conn.close()
    print(f"Test data populated in {db_path}")

if __name__ == "__main__":
    setup_db()
