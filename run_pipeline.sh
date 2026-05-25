#!/usr/bin/env bash
#
# Pipeline Orchestration Script
# Runs the full Food Delivery Data Integration & Analysis pipeline end-to-end.
# Usage: bash run_pipeline.sh [--mock] [--locale {auto,eu,us}] [--skip-scrape] [--skip-classify] [--skip-images]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MOCK=""
FORCE=""
LOCALE=""
SKIP_SCRAPE=false
SKIP_CLASSIFY=false
SKIP_IMAGES=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mock) MOCK="--mock" ;;
        --locale) LOCALE="--locale $2"; shift ;;
        --force) FORCE="--force" ;;
        --skip-scrape) SKIP_SCRAPE=true ;;
        --skip-classify) SKIP_CLASSIFY=true ;;
        --skip-images) SKIP_IMAGES=true ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

echo "============================================"
echo "  Food Delivery Pipeline — Full Run"
echo "============================================"

# Step 0: Initialize database
echo ""
echo "[1/5] Initializing database..."
python3 src/database/init_db.py

# Step 1: Scrape
if [ "$SKIP_SCRAPE" = false ]; then
    echo ""
    echo "[2/5] Scraping Just Eat venues..."
    python3 src/scraper/main.py $MOCK $LOCALE
    echo ""
    echo "[2b/5] Merging venue JSONs into aggregated file..."
    python3 scripts/merge_venues.py source/output/venues source/just_eat_venues.json
else
    echo ""
    echo "[2/5] SKIPPED: Scraping"
fi

# Step 2: Entity Resolution
echo ""
echo "[3/5] Running Entity Resolution..."
python3 src/engine/main.py

# Step 3: Classification
if [ "$SKIP_CLASSIFY" = false ]; then
    echo ""
    echo "[4/5] Classifying menu items..."
    python3 src/engine/main.py --classify $FORCE
else
    echo ""
    echo "[4/5] SKIPPED: Classification"
fi

# Step 4: Image Processing
if [ "$SKIP_IMAGES" = false ]; then
    echo ""
    echo "[5/5] Processing images..."
    python3 src/engine/main.py --process-images
else
    echo ""
    echo "[5/5] SKIPPED: Image Processing"
fi

echo ""
echo "============================================"
echo "  Pipeline complete! Start the dashboard:"
echo "  python3 src/api/main.py"
echo "  Then open src/dashboard/index.html"
echo "============================================"
