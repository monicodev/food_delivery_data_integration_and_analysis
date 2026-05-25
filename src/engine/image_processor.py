import os
import csv
import time
import numpy as np
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import json
import logging
import requests
from typing import Optional, Dict, Any, List, Tuple
from src.config import Config
from src.database.init_db import get_session, ImageDetection

logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self, db_path: str = None,
                 image_root: str = None):
        self.db_path = db_path or str(Config.DB_PATH)
        self.image_root = image_root or str(Config.GOOGLE_IMAGES_DIR)

        try:
            self.device = "cpu"
            self.model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(self.device)
            self.processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            logger.info("ImageProcessor: CLIP model loaded successfully on CPU")
        except Exception as e:
            logger.error("ImageProcessor: Failed to load CLIP model: %s", e)
            self.model = None
            self.processor = None

        self._ensure_detections_table()
        self.food_categories = self._load_categories_from_taxonomy() or list(Config.FOOD_CATEGORIES)
        self.batch_size = Config.IMAGE_MAX_BATCH_SIZE
        self.min_width = Config.IMAGE_MIN_WIDTH
        self.min_height = Config.IMAGE_MIN_HEIGHT

    def _load_categories_from_taxonomy(self) -> Optional[List[str]]:
        try:
            session = get_session(self.db_path)
            try:
                from src.database.init_db import FoodTaxonomy
                rows = session.query(FoodTaxonomy.name).filter(FoodTaxonomy.name.isnot(None)).distinct().all()
                if rows:
                    names = [r[0].strip() for r in rows if r[0] and r[0].strip()]
                    if names:
                        logger.info("Loaded %d food categories from taxonomy", len(names))
                        return [n.lower() for n in names]
            finally:
                session.close()
        except Exception as e:
            logger.warning("Could not load taxonomy for image categories: %s", e)
        return None

    def _ensure_detections_table(self):
        from src.database.init_db import init_db
        init_db(db_path=self.db_path)

    def _load_pil_image(self, image_path: str) -> Optional[Image.Image]:
        """Load an image as a PIL RGB image. CLIPProcessor handles resize/crop/normalize."""
        try:
            img = Image.open(image_path).convert("RGB")
            return img
        except Exception as e:
            logger.error("Error loading image %s: %s", image_path, e)
            return None

    def _validate_image(self, pil_image: Image.Image, img_name: str) -> bool:
        """Validate image dimensions and format before CLIP inference."""
        try:
            if pil_image.mode not in ("RGB", "RGBA"):
                logger.warning("Skipping %s: unsupported mode %s", img_name, pil_image.mode)
                return False
            w, h = pil_image.size
            if w < self.min_width or h < self.min_height:
                logger.warning("Skipping %s: too small (%dx%d)", img_name, w, h)
                return False
            return True
        except Exception as e:
            logger.warning("Validation failed for %s: %s", img_name, e)
            return False

    def _batch_process_images(self, pil_images: List[Image.Image]) -> Optional[torch.Tensor]:
        if not self.model or not self.processor or not pil_images:
            return None
        try:
            inputs = self.processor(
                text=self.food_categories,
                images=pil_images,
                return_tensors="pt",
                padding=True
            ).to(self.device)

            outputs = self.model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1)
            return probs
        except Exception as e:
            logger.error("Error during batch inference: %s", e)
            return None

    @staticmethod
    def _build_predictions(probs: torch.Tensor, categories: List[str], top_k: int = 3) -> List[Dict[str, Any]]:
        top_k = min(top_k, len(categories))
        top_probs, top_indices = torch.topk(probs, k=top_k, dim=-1)
        return [
            {
                "category": categories[top_indices[i].item()],
                "confidence": round(top_probs[i].item(), 4)
            }
            for i in range(top_k)
        ]

    def evaluate(self, ground_truth: Dict[str, str] = None,
                 sample_limit: int = None) -> Dict[str, Any]:
        if not self.model or not self.processor:
            return {"error": "Model not loaded"}

        if ground_truth is None:
            return self._benchmark_latency(sample_limit)

        total = 0
        top1_correct = 0
        top3_correct = 0
        confidences = []
        latencies = []

        for cid, expected_label in ground_truth.items():
            venue_dir = os.path.join(self.image_root, cid)
            if not os.path.exists(venue_dir):
                continue

            batch_images = []
            batch_names = []
            for img_name in sorted(os.listdir(venue_dir)):
                if not img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    continue

                img_path = os.path.join(venue_dir, img_name)
                pil_img = self._load_pil_image(img_path)
                if pil_img is None:
                    continue
                if not self._validate_image(pil_img, img_name):
                    continue

                batch_images.append(pil_img)
                batch_names.append(img_name)

            for batch_start in range(0, len(batch_images), self.batch_size):
                batch_end = batch_start + self.batch_size
                batch_pil = batch_images[batch_start:batch_end]

                start = time.perf_counter()
                probs_batch = self._batch_process_images(batch_pil)
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)

                if probs_batch is None:
                    continue

                for idx in range(len(batch_pil)):
                    probs = probs_batch[idx]
                    predictions = self._build_predictions(probs, self.food_categories)
                    total += 1
                    confidences.append(predictions[0]["confidence"])

                    if predictions[0]["category"].lower() == expected_label.lower():
                        top1_correct += 1
                    top3_labels = [p["category"].lower() for p in predictions]
                    if expected_label.lower() in top3_labels:
                        top3_correct += 1

                    if sample_limit and total >= sample_limit:
                        break
                if sample_limit and total >= sample_limit:
                    break
            if sample_limit and total >= sample_limit:
                break

        if total == 0:
            return {"error": "No images evaluated"}

        return {
            "total_images": total,
            "top1_accuracy": round(top1_correct / total, 4),
            "top3_accuracy": round(top3_correct / total, 4),
            "mean_confidence": round(float(np.mean(confidences)), 4),
            "mean_latency_ms": round(float(np.mean(latencies)) * 1000, 2) if latencies else 0.0,
            "p95_latency_ms": round(float(np.percentile(latencies, 95)) * 1000, 2) if latencies else 0.0,
        }

    def _benchmark_latency(self, sample_limit: int = 10) -> Dict[str, Any]:
        latencies = []
        image_count = 0

        for cid in sorted(os.listdir(self.image_root)):
            venue_dir = os.path.join(self.image_root, cid)
            if not os.path.isdir(venue_dir):
                continue
            for img_name in sorted(os.listdir(venue_dir)):
                if not img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    continue
                img_path = os.path.join(venue_dir, img_name)
                pil_img = self._load_pil_image(img_path)
                if pil_img is None:
                    continue
                start = time.perf_counter()
                self._batch_process_images([pil_img])
                elapsed = time.perf_counter() - start
                latencies.append(elapsed)
                image_count += 1
                if sample_limit and image_count >= sample_limit:
                    break
            if sample_limit and image_count >= sample_limit:
                break

        if not latencies:
            return {"error": "No images found for latency benchmark"}

        return {
            "mode": "latency_benchmark",
            "images_processed": image_count,
            "mean_latency_ms": round(float(np.mean(latencies)) * 1000, 2),
            "p95_latency_ms": round(float(np.percentile(latencies, 95)) * 1000, 2),
            "min_latency_ms": round(float(np.min(latencies)) * 1000, 2),
            "max_latency_ms": round(float(np.max(latencies)) * 1000, 2),
        }

    def download_images(self, cid: str, photo_references: List[str],
                        api_key: str = None) -> List[str]:
        if api_key is None:
            api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        if not api_key:
            logger.warning("GOOGLE_PLACES_API_KEY not set. Cannot download images.")
            return []

        venue_dir = os.path.join(self.image_root, cid)
        os.makedirs(venue_dir, exist_ok=True)
        downloaded = []

        for idx, ref in enumerate(photo_references):
            url = (
                f"https://maps.googleapis.com/maps/api/place/photo"
                f"?maxwidth=800&photoreference={ref}&key={api_key}"
            )
            try:
                resp = requests.get(url, timeout=30, stream=True)
                if resp.status_code == 200:
                    ext = ".jpg"
                    fpath = os.path.join(venue_dir, f"{cid}_{idx}{ext}")
                    with open(fpath, "wb") as f:
                        for chunk in resp.iter_content(1024):
                            f.write(chunk)
                    downloaded.append(fpath)
                    logger.info("Downloaded image %d for CID %s", idx, cid)
                else:
                    logger.warning("Failed to download image %d for CID %s: HTTP %d",
                                   idx, cid, resp.status_code)
            except Exception as e:
                logger.error("Error downloading image %d for CID %s: %s", idx, cid, e)

        return downloaded

    def process_venue(self, google_cid: str) -> Dict[str, Any]:
        if not self.model or not self.processor:
            return {"error": "Model not loaded"}

        venue_dir = os.path.join(self.image_root, google_cid)
        if not os.path.exists(venue_dir):
            return {"error": f"No images found for CID: {google_cid}"}

        results = []
        all_images = []
        all_filenames = []

        for img_name in sorted(os.listdir(venue_dir)):
            if not img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue

            img_path = os.path.join(venue_dir, img_name)
            pil_img = self._load_pil_image(img_path)
            if pil_img is None:
                continue
            if not self._validate_image(pil_img, img_name):
                continue

            all_images.append(pil_img)
            all_filenames.append(img_name)

        # Process in capped batches to avoid OOM
        for batch_start in range(0, len(all_images), self.batch_size):
            batch_end = batch_start + self.batch_size
            batch_pil = all_images[batch_start:batch_end]
            batch_names = all_filenames[batch_start:batch_end]

            probs_tensor = self._batch_process_images(batch_pil)
            if probs_tensor is not None:
                for idx, img_name in enumerate(batch_names):
                    probs = probs_tensor[idx]
                    predictions = self._build_predictions(probs, self.food_categories)

                    results.append({
                        "image_file": img_name,
                        "predictions": predictions
                    })

                    self._persist_result(google_cid, predictions)

        output_data = {
            "google_cid": google_cid,
            "detections": results
        }

        self._save_to_json(google_cid, output_data)
        self._save_to_csv(google_cid, results)

        return output_data

    def _persist_result(self, google_cid: str, predictions: List[Dict[str, Any]]):
        try:
            session = get_session(self.db_path)
            try:
                for pred in predictions:
                    detection = ImageDetection(
                        google_cid=google_cid,
                        concept=pred["category"],
                        confidence=pred["confidence"]
                    )
                    session.add(detection)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.error("Database persistence failed: %s", e)
            finally:
                session.close()
        except Exception as e:
            logger.error("Database session creation failed: %s", e)

    def _save_to_json(self, google_cid: str, data: Dict[str, Any]):
        output_dir = str(Config.IMAGES_OUTPUT_DIR)
        venue_output_dir = os.path.join(output_dir, google_cid)
        os.makedirs(venue_output_dir, exist_ok=True)
        file_path = os.path.join(venue_output_dir, f"{google_cid}_results.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.info("Saved JSON results to %s", file_path)
        except Exception as e:
            logger.error("Failed to save JSON for %s: %s", google_cid, e)

    def _save_to_csv(self, google_cid: str, detections: List[Dict[str, Any]]):
        output_dir = str(Config.IMAGES_OUTPUT_DIR)
        venue_output_dir = os.path.join(output_dir, google_cid)
        os.makedirs(venue_output_dir, exist_ok=True)
        file_path = os.path.join(venue_output_dir, f"{google_cid}_results.csv")
        try:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["image_file", "top_category", "top_confidence",
                                 "second_category", "second_confidence",
                                 "third_category", "third_confidence"])
                for det in detections:
                    preds = det.get("predictions", [])
                    row = [det["image_file"]]
                    for i in range(3):
                        if i < len(preds):
                            row.extend([preds[i]["category"], preds[i]["confidence"]])
                        else:
                            row.extend(["", ""])
                    writer.writerow(row)
            logger.info("Saved CSV results to %s", file_path)
        except Exception as e:
            logger.error("Failed to save CSV for %s: %s", google_cid, e)


if __name__ == "__main__":
    processor = ImageProcessor()
    test_cid = "10320618957461533705"
    logger.info("Testing processing for %s...", test_cid)
    result = processor.process_venue(test_cid)
    if result and "error" not in result:
        logger.info("Processed %d images", len(result.get("detections", [])))
