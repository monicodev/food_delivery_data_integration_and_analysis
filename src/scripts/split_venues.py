import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import Config


def split_venues(num_parts: int = 3):
    src = str(Config.JUST_EAT_VENUES_PATH)
    dst_dir = str(Config.SOURCE_DIR / "just_eat_venues_split")

    if not os.path.exists(src):
        print(f"Source not found: {src}")
        return

    os.makedirs(dst_dir, exist_ok=True)

    print(f"Loading {src}...")
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    keys = sorted(data.keys())
    total = len(keys)
    chunk_size = math.ceil(total / num_parts)

    print(f"Splitting {total} venues into {num_parts} parts ({chunk_size} per part)...")

    for i in range(num_parts):
        start = i * chunk_size
        end = min(start + chunk_size, total)
        chunk_keys = keys[start:end]
        chunk = {k: data[k] for k in chunk_keys}
        part_path = os.path.join(dst_dir, f"part_{i + 1}.json")
        with open(part_path, "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False)
        size_mb = os.path.getsize(part_path) / (1024 * 1024)
        print(f"  {part_path}: {len(chunk)} venues, {size_mb:.1f} MB")

    print(f"\nDone. Files in {dst_dir}/")
    print(f"Original file size: {os.path.getsize(src) / (1024 * 1024):.1f} MB")
    print(f"You can now remove the original: rm '{src}'")


if __name__ == "__main__":
    split_venues(num_parts=3)
