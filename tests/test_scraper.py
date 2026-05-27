import os
import json
import sqlite3
import pytest
import asyncio
import shutil
import tempfile

from src.scraper.crawler import ScraperEngine
from src.config import Config


def _find_menu_item(data: dict, target_name: str) -> bool:
    for section in data.get("menus", []):
        for item in section.get("items", []):
            if item.get("name") == target_name:
                return True
    return False


@pytest.mark.asyncio
async def test_scraper_mock_flow():
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test_food_delivery.db")
    output_dir = os.path.join(tmp_dir, "output", "test_venues")
    urls_file = os.path.join(tmp_dir, "test_urls.json")

    test_urls = {
        "venue-1": "https://www.just-eat.co.uk/test-venue-1",
        "venue-2": "https://www.just-eat.co.uk/test-venue-2"
    }
    with open(urls_file, 'w') as f:
        json.dump(test_urls, f)

    engine = ScraperEngine(
        urls_path=urls_file,
        db_path=db_path,
        output_dir=output_dir,
        use_mock=True
    )

    await engine.run()

    for venue_id in test_urls:
        json_file = os.path.join(output_dir, f"{venue_id}.json")
        assert os.path.exists(json_file)

        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            assert data['id'] == venue_id
            assert _find_menu_item(data, "Burger")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT count(*) FROM venues_je")
    assert cursor.fetchone()[0] == 2

    cursor.execute("SELECT count(*) FROM menu_items")
    assert cursor.fetchone()[0] == 8

    conn.close()

    shutil.rmtree(tmp_dir)
