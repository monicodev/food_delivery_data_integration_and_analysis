import os
import json
import logging
import unicodedata
from typing import List, Dict, Any
from sqlalchemy import text
from src.config import Config
from src.database.init_db import get_session, FoodTaxonomy, MenuItem, Classification

logger = logging.getLogger(__name__)


def _norm(word: str) -> str:
    return unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode('ascii')


ALIASES = {
    "pollo": "chicken",
    "cerveza": "beer",
    "hamburguesa": "burger",
    "queso": "cheese",
    "ensalada": "salads",
    "patatas": "fries",
    "patata": "fries",
    "atún": "tuna",
    "atun": "tuna",
    "zumo": "juice",
    "ternera": "beef",
    "bocadillo": "sandwich",
    "refresco": "soft drinks",
    "cola": "soft drinks",
    "coca": "soft drinks",
    "fanta": "soft drinks",
    "naranja": "fruit",
    "limón": "fruit",
    "limon": "fruit",
    "alitas": "chicken",
    "costillas": "pork",
    "cerdo": "pork",
    "conejo": "rabbit",
    "salsa": "sauces",
    "arroz": "paella",
    "fruta": "fruit",
    "legumbres": "legumes",
    "helado": "ice cream",
    "pizza": "pizza",
    "sopa": "vegetable soups and creams",
    "crema": "vegetable soups and creams",
    "verduras": "vegetable soups and creams",
}


class ClassifierOrchestrator:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _build_alias_map(self, taxonomy: List[Dict[str, Any]]) -> Dict[str, str]:
        name_to_id = {t["text"].lower(): t["id"] for t in taxonomy}
        alias_map = {}
        for alias, category_name in ALIASES.items():
            key = category_name.lower()
            if key in name_to_id:
                alias_map[_norm(alias)] = name_to_id[key]
        return alias_map

    @staticmethod
    def _word_matches(tax_word: str, item_words: set) -> bool:
        if tax_word in item_words:
            return True
        import unicodedata
        tax_norm = unicodedata.normalize('NFKD', tax_word).encode('ascii', 'ignore').decode('ascii')
        for iw in item_words:
            iw_norm = unicodedata.normalize('NFKD', iw).encode('ascii', 'ignore').decode('ascii')
            if tax_norm == iw_norm:
                return True
            if len(tax_word) >= 4 and tax_norm in iw_norm:
                return True
        if len(tax_word) >= 4:
            from rapidfuzz import fuzz
            for iw in item_words:
                if fuzz.ratio(tax_word, iw) >= 80:
                    return True
        return False

    def _classify_item(self, item_text: str, taxonomy: List[Dict[str, Any]],
                        alias_map: Dict[str, str] = None) -> tuple:
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

        if best_score < 1.0 and alias_map:
            for iw in item_words:
                iw_norm = _norm(iw)
                if iw_norm in alias_map:
                    return alias_map[iw_norm], 1.0

        return best_id, best_score

    def _load_taxonomy(self) -> List[Dict[str, Any]]:
        taxonomy = []
        session = get_session(self.db_path)
        try:
            rows = session.query(FoodTaxonomy).all()
            for row in rows:
                name_val = row.name or ""
                taxonomy.append({
                    "id": row.category_uidentifier,
                    "text": name_val
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
        alias_map = self._build_alias_map(taxonomy)
        logger.info("Loaded %d aliases.", len(alias_map))

        results = []
        total_classified = 0
        logger.info("Classifying %d items in batches of %d using keyword matching...",
                     len(items), batch_size)

        num_batches = (len(items) + batch_size - 1) // batch_size
        log_interval = max(1, num_batches // 50)
        import time
        t_start = time.time()
        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start:batch_start + batch_size]
            batch_results = []

            for item in batch:
                category_id, confidence = self._classify_item(item["text"], taxonomy, alias_map)
                if confidence >= 1.0:
                    batch_results.append({
                        "menu_item_id": item["id"],
                        "taxonomy_id": category_id,
                        "confidence": confidence
                    })

            if batch_results:
                self._persist_classifications(batch_results)
                total_classified += len(batch_results)

            results.extend(batch_results)

            batch_num = batch_start // batch_size + 1
            if batch_num % log_interval == 0:
                elapsed = time.time() - t_start
                rate = batch_num / elapsed if elapsed > 0 else 0
                remaining = (num_batches - batch_num) / rate if rate > 0 else 0
                logger.info(
                    "Progress: %d/%d batches (%.0f%%) — %d classified — "
                    "elapsed %dm%02ds — ETA %dm%02ds",
                    batch_num, num_batches, batch_num / num_batches * 100,
                    total_classified,
                    int(elapsed // 60), int(elapsed % 60),
                    int(remaining // 60), int(remaining % 60),
                )

        logger.info("Successfully classified %d items.", total_classified)

        if export_json:
            output_dir = str(Config.OUTPUT_DIR)
            os.makedirs(output_dir, exist_ok=True)
            self._export_classifications_json(os.path.join(output_dir, "classifications.json"))

        logger.info("--- Classification Orchestration Complete ---")
