import os
import json
import shutil
import tempfile
import pytest
import asyncio
from pathlib import Path

from src.config import Config
from src.scraper.crawler import ScraperEngine
from src.engine.matcher import Matcher
from src.database.init_db import init_db, get_session, VenueJE, MenuItem
from src.scraper.main import _validate_url


@pytest.fixture
def tmp_pipeline():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "pipeline.db")
    output_dir = os.path.join(tmp, "output", "venues")
    urls_file = os.path.join(tmp, "urls.json")
    google_venues_file = os.path.join(tmp, "google_venues.json")
    je_venues_file = os.path.join(tmp, "just_eat_venues.json")

    os.makedirs(output_dir, exist_ok=True)

    with open(urls_file, "w") as f:
        json.dump({"ven001": "https://www.just-eat.co.uk/restaurant-ven001"}, f)

    google_data = [
        {"googlePlaceId": "g001", "name": "Test Restaurant Ven001", "rawAddress": "Carrer de Test, Barcelona", "latitude": 41.40, "longitude": 2.17},
        {"googlePlaceId": "g002", "name": "Other Place", "rawAddress": "Carrer Other, Barcelona", "latitude": 41.41, "longitude": 2.18},
    ]
    with open(google_venues_file, "w") as f:
        json.dump(google_data, f)

    yield {
        "tmp": tmp,
        "db_path": db_path,
        "output_dir": output_dir,
        "urls_file": urls_file,
        "google_venues_file": google_venues_file,
        "je_venues_file": je_venues_file,
    }

    shutil.rmtree(tmp)


@pytest.mark.asyncio
async def test_pipeline_scrape_then_match(tmp_pipeline):
    cfg = tmp_pipeline

    engine = ScraperEngine(
        urls_path=cfg["urls_file"],
        db_path=cfg["db_path"],
        output_dir=cfg["output_dir"],
        use_mock=True,
    )
    await engine.run()

    json_files = [f for f in os.listdir(cfg["output_dir"]) if f.endswith(".json")]
    assert len(json_files) == 1, "Expected 1 scraped venue JSON"
    with open(os.path.join(cfg["output_dir"], json_files[0])) as f:
        venue_data = json.load(f)
    assert venue_data["id"] == "ven001"
    assert "menus" in venue_data
    assert len(venue_data["menus"]) > 0

    session = get_session(cfg["db_path"])
    try:
        venues = session.query(VenueJE).all()
        assert len(venues) == 1
        items = session.query(MenuItem).filter(MenuItem.je_venue_id == "ven001").all()
        assert len(items) == 4
    finally:
        session.close()

    init_db(db_path=cfg["db_path"])

    open(cfg["je_venues_file"], "w").close()
    with open(cfg["je_venues_file"], "w") as f:
        json.dump({"ven001": venue_data}, f)

    matcher = Matcher(
        db_path=cfg["db_path"],
        google_venues_path=cfg["google_venues_file"],
        je_venues_path=cfg["je_venues_file"],
    )
    matcher.run_matching(threshold=0.0)

    session = get_session(cfg["db_path"])
    try:
        from src.database.init_db import Match as DBMatch
        match_count = session.query(DBMatch).count()
        assert match_count >= 1, "Expected at least 1 match"
    finally:
        session.close()


def test_url_validation_edge_cases():
    assert _validate_url("https://www.just-eat.es/restaurants-edo/menu") is True
    assert _validate_url("") is False
    assert _validate_url(None) is False
    assert _validate_url("not a url") is False
    assert _validate_url("http://") is False
