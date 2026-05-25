import json
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def merge_venues(input_dir: str, output_path: str):
    """Aggregate individual venue JSON files into a single dict keyed by venue ID."""
    input_dir = Path(input_dir)
    if not input_dir.exists():
        logger.warning("Input directory does not exist: %s", input_dir)
        return

    aggregated = {}
    loaded = 0
    skipped = 0

    for fpath in sorted(input_dir.iterdir()):
        if not fpath.suffix.lower() == ".json":
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Skipping %s: %s", fpath.name, e)
            skipped += 1
            continue

        venue_id = data.get("id") or fpath.stem
        if not venue_id:
            logger.warning("Skipping %s: no venue ID found", fpath.name)
            skipped += 1
            continue

        if venue_id in aggregated:
            logger.warning("Duplicate venue ID %s from %s, overwriting", venue_id, fpath.name)

        aggregated[venue_id] = data
        loaded += 1

    if not aggregated:
        logger.warning("No venues loaded from %s", input_dir)
        return

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, indent=4, ensure_ascii=False)

    logger.info("Merged %d venues (skipped %d) -> %s", loaded, skipped, output_path)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/merge_venues.py <input_dir> <output_path>")
        print("Example: python scripts/merge_venues.py source/output/venues source/just_eat_venues.json")
        sys.exit(1)

    merge_venues(sys.argv[1], sys.argv[2])
