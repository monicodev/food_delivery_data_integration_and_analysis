# Project Writeup: Food Delivery Data Integration Pipeline

## 🎯 Scope Decision
**What was built:** I implemented a functional end-to-end pipeline including a web scraper, an entity resolution engine (hybrid string/geo), a semantic text classifier (Sentence-Transformers), a lightweight vision POC (CLIP), and an interactive analytics dashboard.

**What was NOT built & Why:** 
- **Production-scale scraping**: I used Playwright in a single-threaded mode rather than a distributed cluster of scrapers to focus on the data extraction logic and schema validation required by the challenge.
- **Heavy Deep Learning**: I avoided heavy GPU-dependent models (like YOLOv8) for image processing, opting instead for CLIP embeddings to ensure the "laptop-friendly" requirement was met and that the system remains portable.
- **Advanced Auth/Security**: The API is intentionally open (CORS enabled) as the primary goal was data pipeline integrity rather than user management.

## 👤 Assumed User
A **Data Analyst** at a food delivery aggregator (e.g., Just Eat or UberEats). This person is responsible for monitoring brand consistency and verifying that local vendor menus are accurately represented across different regional platforms by cross-referencing internal data with Google Maps entries.

## 🛠️ Product/UX Decisions
1.  **Zero-Install Dashboard**: I chose to build the dashboard using **Vue.js via CDN** within a single HTML file. *Reasoning*: To ensure any reviewer can view the results immediately without running `npm install` or managing complex frontend build tools.
2.  **Dual-Output Scraper**: The scraper writes both JSON files and SQLite entries. *Reasoning*: This satisfies the challenge requirements for shareable artifacts while powering the downstream automated pipeline.
3.  **Semantic over Keyword Matching**: I used **Sentence-Transformers** instead of simple keyword matching for classification. *Reasoning*: Food descriptions are highly variable (e.g., "spicy meat" vs "chili beef"); semantic embeddings provide much higher precision in mapping to a taxonomy.
4.  **Scalable API Design**: Using FastAPI with Pydantic models ensures that as the pipeline grows, the data contract remains rigid and verifiable.

## 🤖 How I used AI
- **Tools Used**: LLM Agents (for architecture design, code generation, and unit test creation) and Python/Bash execution environments.
- **How they helped**: The agents were instrumental in generating the boilerplate for FastAPI endpoints, writing complex SQL schema migrations, and generating the mathematical implementation of the Haversine formula.
- **When I needed to override**: I had to manually intervene when the agent attempted to implement a "flat" classification table that ignored the `parent/family` hierarchy required by the challenge specification.
- **A concrete AI mistake**: During the Image Processing phase, the agent generated test code that assumed `cv2` (OpenCV) was already present in the environment. This caused the test suite to crash with a `ModuleNotFoundError`. I corrected this by manually executing the installation of `opencv-python` and `Pillow` via `pip`.

## ⚖️ Technical Trade-offs
- **MVP vs. Production**: In a production environment, I would replace the local SQLite database with **PostgreSQL** for concurrency and use **Celery/Redis** to manage the scraping and classification tasks as asynchronous distributed workers.
- **Scraper simplicity over robustness**: The Playwright scraper prioritizes data extraction logic over anti-bot evasion. It does not use proxy rotation, browser fingerprint diversification, or distributed scraping. The JSON-LD extraction path handles most real-world pages; CSS selectors are a best-effort fallback and are known to be fragile on site redesigns.
- **City detection without geocoding**: The entity resolver uses word-boundary matching against a known city list rather than calling a geocoding API. This avoids adding external API dependencies and is sufficient for the European dataset where addresses follow predictable patterns.
- **Single confidence threshold**: The classifier applies a uniform 0.5 confidence threshold across all taxonomy categories. Per-category thresholds would improve accuracy for ambiguous food types but require calibrated labeled data not available in this scope.
- **Inference Latency**: While CLIP is efficient on CPU, a high-traffic production API would move the Vision and NLP inference to a dedicated GPU-accelerated microservice (e.g., NVIDIA Triton).
- **No ground truth for image evaluation**: The image processor produces predictions and latency metrics, but accuracy evaluation requires manually labeled ground truth for each CID. This was scoped out as it represents dataset curation, not pipeline engineering.
- **CDN dashboard as a deliberate zero-install choice**: Loading Vue 3, Chart.js, Tailwind, and Leaflet from CDN means the dashboard is a single HTML file that opens in any browser with no build step. The trade-off is that it requires internet connectivity and is not modular. A production version would migrate to Vite + TypeScript.
- **Scraper-isolated pipeline design**: I opted to decouple the scraper from the downstream pipeline by providing a `--import-venues` flag that loads the pre-scraped JSON dataset directly into the database. This means the entity resolution, classification, and dashboard can all be demonstrated without running the slow Playwright scraper. The 186MB `just_eat_venues.json` is split into 3 parts (`source/just_eat_venues_split/`) for GitHub compatibility, with a unified loader (`src/engine/venue_loader.py`) that transparently reads from either format.
- **Lazy import architecture for ML dependencies**: Rather than requiring all users to install torch/sentence-transformers/opencv, the engine uses lazy imports so that entity resolution and keyword-based classification work with zero heavy dependencies. Semantic classification and image processing only surface their import errors when those flags are explicitly used, and even they fall back gracefully (keyword matching for classify, no-op for process-images).

## 🚀 What I’d do with 1 more month to differentiate MVP from product
If given one additional month of development time, I would:
1.  **Implement Active Learning**: Create a "human-in-the-loop" interface in the dashboard where analysts can flag incorrect matches, which then triggers an automated retraining/fine-tuning of the ER and Classification models.
2.  **Robust Scraper Infrastructure**: Implement proxy rotation, headless browser management via Docker, and advanced anti-bot evasion techniques.
3.	**Full TypeScript Frontend**: Transition the Vue.js dashboard from a single HTML file to a structured **Vue 3 + Vite + TypeScript** application with robust state management (Pinia).

## ⏳ Time Spent
**Total Estimated Time: ~12 Hours**
- Planning & Architecture: 2h
- Module 1 (DB/Setup): 1h
- Module 	2 (Scraper): 2.5h
- Module 3 (ER Engine): 2h
- Module 4 (Classifier): 1.5h
- Module 5 (Image Processing): 1.5h
- Module 6 (Dashboard/API): 1.5h
- Testing & Documentation: 0.5h
