import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def load_je_venues_data(primary_path: str, split_dir: str) -> Dict[str, Any]:
    """Load Just Eat venues from either a single JSON file or a split directory.
    
    Tries the single file first; if missing or empty, reads all part_*.json
    from the split directory and merges them.
    """
    if os.path.exists(primary_path):
        try:
            with open(primary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data:
                logger.info("Loaded %d venues from %s", len(data), primary_path)
                return data
        except Exception as e:
            logger.warning("Failed to load %s: %s", primary_path, e)

    if not os.path.isdir(split_dir):
        logger.error("No venues data found at %s or %s", primary_path, split_dir)
        return {}

    merged: Dict[str, Any] = {}
    part_files = sorted(f for f in os.listdir(split_dir) if f.startswith("part_") and f.endswith(".json"))

    if not part_files:
        logger.error("No part_*.json files found in %s", split_dir)
        return {}

    for fname in part_files:
        fpath = os.path.join(split_dir, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                chunk = json.load(f)
            merged.update(chunk)
        except Exception as e:
            logger.warning("Failed to load %s: %s", fpath, e)

    logger.info("Loaded %d venues from %d split files in %s", len(merged), len(part_files), split_dir)
    return merged


def import_venues_to_db(db_path: str, primary_path: str, split_dir: str) -> int:
    """Import Just Eat venues from JSON file(s) into the database.
    Returns the number of menu items imported.
    """
    from src.database.init_db import init_db, get_session, VenueJE, MenuItem

    data = load_je_venues_data(primary_path, split_dir)
    if not data:
        logger.error("No venue data to import")
        return 0

    init_db(db_path=db_path)
    session = get_session(db_path)

    total_items = 0
    venue_count = 0

    try:
        for venue_id, venue in data.items():
            venue_name = venue.get("name")
            if not venue_name:
                continue

            addr = venue.get("address", {}) or {}
            location = addr.get("location") if addr else None
            coords = location.get("coordinates", [None, None]) if location else [None, None]

            je_venue = VenueJE(
                id=venue_id,
                name=venue_name,
                address=addr.get("firstLine", "") if addr else "",
                latitude=float(coords[1]) if coords and coords[1] is not None else None,
                longitude=float(coords[0]) if coords and coords[0] is not None else None,
                url=venue.get("url", ""),
            )
            session.merge(je_venue)

            session.query(MenuItem).filter(MenuItem.je_venue_id == venue_id).delete()

            for menu_group in (venue.get("menus") or {}).values():
                for section in menu_group.get("sections") or []:
                    section_name = section.get("name", "general")
                    for item in section.get("items") or []:
                        item_name = item.get("name")
                        if not item_name:
                            continue
                        menu_item = MenuItem(
                            je_venue_id=venue_id,
                            name=item_name,
                            description=item.get("description", ""),
                            price=item.get("price"),
                            section=section_name,
                        )
                        session.add(menu_item)
                        total_items += 1

            venue_count += 1
            if venue_count % 200 == 0:
                session.flush()
                logger.info("Imported %d venues (%d items)...", venue_count, total_items)

        session.commit()
        logger.info("Imported %d venues with %d menu items into %s", venue_count, total_items, db_path)
    except Exception as e:
        session.rollback()
        logger.error("Error importing venues to DB: %s", e)
        raise
    finally:
        session.close()

    return total_items
