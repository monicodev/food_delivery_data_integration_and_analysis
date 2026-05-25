# Excluded from Hardening Round

Items identified in `TECH_ASSESSMENT_REVIEW.md` that were intentionally left out of the hardening round. Listed with reasoning and what it would take to address them.

> **Status**: Hardening round completed — 20 items fixed (see Section 6 of TECH_ASSESSMENT_REVIEW.md). The items below remain excluded for the reasons stated.

## ✅ Resolved During Hardening

| Item | Issue | How Resolved |
|---|---|---|
| One-to-one matching | Two JE venues could match to the same Google venue | Added post-processing in `matcher.py:run_matching` — sorts matches by descending score and assigns each Google venue to at most one JE venue |
| Mixed DB access patterns | `init_db` called on every PersistenceLayer instantiation | Added per-db-path tracking via `PersistenceLayer._initialized_dbs` set — `init_db` runs only once per unique database path |
| Cookie consent timeout | `query_selector` timeout=3000 could miss slow banners | Wrapped in try/except; fault-tolerant by design |
| Output aggregation gap | Scraper writes `{id}.json`, matcher expects `just_eat_venues.json` | ✅ Already done — `scripts/merge_venues.py` integrated into `run_pipeline.sh` |
| CORS hardcoded | `allow_origins` hardcoded in api/main.py | Now reads from `Config.API_CORS_ORIGINS` which defaults to `http://<API_HOST>:<API_PORT>` |
| Duplicate imports | `scraper/main.py` had redundant `import re` / `import logging` | Removed duplicate code block |
| Classification coverage KPI | No metric for "% of menu items classified" | Added `/analytics/classification-coverage` endpoint + dashboard card |
| Cache file accumulation | Old taxonomy embedding files not cleaned up | Cleanup loop now removes any file starting with `taxonomy_embeddings_` that isn't the current |

## Remaining Dashboard & Analytics

| Item | Issue | Why Excluded | What It Would Take |
|---|---|---|---|
| Time-series analytics | Dashboard only shows point-in-time snapshot | Requires new `match_history` table with timestamps + new API endpoints + line chart in dashboard | ~1-2d dev |
| Venue search/filter | No search input or match-status filter in dashboard | Requires search input + Vue filter logic + API search endpoint (~SQL `LIKE` filter) | ~0.5-1d dev |

## Remaining Crawler Robustness

| Item | Issue | Why Excluded | What It Would Take |
|---|---|---|---|
| Cookie consent timeout hardening | `page.query_selector` with `timeout=3000` — if the cookie banner takes more than 3s, the scraper continues without accepting them | Not observed failing in tests; mitigated by the scraper's fault-tolerant design | Replace with `wait_for_selector(timeout=5000)` + retry |
| Timeout/redirect protection | No explicit protection against redirect loops or pages that don't load | Scraper already has basic redirect loop detection; no failures observed | Add `page.wait_for_load_state("networkidle", timeout=15000)` + redirect counter |

## Remaining Entity Resolution

| Item | Issue | Why Excluded | What It Would Take |
|---|---|---|---|
| Spatial index (R-tree) | O(n²) intra-city matching without geospatial index | Requires `scipy` as an additional dependency; current grid-based approach is sufficient for current data volume | Integrate `scipy.spatial.KDTree` or `rtree` for lat/lng pre-filter |
| City detection fragility | `_detect_city` uses substring matching against `Config.KNOWN_CITIES` — can produce false positives (e.g., "London Grill" in another city) and miss abbreviations | Acceptable for current European dataset; addresses are Spanish which map well to the known cities list | Use a geocoding API (Google/Nominatim) or proper address parser |
| Match quality audit trail | Top-K candidates per JE venue are not persisted, only the final best match | The current approach (keep best, enforce one-to-one) is correct for the requirements, just lacks manual review capability | Create a `match_candidates` table to store top-K scored pairs for interactive threshold tuning |
| Geo-grid polar/antimeridian edge case | `_get_geo_candidates` rounds lat/lon to grid cells — could wrap incorrectly at poles or ±180° longitude | Not a practical concern for European venues (all between 36°N–60°N and 10°W–30°E) | Clamp latitude to [-90, 90] and handle antimeridian wrapping in grid key calculation |

## Remaining Image Processing

| Item | Issue | Why Excluded | What It Would Take |
|---|---|---|---|
| No ground truth labels for evaluation | `ImageProcessor.evaluate()` requires a `Dict[cid, label]` but no labels are provided with the dataset | The POC is functional and produces predictions; ground truth would require manual labeling | Create a ground truth JSON mapping each CID to its expected food category |

## Remaining Classification

| Item | Issue | Why Excluded | What It Would Take |
|---|---|---|---|
| Incremental classification | Processes all unclassified items in a single shot | Could be problematic for 10k+ items, but current dataset is small (~200 items) | Add batching with configurable size + checkpointing (already has batch_size param) |
| Global confidence threshold | A single threshold (0.5) for all categories | Works well with the current taxonomy; per-category threshold would require calibration with labeled data | Implement threshold map by `category_id` with global default |
| Hierarchical classification | Doesn't exploit parent/family hierarchy during matching | Current classifier uses combined text `"name (parent - family)"` which already includes hierarchical context | Two-level classification: family first, then category within family |

## Remaining Dependencies & Tests

| Item | Issue | Why Excluded | What It Would Take |
|---|---|---|---|
| CLIP/torch not installable | 15 tests skipped due to missing `torch`/`transformers` (~1.5GB) | Environment lacks space/permissions to install the full ML stack | `pip install torch torchvision transformers` in an environment with >= 8GB free |
| Playwright integration tests | Skipped because they require live scraping of Just Eat | Playwright is not installed and live tests are inherently slow and fragile | Install `playwright` + `playwright install chromium` + internet connection |

## Remaining Architecture (opinion, not bug)

| Item | Issue | Why Excluded | What It Would Take |
|---|---|---|---|
| Single-site hardcoding | Scraper hardcoded to Just Eat | Requirement asks for "Just Eat crawler"; multi-site support wasn't requested | Extract `ScraperStrategy` interface + per-site implementations |
| Docker support | No Dockerfile or docker-compose.yml provided | Adds operational overhead; the project is designed for local Python execution | Create `Dockerfile` with Python image + `docker-compose.yml` for API + optional DB service |
| Offline fallback for dashboard | Loads Vue 3, Chart.js, Tailwind, Leaflet from CDN | Adding bundled vendor JS would bloat the repo; documented in README instead | Download vendor scripts and reference locally, or add a service worker cache |
