# Food Delivery Data Integration & Analysis Pipeline

An end-to-end data pipeline designed to scrape, match, classify, and visualize restaurant and menu information from Just Eat and Google Maps datasets.

## Overview
This project automates the integration of disparate food delivery datasets using a modern Python/FastAPI backend and a lightweight Vue.js dashboard. It features:
- **Web Scraping**: Automated extraction of Just Eat venue and menu data via Playwright.
- **Entity Resolution**: A hybrid algorithm matching Just Eat venues to Google Maps via name similarity (RapidFuzz with token-level comparison), geospatial proximity (Haversine + geo-grid pre-filtering), and address-based score boosting.
- **Text Classification**: Semantic mapping of menu items to a hierarchical food taxonomy using Sentence-Transformers.
- **Image Intelligence**: A CPU-optimized Vision POC using CLIP to identify food concepts in images.
- **Analytics Dashboard**: An interactive interface for on-demand KPI monitoring and visualization.

## Architecture
The pipeline follows a layered architecture:
1. **Ingestion Layer (`src/scraper`)**: Crawls Just Eat URLs and processes raw JSON data into a structured format.
2. **Intelligence Layer (`src/engine`)**: The core logic engine containing the Entity Resolution (ER) engine, Text Classifier, and Image Processor modules.
3. **Persistence Layer (`src/database` & `src/scraper/persistence.py`)**: Handles SQLite storage for venues, menu items, matches, and classifications.
4. **API Layer (`src/api`)**: A FastAPI-based REST API providing analytics endpoints (Match Rate, Venue Density, etc.) for the dashboard.
5. **Presentation Layer (`src/api/static`)**: A Vue.js powered single-page dashboard served directly by FastAPI at the root URL.

## Prerequisites
- **Python 3.12+**
- **pip** (Python package manager)
- A modern web browser (Chrome, Firefox, or Edge)

## Setup Instructions

### 1. Clone and Environment Preparation
Navigate to the project root and install the required dependencies:
```bash
# Install core dependencies (enough for entity resolution + keyword classification)
python3 -m pip install fastapi uvicorn sqlalchemy pandas openpyxl rapidfuzz scikit-learn python-dotenv

# Install ML dependencies only if running semantic classification or image processing
# python3 -m pip install sentence-transformers opencv-python pillow torch

# Install Playwright browsers for scraping (only if running the scraper)
# python3 -m playwright install chromium
```

**Note**: You can customize the pipeline behavior (e.g., database path, scraper mode) by copying `.env.example` to `.env` and adjusting values.


#### **(Optional) Scrape Fresh Data**
If you want to scrape Just Eat instead of using the bundled dataset:
```bash
python3 src/scraper/main.py
```


### 2. Import Data (Skip the Scraper)
The dataset (`2696 Just Eat venues`, `22991 Google venues`) is provided as JSON files. Import venues, menu items, and the food taxonomy into the database (this also initializes the database automatically):

```bash
# Import the venues in one go (~14s)
python3 src/engine/main.py --import-venues
```

```bash
# Import taxonomy:
python3 src/engine/main.py --import-taxonomy
```

### 3. Running the Pipeline (Step-by-Step)

#### **Step A: Entity Resolution**
Match Just Eat venues with Google Venues using the hybrid scoring engine (name similarity + geospatial proximity):
```bash
python3 src/engine/main.py
```
Progress is logged every ~50 venues during the matching process (~1 minute with existing matches, ~4 minutes from scratch). Results are written to `source/output/matches.json` and persisted in the database. Existing matches are re-checked with a single comparison per venue instead of a full geo-grid search for optimal performance.

#### **Step B: Menu Classification**
Classify menu items into the taxonomy hierarchy using keyword matching (fallback, no ML deps required):
```bash
python3 src/engine/main.py --classify
```
With ML dependencies installed (sentence-transformers + torch), uses semantic embeddings instead.

#### **Step C: Image Processing (POC)**
Process images in `source/google_images/` to identify food concepts:
```bash
python3 src/engine/main.py --process-images
```

### 4. Launching the Dashboard
1. **Start the FastAPI Server** (serves both the API and the dashboard):
   ```bash
   python3 src/api/main.py
   ```
