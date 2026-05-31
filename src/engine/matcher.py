import json
import os
import re
import time
import uuid
import logging
from typing import List, Dict, Any, Optional
from src.engine.er_engine import EREngine
from src.engine.venue_loader import load_je_venues_data
from src.config import Config
from src.database.init_db import get_session, VenueGoogle, Match as DBMatch
logger = logging.getLogger(__name__)


class Matcher:
    def __init__(self, db_path: Optional[str] = None, google_venues_path: Optional[str] = None,
                 weight_name: Optional[float] = None, weight_geo: Optional[float] = None,
                 je_venues_path: Optional[str] = None, je_venues_split_dir: Optional[str] = None):
        self.db_path = db_path or str(Config.DB_PATH)
        self.google_venues_path = google_venues_path or str(Config.GOOGLE_VENUES_PATH)
        self.je_venues_path = je_venues_path or str(Config.JUST_EAT_VENUES_PATH)
        self.je_venues_split_dir = je_venues_split_dir or str(Config.JUST_EAT_VENUES_SPLIT_DIR)
        self.engine = EREngine(
            weight_name=weight_name if weight_name is not None else Config.ER_WEIGHT_NAME,
            weight_geo=weight_geo if weight_geo is not None else Config.ER_WEIGHT_GEO
        )

    def load_je_venues(self) -> List[Dict[str, Any]]:
        data = load_je_venues_data(self.je_venues_path, self.je_venues_split_dir)
        if not data:
            return []
        venues = []
        for venue_id, venue in data.items():
            addr = venue.get("address", {})
            location = addr.get("location") if addr else None
            coords = location.get("coordinates", [None, None]) if location else [None, None]
            venue_name = venue.get("name")
            if not venue_name:
                logger.warning("JE venue %s has no name, skipping", venue_id)
                continue
            venues.append({
                "id": venue_id,
                "name": venue_name,
                "name_clean": EREngine.clean_name(venue_name),
                "address": addr.get("firstLine", "") if addr else "",
                "city": addr.get("city", "") if addr else "",
                "latitude": float(coords[1]) if coords and coords[1] is not None else None,
                "longitude": float(coords[0]) if coords and coords[0] is not None else None
            })
        return venues

    @staticmethod
    def _detect_city(raw_address: str) -> str:
        if not raw_address:
            return "unknown"
        lower = raw_address.lower()
        for city in Config.KNOWN_CITIES:
            if re.search(r'\b' + re.escape(city.lower()) + r'\b', lower):
                return city
        return "unknown"

    @staticmethod
    def _safe_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def load_google_venues(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.google_venues_path):
            logger.warning("Google venues file not found: %s", self.google_venues_path)
            return []
        try:
            with open(self.google_venues_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                venues = []
                for idx, v in enumerate(data):
                    name = v.get("name")
                    if not name:
                        logger.warning("Google venue at index %d has no name, skipping", idx)
                        continue
                    raw_addr = v.get("rawAddress") or v.get("address", "")
                    vid = v.get("id") or v.get("googlePlaceId")
                    if not vid:
                        vid = str(uuid.uuid4())
                        logger.warning("Google venue '%s' has no id or googlePlaceId, generated UUID: %s", name, vid)
                    venues.append({
                        "id": vid,
                        "name": name,
                        "name_clean": EREngine.clean_name(name),
                        "address": raw_addr,
                        "latitude": self._safe_float(v.get("latitude")),
                        "longitude": self._safe_float(v.get("longitude")),
                        "city": self._detect_city(raw_addr)
                    })
                return venues
        except Exception as e:
            logger.error("Error loading Google venues from JSON: %s", e)
            return []

    def _export_matches_json(self, matches: List[Dict[str, Any]], output_path: Optional[str] = None):
        if output_path is None:
            output_path = os.path.join(str(Config.OUTPUT_DIR), "matches.json")
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(matches, f, indent=4, ensure_ascii=False)
            logger.info("Exported %d matches to %s", len(matches), output_path)
        except Exception as e:
            logger.error("Error exporting matches to JSON: %s", e)

    def _export_unmatched_json(self, unmatched_ids: List[str], output_path: Optional[str] = None):
        if output_path is None:
            output_path = os.path.join(str(Config.OUTPUT_DIR), "unmatched_venues.json")
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({"unmatched_je_venue_ids": unmatched_ids, "count": len(unmatched_ids)},
                          f, indent=4, ensure_ascii=False)
            logger.info("Exported %d unmatched venue IDs to %s", len(unmatched_ids), output_path)
        except Exception as e:
            logger.error("Error exporting unmatched venues to JSON: %s", e)

    def _group_by_city(self, venues: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for v in venues:
            city = v.get("city", "unknown") or "unknown"
            groups.setdefault(city, []).append(v)
        return groups

    @staticmethod
    def _geo_grid_key(lat: Optional[float], lon: Optional[float], cell_size_degrees: float = 0.05) -> str:
        """Assign a venue to a geographic grid cell for spatial pre-filtering.
        Cell size ~0.05° ≈ 5.6km at mid-latitudes."""
        if lat is None or lon is None:
            return "no_coords"
        cell_lat = round(lat / cell_size_degrees) * cell_size_degrees
        cell_lon = round(lon / cell_size_degrees) * cell_size_degrees
        return f"{cell_lat:.2f}_{cell_lon:.2f}"

    def _get_geo_candidates(self, je_lat: Optional[float], je_lon: Optional[float],
                             google_by_grid: Dict[str, List[Dict[str, Any]]],
                             google_venues: List[Dict[str, Any]],
                             cell_size: float = 0.05) -> List[Dict[str, Any]]:
        """Get candidate Google venues from the same or adjacent grid cells."""
        if je_lat is None or je_lon is None:
            return google_venues  # fallback: full scan
        center_cell = self._geo_grid_key(je_lat, je_lon, cell_size)
        candidates = list(google_by_grid.get(center_cell, []))
        # Also include adjacent cells (±1 in each direction)
        center_lat = round(je_lat / cell_size) * cell_size
        center_lon = round(je_lon / cell_size) * cell_size
        for dlat in (-cell_size, 0, cell_size):
            for dlon in (-cell_size, 0, cell_size):
                if dlat == 0 and dlon == 0:
                    continue
                adj_key = f"{center_lat + dlat:.2f}_{center_lon + dlon:.2f}"
                candidates.extend(google_by_grid.get(adj_key, []))
        return candidates

    def run_matching(self, threshold: Optional[float] = None):
        if threshold is None:
            threshold = Config.ER_DEFAULT_THRESHOLD
        je_venues = self.load_je_venues()
        google_venues = self.load_google_venues()

        if not je_venues or not google_venues:
            logger.warning("Missing data for matching. Aborting.")
            return

        logger.info("Starting matching process: %d JE venues vs %d Google venues", len(je_venues), len(google_venues))

        from src.database.init_db import init_db
        init_db(db_path=self.db_path)

        self._populate_venues_google(google_venues)

        # Load existing matches for re-check
        google_by_id: Dict[str, Dict[str, Any]] = {v["id"]: v for v in google_venues}
        session = get_session(self.db_path)
        old_matches: Dict[str, Dict[str, Any]] = {}
        try:
            for row in session.query(DBMatch).all():
                old_matches[row.je_venue_id] = {
                    "google_venue_id": row.google_venue_id,
                    "similarity_score": row.similarity_score,
                }
            logger.info("Loaded %d existing matches for re-check", len(old_matches))
        finally:
            session.close()

        # Build geo-spatial grid index
        google_by_grid: Dict[str, List[Dict[str, Any]]] = {}
        for v in google_venues:
            gk = self._geo_grid_key(v.get("latitude"), v.get("longitude"))
            google_by_grid.setdefault(gk, []).append(v)

        best_matches = {}
        unmatched_ids = []
        match_scores = []
        total_comparisons = 0
        total_je = len(je_venues)
        log_interval = max(1, total_je // 50)
        t_start = time.time()
        needs_full_search: List[Dict[str, Any]] = []

        for idx, je in enumerate(je_venues):
            je_id = je["id"]
            best_score = 0.0
            best_google_id = None
            is_matched = True

            old = old_matches.get(je_id)
            if old:
                gid = old["google_venue_id"]
                gv = google_by_id.get(gid)
                if gv:
                    score = self.engine.compute_total_score_cleaned(
                        je["name_clean"], je.get("latitude"), je.get("longitude"),
                        gv["name_clean"], gv.get("latitude"), gv.get("longitude"),
                        je.get("address", ""), gv.get("address", ""),
                    )
                    total_comparisons += 1
                    if score >= threshold:
                        best_score = score
                        best_google_id = gid
                    else:
                        is_matched = False
                else:
                    is_matched = False
            else:
                is_matched = False

            if not is_matched:
                needs_full_search.append(je)
                je_lat, je_lon = je.get("latitude"), je.get("longitude")
                candidates = self._get_geo_candidates(je_lat, je_lon, google_by_grid, google_venues)

                for google in candidates:
                    g_lat, g_lon = google.get("latitude"), google.get("longitude")
                    if (je_lat is not None and je_lon is not None
                            and g_lat is not None and g_lon is not None):
                        if abs(je_lat - g_lat) > 0.02 or abs(je_lon - g_lon) > 0.02:
                            continue

                    score = self.engine.compute_total_score_cleaned(
                        je["name_clean"], je_lat, je_lon,
                        google["name_clean"], g_lat, g_lon,
                        je.get("address", ""), google.get("address", "")
                    )
                    total_comparisons += 1
                    if score > best_score:
                        best_score = score
                        best_google_id = google["id"]

            if best_score >= threshold and best_google_id:
                best_matches[je_id] = {
                    "je_venue_id": je_id,
                    "google_venue_id": best_google_id,
                    "similarity_score": best_score
                }
                match_scores.append(best_score)
            else:
                unmatched_ids.append(je_id)

            elapsed = time.time() - t_start
            if (idx + 1) % log_interval == 0:
                rate = (idx + 1) / elapsed if elapsed > 0 else 0
                remaining = (total_je - idx - 1) / rate if rate > 0 else 0
                logger.info(
                    "Progress: %d/%d (%.0f%%) — %d comparisons — "
                    "elapsed %dm%02ds — ETA %dm%02ds",
                    idx + 1, total_je, (idx + 1) / total_je * 100,
                    total_comparisons,
                    int(elapsed // 60), int(elapsed % 60),
                    int(remaining // 60), int(remaining % 60),
                )

        # Enforce one-to-one: each Google venue matched to at most one JE venue
        google_used: set = set()
        deduped_matches = {}
        for je_id, match in sorted(best_matches.items(),
                                    key=lambda x: x[1]["similarity_score"], reverse=True):
            gid = match["google_venue_id"]
            if gid not in google_used:
                google_used.add(gid)
                deduped_matches[je_id] = match
            else:
                logger.debug("One-to-one enforcement: JE '%s' dropped, Google '%s' already matched",
                             je_id, gid)
                unmatched_ids.append(je_id)
        best_matches = deduped_matches

        if best_matches:
            match_list = list(best_matches.values())
            stale_ids = set(old_matches) - set(best_matches)
            self._persist_matches(match_list, stale_ids)
            self._export_matches_json(match_list)
            logger.info("Successfully persisted %d best matches (%d updated, %d stale removed)",
                         len(match_list), len(best_matches), len(stale_ids))
            if match_scores:
                logger.info("Match score distribution — min: %.4f, max: %.4f, mean: %.4f",
                            min(match_scores), max(match_scores), sum(match_scores) / len(match_scores))
        else:
            logger.info("No matches found above threshold.")

        if unmatched_ids:
            logger.info("Unmatched JE venues (%d): %s", len(unmatched_ids), unmatched_ids[:10])
            self._export_unmatched_json(unmatched_ids)
        rechecked = len(old_matches) - len(needs_full_search)
        logger.info("Total: %d JE venues — %d comparisons (re-checked %d, full-search %d)",
                     total_je, total_comparisons, rechecked, len(needs_full_search))

    def _populate_venues_google(self, google_venues: List[Dict[str, Any]]):
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        session = get_session(self.db_path)
        try:
            stmt = sqlite_insert(VenueGoogle).values([
                {
                    "id": v["id"],
                    "name": v["name"],
                    "address": v.get("address", ""),
                    "latitude": v.get("latitude"),
                    "longitude": v.get("longitude"),
                }
                for v in google_venues
            ])
            stmt = stmt.on_conflict_do_nothing()
            session.execute(stmt)
            session.commit()
            logger.info("Populated %d venues in venues_google table.", len(google_venues))
        except Exception as e:
            session.rollback()
            logger.error("Error populating venues_google: %s", e)
        finally:
            session.close()

    def _persist_matches(self, matches: List[Dict[str, Any]], stale_je_ids: set):
        session = get_session(self.db_path)
        try:
            if stale_je_ids:
                session.query(DBMatch).filter(
                    DBMatch.je_venue_id.in_(stale_je_ids)
                ).delete(synchronize_session=False)
            for m in matches:
                existing = session.query(DBMatch).filter_by(je_venue_id=m["je_venue_id"]).first()
                if existing:
                    existing.google_venue_id = m["google_venue_id"]
                    existing.similarity_score = m["similarity_score"]
                else:
                    session.add(DBMatch(
                        je_venue_id=m["je_venue_id"],
                        google_venue_id=m["google_venue_id"],
                        similarity_score=m["similarity_score"]
                    ))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Error persisting matches: %s", e)
        finally:
            session.close()

if __name__ == "__main__":
    matcher = Matcher()
    matcher.run_matching()
