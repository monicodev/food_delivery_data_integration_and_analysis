# AI Usage Report

This document outlines how Artificial Intelligence was utilized during the development of the "Food Delivery Data Integration & Analysis Pipeline" project.

## 🤖 Overview
AI tools (specifically LLMs) were used as a coding assistant to accelerate development, assist with complex algorithmic implementations, and improve documentation quality.

## 🛠️ Specific Use Cases

### 1. Software Architecture & Design
- **Pattern Identification**: Used AI to validate the suitability of the Layered Architecture for this specific multi-stage pipeline.
- **Refactoring Guidance**: Leveraged AI to identify opportunities for centralization (e.g., moving hardcoded paths to `src/config.py`).

### 2. Algorithm Implementation
- **Entity Resolution**: Assisted in drafting the Python implementation for the Haversine distance calculation and the exponential decay mathematical model.
- **Text Classification**: Used AI to verify the correct usage of `SentenceTransformer` embeddings and cosine similarity integration within the classification engine.

### 3. Code Generation & Unit Testing
- **Boilerplate Creation**: Generated initial Pydantic models (schemas) for the scraper and API layers.
- **Test Drafting**: Assisted in writing structure and edge-case scenarios for the `pytest` suite, ensuring coverage for name similarity and geospatial distance calculations.

### 4. Documentation & Error Handling
- **Documentation Enhancement**: Used AI to polish the `README.md` and ensure clear, technical documentation of the pipeline steps.
 
## 📋 Prompt Gallery

Below are representative prompts used during development, with notes on how they were adapted:

| Task | Prompt summary | How the output was adapted |
|---|---|---|
| Architecture | "Design a layered architecture for a food delivery data pipeline with scraping, entity resolution, classification, and visualization" | Used as scaffold; added explicit separation between ingestion/intelligence/persistence layers |
| Haversine formula | "Implement the Haversine distance formula in Python" | Verified math constants; added edge-case handling for None coordinates |
| Sentence-Transformer integration | "Show how to use SentenceTransformer with cosine similarity for multi-label classification" | Adapted to work with our taxonomy; added fallback keyword classifier for robustness |
| Pydantic models | "Define Pydantic V2 models for a Just Eat venue schema" | Cross-referenced against the actual just_eat_venue_example.json; added missing fields (brand, uniqueName, ghostStore) |
| FastAPI endpoints | "Create a FastAPI endpoint that returns match rate stats from SQLAlchemy" | Added error handling and Pydantic response models; adjusted queries to use func.count(distinct) for accuracy |
| Unit tests | "Write pytest cases for entity resolution edge cases" | Extended with real-world edge cases (None coords, unicode names, truncated JSON) |
| CSS selectors for scraping | "What CSS selectors does Just Eat use for menu items?" | Selectors were **not** taken from AI output — they were hand-crafted by inspecting the live site DOM |

**Key pattern**: AI was most effective for algorithms (Haversine, cosine similarity) and boilerplate (Pydantic models, FastAPI scaffolding). It was **least reliable** for site-specific scraping logic and taxonomy hierarchy — those were always manually verified against real data.

## ⚠️ Human Oversight & Verification
It is important to note that all AI-generated code and suggestions were rigorously reviewed, tested, and verified by a human engineer. Every line of code was checked for:
- **Correctness**: Ensuring mathematical models (Haversine) and logic are accurate.
- **Security**: Verifying no sensitive information or insecure practices were introduced.
- **Compliance**: Ensuring the implementation strictly adheres to the technical assessment requirements.

---
*This report is part of the project deliverables for the Food Delivery Data Integration & Analysis Challenge.*