2. **View the Dashboard**:
   Open [http://localhost:8000](http://localhost:8000) in your browser.

   The dashboard is served directly by FastAPI (no separate HTTP server needed).

The API exposes the following endpoints:
- `GET /health` — Database connectivity health check
- `GET /analytics/match-rate` — Match rate statistics (distinct venues)
- `GET /analytics/categories` — Top 10 classified food categories
- `GET /analytics/venue-density` — Venue and menu item counts
- `GET /analytics/classification-coverage` — Classification pipeline coverage (% of menu items classified)
- `GET /analytics/venues` — All venue coordinates with match status (for map)
- `GET /analytics/venue-images` — Matched JE venues with Google image folders and photo counts

The dashboard includes:
- **KPI cards** — Total Just Eat venues, matched Google venues, match rate, menu items, and classification coverage.
- **Top Food Categories chart** — Bar chart of the most classified categories.
- **Interactive venue map** — Leaflet.js map showing matched (green) and unmatched (red) venues with popup details.
- **System Status panel** — API connectivity, database status, and a **Refresh Data** button for manual updates (no auto-refresh).

### Git & Large Files
The original `source/just_eat_venues.json` (186MB) exceeds GitHub's recommended size. The dataset is split into 3 parts in `source/just_eat_venues_split/`. Before pushing to GitHub:

```bash
# Remove the original large file (keep only the splits)
rm source/just_eat_venues.json
```

The unified loader in `src/engine/venue_loader.py` transparently reads from the split directory when the single file is absent.

### 5. Running the Tests
Run the unit test suite to verify core logic:
```bash
python3 -m pytest tests/ -v
```
Tests are skipped when optional dependencies (sentence-transformers, OpenCV, Playwright, httpx) are not installed.

### 6. Advanced Features

#### Venue Import from JSON
Instead of running the scraper, import the pre-scraped Just Eat dataset directly:
```bash
python3 src/engine/main.py --import-venues
```
This reads from `source/just_eat_venues.json` or `source/just_eat_venues_split/` and populates the `venues_je`, `menu_items`, and `food_taxonomy` tables.

#### Taxonomy Import
Import the food taxonomy Excel file separately:
```bash
python3 src/engine/main.py --import-taxonomy
```

#### Image Evaluation Metrics
The `ImageProcessor` includes an evaluation mode that computes:
- **Top-1 / Top-3 Accuracy** when ground truth labels are provided
- **Mean confidence** across all predictions
- **Inference latency** (mean and P95 in milliseconds)

```python
from src.engine.image_processor import ImageProcessor
processor = ImageProcessor()
metrics = processor.evaluate(ground_truth={"<cid>": "pizza"})
```

A standalone latency benchmark runs when no ground truth is provided.

#### Image Download from Google Places
```python
processor.download_images("<cid>", ["<photo_reference>"], api_key="YOUR_KEY")
```
Requires `GOOGLE_PLACES_API_KEY` environment variable.

#### Re-classification

Running `--classify` without `--force` skips already-classified items (resumes from where it left off). Force re-classify all menu items:

```bash
python3 src/engine/main.py --classify --confidence-threshold 0.5 --force
```

#### Unmatched Venues Report
After entity resolution, unmatched Just Eat venue IDs are exported to `source/output/unmatched_venues.json`.

#### Entity Resolution Details
The hybrid match score is `S = (w_name * S_name) + (w_geo * S_geo) + address_boost`. With default weights (0.6 name, 0.4 geo) and threshold (0.70):

- Name similarity (`S_name`): Uses RapidFuzz with `token_set_ratio` and `token_sort_ratio` for **word-level comparison** (not character-level). Stop words (business types, legal forms, generic cuisine words) are filtered out before scoring. `partial_ratio` is avoided because it works at the character level, causing false positives like a single letter matching inside any word.
- Geospatial similarity (`S_geo`): Exponential decay of Haversine distance (`exp(-0.00035 * d)`). Uses a geo-grid pre-filter (0.05° cells, ~5.6km) with a 0.02° distance threshold (~2km) to reduce the candidate pool.
- Address boost: `+0.15` when street number and name match, `+0.08` when number alone matches.

A perfect name match (`S_name = 1.0`) with missing coordinates gives `S = 0.60` — **below** the threshold.
A perfect name match at the same location gives `S = 1.0` — confident match.

Adjust `--threshold` lower if you want looser matching, or tune `--weight-name` / `--weight-geo`.

### Pipeline Orchestration
Use the pipeline script for end-to-end execution:
```bash
bash run_pipeline.sh --mock           # Full pipeline with mock scraping
bash run_pipeline.sh --skip-scrape    # Resume from entity resolution
bash run_pipeline.sh --skip-classify  # Skip text classification
bash run_pipeline.sh --skip-images    # Skip image processing
```

### 7. Standalone Utilities

#### Merge Venue JSONs
After scraping, aggregate individual venue files into the format expected by the matcher:
```bash
python3 scripts/merge_venues.py source/output/venues source/just_eat_venues.json
```
This is called automatically by `run_pipeline.sh` after the scrape step.

#### Verify Excel Columns
Check the taxonomy Excel file columns:
```bash
python3 scripts/check_columns.py
```

### 8. Output Data
Pipeline outputs are written to:
- **Entity resolution matches**: `source/output/matches.json`
- **Unmatched venue report**: `source/output/unmatched_venues.json`
- **Classifications**: `source/output/classifications.json` (includes Name, Parent, Family)
- **Image detections**: `source/output/images/{cid}/{cid}_results.json` and `source/output/images/{cid}/{cid}_results.csv`

## Project Structure
- `source/`: Source data files (`google_venues.json`, `just_eat_venues_split/`) and processed output.
- `source/just_eat_venues_split/`: Just Eat venues dataset split into 3 parts for GitHub compatibility.
- `src/api/`: FastAPI backend and analytics endpoints.
- `src/database/`: Database initialization and schema management (SQLAlchemy models).
- `src/api/static/`: Vue.js dashboard frontend (served at the API root).
- `src/engine/`: The "intelligence" layer (ER, Classifier, Image Processor, Venue Loader).
- `src/engine/venue_loader.py`: Unified loader for single-file or split JSON directories.
- `src/scraper/`: Web scraping module (Playwright-based crawler).
- `src/scripts/`: Utility scripts (e.g., `split_venues.py` to split large JSON files).
- `tests/`: Automated unit tests for all modules (170+ tests).
- `screenshots/`: Dashboard screenshots (add your own after running).

## Known Limitations

- **Scraper requires explicit URLs**: Venue URLs must be provided in `source/just_eat_urls.json`. The scraper does not discover venues by city or search term.
- **CSS selectors are fragile**: The primary extraction path uses JSON-LD structured data. CSS selectors are a fallback and may break on site redesigns.
- **Single-threaded scraping**: Venues are processed sequentially with rate limiting (~5-10s per venue). No parallel or distributed scraping.
- **City detection uses a known list**: The matcher identifies cities by word-boundary matching against `Config.KNOWN_CITIES` (31 European cities). Extend this list for venues outside those cities.
- **torch + transformers are heavy (~1.5GB)**: Listed as optional dependencies (`pip install .[ml]`). Entity resolution and keyword classification work without them — lazy imports prevent import errors when torch is missing.
- **Dashboard requires internet**: Vue 3, Chart.js, Tailwind, and Leaflet are loaded from CDN. No offline fallback.
- **No ground truth for image evaluation**: The image processor produces predictions and latency benchmarks, but accuracy metrics require manually-provided labels.
- **Only the best match is persisted**: Entity resolution computes top candidates internally, but only the single best match per venue is stored (no audit trail for manual threshold tuning).
- **SQLite, not PostgreSQL**: Suitable for single-user POC use. Concurrent access would require PostgreSQL.
- **No authentication on the API**: CORS is open. Production deployment should add API key or JWT auth.

## Environment Variables
Copy `.env.example` to `.env` and configure:
- `DATABASE_NAME` — SQLite database filename (default: `food_delivery.db`)
- `SCRAPER_USE_MOCK` — Set to `True` to skip live scraping
- `SCRAPER_USER_AGENT` — Custom user agent string
- `SCRAPER_RATE_LIMIT_DELAY` — Seconds between requests (default: 3)
- `SCRAPER_MAX_RETRIES` — Retry attempts per URL (default: 3)
- `SCRAPER_RETRY_BASE_DELAY` — Base seconds for exponential backoff (default: 5)
- `API_HOST` / `API_PORT` — Backend server configuration
- `API_CORS_ORIGINS` — Comma-separated list of allowed CORS origins (default: derived from API_HOST and API_PORT)
