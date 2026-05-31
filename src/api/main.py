import os
import re
import json
import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from src.config import Config
from src.database.init_db import get_session, VenueJE, MenuItem, Match, FoodTaxonomy, Classification, ImageDetection

logger = logging.getLogger(__name__)


def _load_place_id_to_cid():
    path = os.path.join(str(Config.SOURCE_DIR), "google_venues.json")
    if not os.path.exists(path):
        logger.warning("google_venues.json not found at %s", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mapping = {}
        cid_re = re.compile(r"cid=(\d+)")
        for v in data:
            place_id = v.get("googlePlaceId")
            url = v.get("googleMapsUrl", "")
            m = cid_re.search(url)
            if place_id and m:
                mapping[place_id] = m.group(1)
        logger.info("Loaded %d place_id → cid mappings from google_venues.json", len(mapping))
        return mapping
    except Exception as e:
        logger.error("Failed to load google_venues.json: %s", e)
        return {}


PLACE_ID_TO_CID = _load_place_id_to_cid()

app = FastAPI(title="Food Delivery Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


class MatchRateStats(BaseModel):
    total_je_venues: int
    total_google_matches: int
    match_rate_percentage: float


class CategoryStats(BaseModel):
    category_name: str
    count: int


class VenueDensity(BaseModel):
    total_active_venues: int
    matched_venues: int
    total_menu_items: int


class HealthStatus(BaseModel):
    status: str
    database: str


class ClassificationCoverage(BaseModel):
    total_menu_items: int
    classified_items: int
    coverage_percentage: float


class VenueCoordinate(BaseModel):
    id: str
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_matched: bool = False


class VenueImageInfo(BaseModel):
    je_venue_id: str
    je_venue_name: str
    google_cid: str
    images: List[str]
    has_detections: bool = False


def _count_je_venues(db: Session) -> int:
    return db.query(func.count(VenueJE.id)).scalar() or 0


def _count_distinct_matched(db: Session) -> int:
    return db.query(func.count(func.distinct(Match.je_venue_id))).scalar() or 0


@app.get("/analytics/match-rate", response_model=MatchRateStats)
def get_match_rate(db: Session = Depends(get_db)):
    try:
        je_count = _count_je_venues(db)
        distinct_matched = _count_distinct_matched(db)
        rate = (distinct_matched / je_count * 100) if je_count > 0 else 0.0
        return MatchRateStats(
            total_je_venues=je_count,
            total_google_matches=distinct_matched,
            match_rate_percentage=round(rate, 2)
        )
    except Exception as e:
        logger.error("Error fetching match rate: %s", e)
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/analytics/categories", response_model=List[CategoryStats])
def get_category_stats(db: Session = Depends(get_db)):
    try:
        results = (
            db.query(FoodTaxonomy.name, func.count(Classification.id))
            .join(Classification, Classification.taxonomy_id == FoodTaxonomy.category_uidentifier)
            .group_by(FoodTaxonomy.name)
            .order_by(func.count(Classification.id).desc())
            .limit(10)
            .all()
        )
        return [CategoryStats(category_name=name, count=count) for name, count in results]
    except Exception as e:
        logger.error("Error fetching category stats: %s", e)
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/analytics/venue-density", response_model=VenueDensity)
def get_venue_density(db: Session = Depends(get_db)):
    try:
        total = _count_je_venues(db)
        matched = _count_distinct_matched(db)
        menu_count = db.query(func.count(MenuItem.id)).scalar() or 0
        return VenueDensity(
            total_active_venues=total,
            matched_venues=matched,
            total_menu_items=menu_count
        )
    except Exception as e:
        logger.error("Error fetching venue density: %s", e)
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/analytics/classification-coverage", response_model=ClassificationCoverage)
def get_classification_coverage(db: Session = Depends(get_db)):
    try:
        total = db.query(func.count(MenuItem.id)).scalar() or 0
        classified = db.query(func.count(func.distinct(Classification.menu_item_id))).scalar() or 0
        coverage = (classified / total * 100) if total > 0 else 0.0
        return ClassificationCoverage(
            total_menu_items=total,
            classified_items=classified,
            coverage_percentage=round(coverage, 2)
        )
    except Exception as e:
        logger.error("Error fetching classification coverage: %s", e)
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/health", response_model=HealthStatus)
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return HealthStatus(status="healthy", database="connected")
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return HealthStatus(status="unhealthy", database="disconnected")


@app.get("/analytics/venues", response_model=List[VenueCoordinate])
def get_venue_coordinates(db: Session = Depends(get_db)):
    try:
        matched_je_ids = set(
            row[0] for row in db.query(func.distinct(Match.je_venue_id)).all()
        )
        venues = db.query(VenueJE.id, VenueJE.name, VenueJE.latitude,
                          VenueJE.longitude).all()
        return [
            VenueCoordinate(
                id=v.id,
                name=v.name,
                latitude=v.latitude,
                longitude=v.longitude,
                is_matched=v.id in matched_je_ids
            )
            for v in venues
        ]
    except Exception as e:
        logger.error("Error fetching venue coordinates: %s", e)
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


@app.get("/analytics/venue-images", response_model=List[VenueImageInfo])
def get_venue_images(db: Session = Depends(get_db)):
    try:
        matches = db.query(Match.je_venue_id, Match.google_venue_id).all()
        detected_cids = set(
            row[0] for row in db.query(func.distinct(ImageDetection.google_cid)).all()
        )
        matched_ids = [m.je_venue_id for m in matches]
        venues_map = {
            v.id: v.name
            for v in db.query(VenueJE.id, VenueJE.name).filter(VenueJE.id.in_(matched_ids)).all()
        }
        images_dir = str(Config.GOOGLE_IMAGES_DIR)
        result = []
        seen_cids = set()
        for match in matches:
            google_cid = PLACE_ID_TO_CID.get(match.google_venue_id)
            if not google_cid or google_cid in seen_cids:
                continue
            venue_dir = os.path.join(images_dir, google_cid)
            if os.path.isdir(venue_dir):
                images = sorted([
                    f for f in os.listdir(venue_dir)
                    if f.lower().endswith(('.jpg', '.jpeg', '.png'))
                ])
                if images:
                    seen_cids.add(google_cid)
                    result.append(VenueImageInfo(
                        je_venue_id=match.je_venue_id,
                        je_venue_name=venues_map.get(match.je_venue_id, "Unknown"),
                        google_cid=google_cid,
                        images=images,
                        has_detections=google_cid in detected_cids
                    ))
        return result
    except Exception as e:
        logger.error("Error fetching venue images: %s", e)
        raise HTTPException(status_code=503, detail=f"Database error: {e}")


app.mount("/static/images", StaticFiles(directory=str(Config.GOOGLE_IMAGES_DIR)), name="images")
app.mount("/", StaticFiles(directory="src/api/static", html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    import argparse

    Config.ensure_dirs()

    parser = argparse.ArgumentParser(description="Food Delivery Analytics API")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
