import argparse
import sys
import os
import logging

from src.config import Config
from src.engine.matcher import Matcher
# Lazy imports: ClassifierOrchestrator and ImageProcessor are imported inside their
# respective code branches to avoid requiring heavy ML deps (torch, transformers, etc.)
# when only running entity resolution.
from src.validators import validate_weights, validate_threshold

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Food Delivery Data Integration: ER Engine Orchestrator")

    parser.add_argument("--db-path", type=str, default=str(Config.DB_PATH),
                        help="Path to the SQLite database file")
    parser.add_argument("--google-venues-json", type=str, default=str(Config.GOOGLE_VENUES_PATH),
                        help="Path to the Google venues JSON file")
    parser.add_argument("--threshold", type=float, default=0.70,
                        help="Similarity score threshold for a match (default: 0.70)")
    parser.add_argument("--weight-name", type=float, default=0.6,
                        help="Weight for name similarity (0.0 - 1.0, default: 0.6)")
    parser.add_argument("--weight-geo", type=float, default=0.4,
                        help="Weight for geospatial similarity (0.0 - 1.0, default: 0.4)")
    parser.add_argument("--classify", action="store_true",
                        help="Run the text classification pipeline")
    parser.add_argument("--force", action="store_true",
                        help="Force re-classification of all items (clears existing classifications)")
    parser.add_argument("--process-images", action="store_true",
                        help="Run the image processing pipeline")
    parser.add_argument("--image-root", type=str, default=str(Config.GOOGLE_IMAGES_DIR),
                        help="Root directory for images")
    parser.add_argument("--import-venues", action="store_true",
                        help="Import Just Eat venues from JSON into the database (needed before --classify or --process-images)")
    parser.add_argument("--import-taxonomy", action="store_true",
                        help="Import food taxonomy from Excel file into the database")

    args = parser.parse_args()
    Config.ensure_dirs()

    if args.import_taxonomy:
        from src.database.init_db import init_db, ingest_taxonomy
        logger.info("--- Importing Food Taxonomy into Database ---")
        try:
            init_db(db_path=args.db_path)
            ingest_taxonomy(str(Config.TAXONOMY_EXCEL_PATH), db_path=args.db_path)
        except Exception as e:
            logger.critical("FATAL ERROR during taxonomy import: %s", e)
            sys.exit(1)
        return

    if args.import_venues:
        from src.engine.venue_loader import import_venues_to_db
        from src.database.init_db import ingest_taxonomy
        logger.info("--- Importing Just Eat Venues into Database ---")
        try:
            import_venues_to_db(
                db_path=args.db_path,
                primary_path=str(Config.JUST_EAT_VENUES_PATH),
                split_dir=str(Config.JUST_EAT_VENUES_SPLIT_DIR),
            )
            ingest_taxonomy(str(Config.TAXONOMY_EXCEL_PATH), db_path=args.db_path)
        except Exception as e:
            logger.critical("FATAL ERROR during venue import: %s", e)
            sys.exit(1)
        return

    # Validate weights and threshold when running entity resolution
    if not args.classify and not args.process_images:
        validate_weights(args.weight_name, args.weight_geo)
        validate_threshold(args.threshold)

    if args.classify:
        from src.engine.classifier_orchestrator import ClassifierOrchestrator
        logger.info("--- Starting Classification Pipeline ---")
        try:
            orchestrator = ClassifierOrchestrator(db_path=args.db_path)
            orchestrator.run_classification(force_reclassify=args.force)
        except Exception as e:
            logger.critical("FATAL ERROR during classification: %s", e)
            sys.exit(1)
        return

    if args.process_images:
        from src.database.init_db import init_db
        from src.engine.image_processor import ImageProcessor
        init_db(db_path=args.db_path)
        logger.info("--- Starting Image Processing Pipeline ---")
        try:
            processor = ImageProcessor(db_path=args.db_path, image_root=args.image_root)
            cids = [d for d in os.listdir(args.image_root) if os.path.isdir(os.path.join(args.image_root, d))]
            for cid in cids:
                logger.info("Processing CID: %s", cid)
                result = processor.process_venue(cid)
                logger.info("Result: %s", result)
        except Exception as e:
            logger.critical("FATAL ERROR during image processing: %s", e)
            sys.exit(1)
        return

    logger.info("--- Entity Resolution Engine Execution ---")
    logger.info("Database: %s", args.db_path)
    logger.info("Google Venues: %s", args.google_venues_json)
    logger.info("Threshold: %s", args.threshold)
    logger.info("Weights: Name=%s, Geo=%s", args.weight_name, args.weight_geo)
    logger.info("------------------------------------------")

    try:
        matcher = Matcher(
            db_path=args.db_path,
            google_venues_path=args.google_venues_json,
            weight_name=args.weight_name,
            weight_geo=args.weight_geo
        )
        matcher.run_matching(threshold=args.threshold)
    except Exception as e:
        logger.critical("FATAL ERROR during execution: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
