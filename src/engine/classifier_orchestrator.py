import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from src.config import Config
from src.database.init_db import get_session, FoodTaxonomy, MenuItem, Classification

logger = logging.getLogger(__name__)


class ClassifierOrchestrator:
    def __init__(self, db_path: str, confidence_threshold: float = 0.5):
        self.db_path = db_path
        self.confidence_threshold = confidence_threshold
        self._classifier = None

    @property
    def classifier(self):
        if self._classifier is None:
            try:
                from src.engine.classifier import TextClassifier
                self._classifier = TextClassifier()
            except Exception as e:
                logger.error("Failed to load TextClassifier: %s", e)
                self._classifier = None
        return self._classifier

    def _get_embedding_cache_path(self) -> str:
        taxonomy_path = Config.TAXONOMY_EXCEL_PATH
        embedding_dir = os.path.join(Config.OUTPUT_DIR, "embeddings")
        os.makedirs(embedding_dir, exist_ok=True)
        mtime = os.path.getmtime(taxonomy_path) if os.path.exists(taxonomy_path) else "0"
        safe_name = f"taxonomy_embeddings_{int(mtime)}"
        return {
            "embeddings": os.path.join(embedding_dir, f"{safe_name}.npy"),
            "ids": os.path.join(embedding_dir, f"{safe_name}_ids.json"),
        }

    def _load_or_compute_embeddings(self, taxonomy_ids: List[str], taxonomy_texts: List[str]) -> np.ndarray:
        cache = self._get_embedding_cache_path()
        embed_path = cache["embeddings"]
        ids_path = cache["ids"]

        if os.path.exists(embed_path) and os.path.exists(ids_path):
            try:
                with open(ids_path, 'r') as f:
                    cached_ids = json.load(f)
                if cached_ids == taxonomy_ids:
                    cached = np.load(embed_path)
                    if cached.shape[0] == len(taxonomy_ids):
                        logger.info("Loaded cached taxonomy embeddings (%d nodes)", len(taxonomy_ids))
                        return cached
            except Exception as e:
                logger.warning("Could not load cached embeddings: %s", e)

        logger.info("Computing taxonomy embeddings for %d nodes...", len(taxonomy_ids))
        clf = self.classifier
        if clf is None:
            raise RuntimeError("Classifier unavailable")

        embeddings = clf.encode(taxonomy_texts)

        try:
            np.save(embed_path, embeddings)
            with open(ids_path, 'w') as f:
                json.dump(taxonomy_ids, f)
            logger.info("Saved taxonomy embeddings to cache")

            # Clean old cache files for this taxonomy
            embedding_dir = os.path.dirname(embed_path)
            for fname in os.listdir(embedding_dir):
                if fname.startswith("taxonomy_embeddings_") and fname != os.path.basename(embed_path) and fname != os.path.basename(ids_path):
                    old_path = os.path.join(embedding_dir, fname)
                    try:
                        os.remove(old_path)
                        logger.debug("Removed old cache file: %s", old_path)
                    except OSError:
                        pass
        except Exception as e:
            logger.warning("Could not cache embeddings: %s", e)

        return embeddings

    @staticmethod
    def _word_matches(tax_word: str, item_words: set) -> bool:
        if tax_word in item_words:
            return True
        if len(tax_word) >= 4:
            for iw in item_words:
                if iw.startswith(tax_word) or tax_word.startswith(iw):
                    return True
        return False

    def _keyword_fallback_classify(self, item_text: str, taxonomy: List[Dict[str, Any]]) -> tuple:
        item_lower = item_text.lower()
        item_words = set(w.strip(".,!?()[]{}'\"") for w in item_lower.split())
        best_score = 0.0
        best_id = "unknown"
        for entry in taxonomy:
            tax_text = entry["text"].lower()
            tax_words = [w.strip(".,!?()[]{}'\"-") for w in tax_text.split() if w.strip(".,!?()[]{}'\"-")]
            if not tax_words:
                continue
            matches = sum(1 for tw in tax_words if self._word_matches(tw, item_words))
            score = matches / max(len(tax_words), 1)
            if score > best_score:
                best_score = score
                best_id = entry["id"]
        return best_id, best_score

    def _load_taxonomy(self) -> List[Dict[str, Any]]:
        taxonomy = []
        session = get_session(self.db_path)
        try:
            rows = session.query(FoodTaxonomy).all()
            for row in rows:
                name_val = row.name or ""
                parent_val = row.parent or ""
                family_val = row.family or ""

                if parent_val and family_val:
                    text = f"{name_val} ({parent_val} - {family_val})"
                elif parent_val:
                    text = f"{name_val} ({parent_val})"
                elif family_val:
                    text = f"{name_val} ({family_val})"
                else:
                    text = name_val

                taxonomy.append({
                    "id": row.category_uidentifier,
                    "text": text
                })
        except Exception as e:
            logger.error("Error loading taxonomy from DB: %s", e)
        finally:
            session.close()
        return taxonomy

    def _load_unclassified_items(self, force_reclassify: bool = False) -> List[Dict[str, Any]]:
        items = []
        session = get_session(self.db_path)
        try:
            if force_reclassify:
                rows = session.query(MenuItem).all()
            else:
                rows = (
                    session.query(MenuItem)
                    .outerjoin(Classification, MenuItem.id == Classification.menu_item_id)
                    .filter(Classification.id.is_(None))
                    .all()
                )
            for row in rows:
                desc = row.description if row.description else ""
                items.append({
                    "id": row.id,
                    "text": f"{row.name} {desc}".strip()
                })
        except Exception as e:
            logger.error("Error loading items for classification from DB: %s", e)
        finally:
            session.close()
        return items

    def _persist_classifications(self, results: List[Dict[str, Any]]):
        if not results:
            return
        session = get_session(self.db_path)
        try:
            for r in results:
                classification = Classification(
                    menu_item_id=r["menu_item_id"],
                    taxonomy_id=r["taxonomy_id"],
                    confidence=r["confidence"]
                )
                session.add(classification)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Error persisting classifications to DB: %s", e)
        finally:
            session.close()

    def _export_classifications_json(self, output_path: str):
        session = get_session(self.db_path)
        try:
            rows = (
                session.query(
                    MenuItem.name.label("item_name"),
                    MenuItem.description.label("item_description"),
                    FoodTaxonomy.name.label("category_name"),
                    FoodTaxonomy.parent.label("category_parent"),
                    FoodTaxonomy.family.label("category_family"),
                    Classification.confidence,
                )
                .join(Classification, Classification.menu_item_id == MenuItem.id)
                .join(FoodTaxonomy, Classification.taxonomy_id == FoodTaxonomy.category_uidentifier)
                .order_by(Classification.confidence.desc())
                .all()
            )
            export_data = [
                {
                    "item_name": r.item_name,
                    "item_description": r.item_description,
                    "category_name": r.category_name,
                    "category_parent": r.category_parent,
                    "category_family": r.category_family,
                    "confidence": r.confidence,
                }
                for r in rows
            ]
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=4, ensure_ascii=False)
            logger.info("Exported %d classifications to %s", len(export_data), output_path)
        except Exception as e:
            logger.error("Error exporting classifications: %s", e)
        finally:
            session.close()

    def evaluate(self, ground_truth: Dict[int, str]) -> Dict[str, float]:
        if not ground_truth:
            return {"error": "No ground truth provided"}
        session = get_session(self.db_path)
        try:
            rows = (
                session.query(Classification.menu_item_id, FoodTaxonomy.name)
                .join(FoodTaxonomy, Classification.taxonomy_id == FoodTaxonomy.category_uidentifier)
                .all()
            )
            predictions = {row.menu_item_id: row.name.lower() for row in rows}

            if not predictions:
                return {"error": "No classifications found to evaluate"}

            correct = 0
            incorrect = 0
            unclassified = 0
            all_labels = sorted(set(
                list(ground_truth.values()) + list(predictions.values())
            ))
            conf_matrix = {true: {pred: 0 for pred in all_labels} for true in all_labels}

            for item_id, true_label in ground_truth.items():
                predicted = predictions.get(item_id)
                true_lower = true_label.lower()
                pred_lower = predicted.lower() if predicted else "unknown"
                if predicted and pred_lower == true_lower:
                    correct += 1
                elif predicted:
                    incorrect += 1
                else:
                    unclassified += 1
                if predicted:
                    conf_matrix.setdefault(true_lower, {}).setdefault(pred_lower, 0)
                    conf_matrix[true_lower][pred_lower] += 1

            accuracy = correct / len(ground_truth) if ground_truth else 0.0

            return {
                "total_items": len(ground_truth),
                "classified_items": len(predictions),
                "correct": correct,
                "incorrect": incorrect,
                "unclassified": unclassified,
                "accuracy": round(accuracy, 4),
                "confusion_matrix": conf_matrix,
            }
        except Exception as e:
            logger.error("Error computing classification metrics: %s", e)
            return {"error": str(e)}
        finally:
            session.close()

    def run_classification(self, export_json: bool = True, force_reclassify: bool = False,
                            batch_size: int = 500):
        from src.database.init_db import init_db
        init_db(db_path=self.db_path)

        logger.info("--- Starting Classification Orchestration ---")

        taxonomy = self._load_taxonomy()
        if not taxonomy:
            logger.warning("No taxonomy found. Abort.")
            return

        if force_reclassify:
            logger.info("Force re-classification requested. Clearing existing classifications.")
            session = get_session(self.db_path)
            try:
                existing_count = session.query(Classification).count()
                logger.info("Backing up %d existing classifications (count only).", existing_count)
                session.query(Classification).delete()
                session.commit()
                logger.info("Cleared %d existing classifications.", existing_count)
            except Exception as e:
                session.rollback()
                logger.error("Failed to clear classifications: %s", e)
                logger.warning("Proceeding with re-classification without clearing (will skip existing).")
                force_reclassify = False
            finally:
                session.close()

        items = self._load_unclassified_items(force_reclassify=force_reclassify)
        if not items:
            logger.info("No unclassified items found. Everything is up to date.")
            return

        logger.info("Loaded %d taxonomy nodes and %d unclassified items.", len(taxonomy), len(items))

        taxonomy_ids = [t["id"] for t in taxonomy]
        taxonomy_texts = [t["text"] for t in taxonomy]

        use_semantic = self.classifier is not None
        if use_semantic:
            try:
                taxonomy_embeddings = self._load_or_compute_embeddings(taxonomy_ids, taxonomy_texts)
            except Exception as e:
                logger.warning("Semantic classification unavailable, falling back to keyword matching: %s", e)
                use_semantic = False

        results = []
        total_classified = 0
        logger.info("Classifying %d items in batches of %d using %s...",
                     len(items), batch_size, "semantic" if use_semantic else "keyword fallback")

        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start:batch_start + batch_size]
            batch_results = []
            for item in batch:
                if use_semantic:
                    try:
                        category_id, confidence = self.classifier.classify(
                            item["text"],
                            taxonomy_embeddings,
                            taxonomy_ids
                        )
                    except Exception as e:
                        logger.warning("Classification failed for item %s, using fallback: %s", item["id"], e)
                        category_id, confidence = self._keyword_fallback_classify(item["text"], taxonomy)
                else:
                    category_id, confidence = self._keyword_fallback_classify(item["text"], taxonomy)

                if confidence >= self.confidence_threshold:
                    batch_results.append({
                        "menu_item_id": item["id"],
                        "taxonomy_id": category_id,
                        "confidence": confidence
                    })

            # Persist after each batch to avoid data loss on crash
            if batch_results:
                self._persist_classifications(batch_results)
                total_classified += len(batch_results)
                logger.info("Batch %d/%d: classified %d items (cumulative: %d)",
                             batch_start // batch_size + 1,
                             (len(items) + batch_size - 1) // batch_size,
                             len(batch_results), total_classified)
            results.extend(batch_results)

        logger.info("Successfully classified %d items (threshold: %.2f).", total_classified, self.confidence_threshold)

        if export_json:
            output_dir = str(Config.OUTPUT_DIR)
            os.makedirs(output_dir, exist_ok=True)
            self._export_classifications_json(os.path.join(output_dir, "classifications.json"))

        logger.info("--- Classification Orchestration Complete ---")
