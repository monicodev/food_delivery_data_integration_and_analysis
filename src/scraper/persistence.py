import json
import os
from typing import Any, Dict, List
from src.config import Config
from src.scraper.models import VenueSchema, MenuItemSchema
from src.database.init_db import get_session, VenueJE, MenuItem as DBMenuItem


class PersistenceLayer:
    _initialized_dbs: set = set()

    def __init__(self, db_path: str, output_dir: str):
        self.db_path = db_path
        self.output_dir = output_dir
        Config.ensure_dirs()
        os.makedirs(self.output_dir, exist_ok=True)
        if db_path not in PersistenceLayer._initialized_dbs:
            from src.database.init_db import init_db
            init_db(db_path=db_path)
            PersistenceLayer._initialized_dbs.add(db_path)

    def _flatten_menu_items(self, venue_data: VenueSchema) -> List[MenuItemSchema]:
        items = []
        for section in venue_data.menus:
            items.extend(section.items)
        return items

    def _get_address_string(self, venue_data: VenueSchema) -> str:
        addr = venue_data.address
        parts = [p for p in [addr.firstLine, addr.city, addr.postalCode] if p]
        return ", ".join(parts) if parts else ""

    def _get_coordinates(self, venue_data: VenueSchema):
        location = venue_data.address.location or {}
        coords = location.get("coordinates")
        if coords and len(coords) >= 2 and coords[0] is not None and coords[1] is not None:
            return float(coords[1]), float(coords[0])
        return None, None

    def save_to_json(self, venue_data: VenueSchema) -> str:
        file_path = os.path.join(self.output_dir, f"{venue_data.id}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(venue_data.model_dump(), f, indent=4, ensure_ascii=False)
        return file_path

    def save_to_sqlite(self, venue_data: VenueSchema):
        session = get_session(self.db_path)
        try:
            lat, lon = self._get_coordinates(venue_data)
            address_str = self._get_address_string(venue_data)

            venue = VenueJE(
                id=venue_data.id,
                name=venue_data.name,
                address=address_str,
                latitude=lat,
                longitude=lon,
                url=venue_data.url
            )
            session.merge(venue)

            flat_items = self._flatten_menu_items(venue_data)
            for item in flat_items:
                menu_item = DBMenuItem(
                    je_venue_id=venue_data.id,
                    name=item.name,
                    description=item.description,
                    price=item.price
                )
                session.add(menu_item)

            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def save_batch_to_sqlite(self, venues: List[VenueSchema]):
        """Save multiple venues in a single transaction for better performance."""
        if not venues:
            return
        session = get_session(self.db_path)
        try:
            for venue_data in venues:
                lat, lon = self._get_coordinates(venue_data)
                address_str = self._get_address_string(venue_data)

                venue = VenueJE(
                    id=venue_data.id,
                    name=venue_data.name,
                    address=address_str,
                    latitude=lat,
                    longitude=lon,
                    url=venue_data.url
                )
                session.merge(venue)

                flat_items = self._flatten_menu_items(venue_data)
                for item in flat_items:
                    menu_item = DBMenuItem(
                        je_venue_id=venue_data.id,
                        name=item.name,
                        description=item.description,
                        price=item.price
                    )
                    session.add(menu_item)

            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
