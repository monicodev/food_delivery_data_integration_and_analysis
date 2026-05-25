import os
from sqlalchemy import create_engine, Column, String, Float, Integer, ForeignKey, Text, func
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from src.config import Config

DATABASE_URL = Config.DATABASE_URL

_engine_cache: dict = {}

Base = declarative_base()


class FoodTaxonomy(Base):
    __tablename__ = 'food_taxonomy'
    category_uidentifier = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    parent = Column(String)
    family = Column(String)


class VenueJE(Base):
    __tablename__ = 'venues_je'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)
    url = Column(String)
    menu_items = relationship("MenuItem", back_populates="venue")


class VenueGoogle(Base):
    __tablename__ = 'venues_google'
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)


class Match(Base):
    __tablename__ = 'matches'
    id = Column(Integer, primary_key=True, autoincrement=True)
    je_venue_id = Column(String, ForeignKey('venues_je.id'))
    google_venue_id = Column(String, ForeignKey('venues_google.id'))
    similarity_score = Column(Float)


class MenuItem(Base):
    __tablename__ = 'menu_items'
    id = Column(Integer, primary_key=True, autoincrement=True)
    je_venue_id = Column(String, ForeignKey('venues_je.id'))
    name = Column(String, nullable=False)
    description = Column(Text)
    price = Column(Float)
    venue = relationship("VenueJE", back_populates="menu_items")


class Classification(Base):
    __tablename__ = 'classifications'
    id = Column(Integer, primary_key=True, autoincrement=True)
    menu_item_id = Column(Integer, ForeignKey('menu_items.id'))
    taxonomy_id = Column(String, ForeignKey('food_taxonomy.category_uidentifier'))
    confidence = Column(Float)


class ImageDetection(Base):
    __tablename__ = 'image_detections'
    id = Column(Integer, primary_key=True, autoincrement=True)
    google_cid = Column(String, nullable=False)
    concept = Column(String, nullable=False)
    confidence = Column(Float)
    created_at = Column(String, server_default=func.current_timestamp())


def _get_engine(db_path: str = None):
    """Create or retrieve a cached SQLAlchemy engine for the given db_path."""
    url = f"sqlite:///{db_path}" if db_path else DATABASE_URL
    cache_key = db_path or str(Config.DB_PATH)
    if cache_key not in _engine_cache:
        _engine_cache[cache_key] = create_engine(url, connect_args={"check_same_thread": False})
    return _engine_cache[cache_key]


def init_db(db_path: str = None):
    """Initialize the database and create tables.
    
    Args:
        db_path: Optional custom database path (for testing). Defaults to Config.DB_PATH.
    """
    target = db_path or str(Config.DB_PATH)
    if target != ":memory:":
        os.makedirs(os.path.dirname(target), exist_ok=True)
    engine = _get_engine(db_path)
    Base.metadata.create_all(bind=engine)


def get_session(db_path: str = None):
    """Get a new SQLAlchemy session for the given db_path or the default."""
    engine = _get_engine(db_path)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def ingest_taxonomy(excel_path, db_path: str = None):
    """Ingest taxonomy from Excel file.
    
    Args:
        excel_path: Path to the Excel taxonomy file.
        db_path: Optional custom database path. Defaults to Config.DB_PATH.
    """
    import pandas as pd

    if not os.path.exists(excel_path):
        print(f"Taxonomy file not found: {excel_path}. Skipping ingestion.")
        return

    print(f"Ingesting taxonomy from: {excel_path}")
    try:
        df = pd.read_excel(excel_path)
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        session = get_session(db_path)
        try:
            for _, row in df.iterrows():
                taxonomy = FoodTaxonomy(
                    category_uidentifier=str(row['uidentifier']),
                    name=str(row['name']),
                    parent=str(row['parent']) if pd.notna(row['parent']) else None,
                    family=str(row['family']) if pd.notna(row['family']) else None
                )
                session.merge(taxonomy)
            session.commit()
            print(f"Successfully ingested {len(df)} taxonomy entries.")
        except Exception as e:
            session.rollback()
            print(f"Error during taxonomy ingestion: {e}")
            raise
        finally:
            session.close()
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        raise


if __name__ == "__main__":
    Config.ensure_dirs()
    init_db()
    taxonomy_excel = Config.TAXONOMY_EXCEL_PATH
    ingest_taxonomy(taxonomy_excel)
