# Project Writeup: Food Delivery Data Integration Pipeline

## 🎯 Scope Decision
**What was built:** I implemented a functional end-to-end pipeline including a web scraper, an entity resolution engine (hybrid string/geo), a keyword-based text classifier with fuzzy matching, an OCR menu extraction module (EasyOCR), and an interactive analytics dashboard.

**What was NOT built & Why:** 
- **Production-scale scraping**: I used Playwright in a single-threaded mode rather than a distributed cluster of scrapers to focus on the data extraction logic and schema validation required by the challenge.
- **Deep Learning for OCR**: EasyOCR (with PyTorch backend) is used for text extraction from menu images. It runs on CPU and downloads pre-trained models on first use. The ~2GB dependency is isolated as an optional `pip install easyocr`.
- **Advanced Auth/Security**: The API is intentionally open (CORS enabled) as the primary goal was data pipeline integrity rather than user management.

## 👤 Assumed User
A **Data Analyst** at a food delivery aggregator (e.g., Just Eat or UberEats). This person is responsible for monitoring brand consistency and verifying that local vendor menus are accurately represented across different regional platforms by cross-referencing internal data with Google Maps entries.

## 🛠️ Product/UX Decisions
1.  **Zero-Install Dashboard**: I chose to build the dashboard using **Vue.js via CDN** within a single HTML file. *Reasoning*: To ensure any reviewer can view the results immediately without running `npm install` or managing complex frontend build tools.
2.  **Dual-Output Scraper**: The scraper writes both JSON files and SQLite entries. *Reasoning*: This satisfies the challenge requirements for shareable artifacts while powering the downstream automated pipeline.
3.  **Keyword Matching with Fuzzy Fallback**: I used **RapidFuzz token_set_ratio** for menu item matching. *Reasoning*: OCR text is noisy with character errors; fuzzy token matching handles misspellings and partial reads better than exact or semantic matching for short item names.
4.  **Scalable API Design**: Using FastAPI with Pydantic models ensures that as the pipeline grows, the data contract remains rigid and verifiable.

## 🤖 How I used AI
- **Tools Used**: LLM Agents (for architecture design, code generation, and unit test creation) and Python/Bash execution environments.
- **How they helped**: The agents were instrumental in generating the boilerplate for FastAPI endpoints, writing complex SQL schema migrations, and generating the mathematical implementation of the Haversine formula.

Concrete AI Mistake & Resolution: During the implementation of the Scrapping process, a specialized agent entered an "Infinite Loop" hallucination. The agent repeatedly attempted to edit a file using an incorrect path, failing each time, yet its internal logs started reporting "Success" due to a corrupted context window.

The Correction: Instead of attempting to "fix" the stuck agent, I applied the following techniques:

1. Context Reset: I terminated the corrupted session to clear the hallucinated state.

2. Strategic Initialization: I initialized a new session, feeding it only the relevant "ground truth" (the current file state and the specific error logs).

## ⚖️ Technical Trade-offs
- **MVP vs. Production**: In a production environment, I would replace the local SQLite database with **PostgreSQL** for concurrency and use **Celery/Redis** to manage the scraping and classification tasks as asynchronous distributed workers.
- **Scraper simplicity over robustness**: The Playwright scraper prioritizes data extraction logic over anti-bot evasion. It does not use proxy rotation, browser fingerprint diversification, or distributed scraping. The JSON-LD extraction path handles most real-world pages; CSS selectors are a best-effort fallback and are known to be fragile on site redesigns.
- **City detection without geocoding**: The entity resolver uses word-boundary matching against a known city list rather than calling a geocoding API. This avoids adding external API dependencies and is sufficient for the European dataset where addresses follow predictable patterns.
- **OCR dependency weight**: EasyOCR pulls PyTorch (~2GB) which is heavy for a "laptop-friendly" POC. It was chosen over pytesseract (requires system binary) for pure pip-install portability, but the size tradeoff is real.
- **CDN dashboard as a deliberate zero-install choice**: Loading Vue 3, Chart.js, Tailwind, and Leaflet from CDN means the dashboard is a single HTML file that opens in any browser with no build step. The trade-off is that it requires internet connectivity and is not modular. A production version would migrate to Vite + TypeScript.
- **Section-based menu matching**: OCR-extracted items are matched against database items within the same menu section (e.g., "Drinks" items only compare to DB "Drinks" items). This improves accuracy but depends on section names being consistent between the physical menu and the database import.
- **Scraper-isolated pipeline design**: I opted to decouple the scraper from the downstream pipeline by providing a `--import-venues` flag that loads the pre-scraped JSON dataset directly into the database. This means the entity resolution, menu extraction, and dashboard can all be demonstrated without running the slow Playwright scraper. The 186MB `just_eat_venues.json` is split into 3 parts (`source/just_eat_venues_split/`) for GitHub compatibility, with a unified loader (`src/engine/venue_loader.py`) that transparently reads from either format.

## 🚀 What I’d do with 1 more month to differentiate MVP from product
If given one additional month of development time, I would:
1.  **OCR Accuracy Tuning**: Experiment with EasyOCR paragraph vs. line mode, custom post-processing regexes, and confidence threshold tuning per venue based on image quality.
2.  **Robust Scraper Infrastructure**: Implement proxy rotation, headless browser management via Docker, and advanced anti-bot evasion techniques.
3.  **Full TypeScript Frontend**: Transition the Vue.js dashboard from a single HTML file to a structured **Vue 3 + Vite + TypeScript** application with robust state management (Pinia).

## ⏳ Time Spent
**Total Estimated Time: ~9 Hours**
- Planning, Architecture and Setup: 1h
- Module 1 (Scraper): 1.5h
- Module 2 (ER Engine): 1h
- Module 3 (Classifier): 2h
- Module 4 (Image Processing): 2h
- Module 5 (Dashboard/API): 1h
- Testing & Documentation: 0.5h
