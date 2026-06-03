from __future__ import annotations

import os
import csv
import json
import logging
from typing import Optional, Dict, Any, List
from src.config import Config
from src.engine.menu_extractor import MenuExtractor

logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self, db_path: str = None,
                 image_root: str = None):
        self.db_path = db_path or str(Config.DB_PATH)
        self.image_root = image_root or str(Config.GOOGLE_IMAGES_DIR)
        self._extractor = MenuExtractor(db_path=self.db_path)

    def process_venue(self, google_cid: str) -> Dict[str, Any]:
        result = self._extractor.process_venue(google_cid)
        self._save_to_json(google_cid, result)
        self._save_to_csv(google_cid, result)
        return result

    def _save_to_json(self, google_cid: str, data: Dict[str, Any]):
        output_dir = str(Config.IMAGES_OUTPUT_DIR)
        venue_output_dir = os.path.join(output_dir, google_cid)
        os.makedirs(venue_output_dir, exist_ok=True)
        file_path = os.path.join(venue_output_dir, f"{google_cid}_results.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.info("Saved JSON results to %s", file_path)
        except Exception as e:
            logger.error("Failed to save JSON for %s: %s", google_cid, e)

    def _save_to_csv(self, google_cid: str, result: Dict[str, Any]):
        output_dir = str(Config.IMAGES_OUTPUT_DIR)
        venue_output_dir = os.path.join(output_dir, google_cid)
        os.makedirs(venue_output_dir, exist_ok=True)
        file_path = os.path.join(venue_output_dir, f"{google_cid}_results.csv")
        try:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["extracted_name", "extracted_price", "extracted_description",
                                 "db_name", "db_price", "db_description", "diff_type", "section"])
                for d in (result.get("diffs") or []):
                    writer.writerow([
                        d.get("extracted_name", ""),
                        d.get("extracted_price", ""),
                        d.get("extracted_description", ""),
                        d.get("db_name", ""),
                        d.get("db_price", ""),
                        d.get("db_description", ""),
                        d.get("diff_type", ""),
                        d.get("section", ""),
                    ])
            logger.info("Saved CSV results to %s", file_path)
        except Exception as e:
            logger.error("Failed to save CSV for %s: %s", google_cid, e)


if __name__ == "__main__":
    processor = ImageProcessor()
    test_cid = "10320618957461533705"
    logger.info("Testing processing for %s...", test_cid)
    result = processor.process_venue(test_cid)
    if result and "error" not in result:
        logger.info("Processed venue: %s", result.get("google_cid"))
