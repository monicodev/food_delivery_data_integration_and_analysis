"""
Menu Extractor — EasyOCR + parsing + matching + diff for venue menu images.
"""

from __future__ import annotations

import os
import re
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from src.config import Config

# Required libraries for image rotation and preprocessing
import cv2
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

try:
    import easyocr
    _HAS_EASYOCR = True
except ImportError:
    easyocr = None
    _HAS_EASYOCR = False


def _fix_ssl():
    """Ensure SSL certificates are reachable for model downloads."""
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        for p in ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
            if os.path.exists(p):
                os.environ.setdefault("SSL_CERT_FILE", p)
                break


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_cid_to_place_id() -> Dict[str, str]:
    path = os.path.join(str(Config.SOURCE_DIR), "google_venues.json")
    if not os.path.exists(path):
        logger.warning("google_venues.json not found at %s", path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mapping: Dict[str, str] = {}
        cid_re = re.compile(r"cid=(\d+)")
        for v in data:
            place_id = v.get("googlePlaceId")
            url = v.get("googleMapsUrl", "")
            m = cid_re.search(url)
            if place_id and m:
                mapping[m.group(1)] = place_id
        logger.info("Loaded %d CID → place_id mappings", len(mapping))
        return mapping
    except Exception as e:
        logger.error("Failed to load google_venues.json: %s", e)
        return {}


CID_TO_PLACE_ID = _load_cid_to_place_id()

# ── EasyOCR reader (lazy singleton) ──────────────────────────────────────────

_READER = None

def _get_reader():
    global _READER
    if _READER is None and _HAS_EASYOCR:
        _fix_ssl()
        logger.info("Initializing EasyOCR reader...")
        _READER = easyocr.Reader(["en", "es"], gpu=False)
    return _READER


# ── Intelligent Auto-Rotation and Preprocessing ──────────────────────────────

def _rotate_image_if_needed(image_path: str) -> np.ndarray:
    """
    Safely detects the optimal image orientation.
    Only applies rotations if the current readability is poor and 
    another orientation drastically improves text detection.
    """
    # 1. Attempt to correct using EXIF camera metadata
    try:
        img_pil = Image.open(image_path)
        img_pil = ImageOps.exif_transpose(img_pil)
        img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    except Exception:
        img = cv2.imread(image_path)

    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    reader = _get_reader()
    if not reader:
        return img

    # 2. Sample the center of the image to evaluate readability quickly
    h, w = img.shape[:2]
    crop_y1, crop_y2 = int(h * 0.25), int(h * 0.75)
    crop_x1, crop_x2 = int(w * 0.25), int(w * 0.75)
    
    def _get_orientation_score(image_array: np.ndarray) -> int:
        sample = image_array[crop_y1:crop_y2, crop_x1:crop_x2]
        detected_texts = reader.readtext(sample, detail=0)
        # Count words that look like real menu text (alphanumeric > 2 chars)
        return sum(1 for text in detected_texts if len(text) >= 3 and not re.match(r'^[^a-zA-Z0-9]+$', text))

    score_original = _get_orientation_score(img)
    logger.info(f"Original readability score for {os.path.basename(image_path)}: {score_original}")

    # Avoid false positives: if current orientation is good enough, do not rotate
    if score_original >= 8:
        logger.info("Original image is readable. Keeping current orientation.")
        return img

    # 3. Evaluate alternative rotations
    img_90 = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    img_270 = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    img_180 = cv2.rotate(img, cv2.ROTATE_180)

    # Re-calculate dimensions for rotated samples
    h_rot, w_rot = img_90.shape[:2]
    r_crop_y1, r_crop_y2 = int(h_rot * 0.25), int(h_rot * 0.75)
    r_crop_x1, r_crop_x2 = int(w_rot * 0.25), int(w_rot * 0.75)

    def _get_rot_orientation_score(image_array: np.ndarray) -> int:
        sample = image_array[r_crop_y1:r_crop_y2, r_crop_x1:r_crop_x2]
        detected_texts = reader.readtext(sample, detail=0)
        return sum(1 for text in detected_texts if len(text) >= 3 and not re.match(r'^[^a-zA-Z0-9]+$', text))

    score_90 = _get_rot_orientation_score(img_90)
    score_270 = _get_rot_orientation_score(img_270)
    score_180 = _get_orientation_score(img_180) 

    scores = {
        "original": score_original,
        "90": score_90,
        "270": score_270,
        "180": score_180
    }
    
    best_orientation = max(scores, key=scores.get)
    
    # 4. Apply rotation only if it improves readability by a significant margin
    if best_orientation == "original" or scores[best_orientation] <= score_original + 3:
        logger.info("No rotation significantly improves text readability. Keeping original.")
        return img
    
    if best_orientation == "90":
        logger.info(f"Rotating 90° (CW). Score: {score_90} vs Original: {score_original}")
        return img_90
    elif best_orientation == "270":
        logger.info(f"Rotating 270° (CCW). Score: {score_270} vs Original: {score_original}")
        return img_270
    elif best_orientation == "180":
        logger.info(f"Rotating 180° (Upside down). Score: {score_180} vs Original: {score_original}")
        return img_180

    return img


# ── OCR ──────────────────────────────────────────────────────────────────────

def ocr_image(image_path: str) -> Optional[str]:
    """Extract raw text from an image via EasyOCR with prior orientation correction."""
    if not _HAS_EASYOCR:
        logger.warning("EasyOCR not installed. Run: pip install easyocr")
        return None
    reader = _get_reader()
    if not reader:
        return None
    try:
        corrected_img = _rotate_image_if_needed(image_path)
        
        # EasyOCR can process OpenCV arrays (numpy ndarray) directly
        results = reader.readtext(corrected_img, paragraph=False)
        if not results:
            return None
        lines = []
        for entry in results:
            if len(entry) == 3:
                _, text, conf = entry
            else:
                text, conf = entry
            if isinstance(text, list):
                text = " ".join(text)
            text = text.strip()
            if text and conf >= 0.3:
                lines.append(text)
        return "\n".join(lines) if lines else None
    except Exception as e:
        logger.error("EasyOCR failed for %s: %s", image_path, e)
        return None


# ── Parsing ──────────────────────────────────────────────────────────────────

_PRICE_RE = re.compile(
    r"(?P<price>\d{1,3}[.,]\d{2})\s*(?:€|EUR|euro|lata)?|(?:€|EUR|euro)\s*(?P<price2>\d{1,3}[.,]\d{2})",
    re.IGNORECASE,
)

_ITEM_NUMBER_RE = re.compile(r"^\d+[\s.-]+")
_SECTION_HEADER_RE = re.compile(
    r"^(ENSALADAS|POSTRES|PIZZAS|COMPLEMENTOS|BEBIDAS|ENTRANTS|ENTRANTES|SEGONS|SEGUNDOS|PLATES|COMBINADOS|ESPECIALITAT|POSTRES|DRINKS|CURRIES|PIZZES)$",
    re.IGNORECASE
)


def _normalize_price(text: str) -> Optional[float]:
    if not text:
        return None
    cleaned = re.sub(r"[^\d.,]", "", text).strip()
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except (ValueError, TypeError):
        return None


def _extract_price(line: str) -> Optional[float]:
    match = _PRICE_RE.search(line)
    if not match:
        return None
    val = match.group("price") or match.group("price2")
    return _normalize_price(val)


def parse_menu_text(raw: str) -> List[Dict[str, Any]]:
    lines = [ln.strip() for ln in raw.split("\n") if ln.strip()]
    candidates: List[Dict[str, Any]] = []
    
    current_section = "general"
    current_item: Optional[Dict[str, Any]] = None
    
    for line in lines:
        if _SECTION_HEADER_RE.match(line) or (line.isupper() and len(line) < 30 and not _PRICE_RE.search(line)):
            if current_item and current_item["name"]:
                candidates.append(current_item)
                current_item = None
            current_section = line.strip().lower()
            continue

        price = _extract_price(line)
        cleaned_line = _PRICE_RE.sub("", line).strip().rstrip(".,-–— \t")
        
        is_numbered = _ITEM_NUMBER_RE.match(cleaned_line)
        if is_numbered:
            cleaned_line = _ITEM_NUMBER_RE.sub("", cleaned_line).strip()

        if is_numbered or (cleaned_line.isupper() and len(cleaned_line) > 3 and len(cleaned_line) < 40) or not current_item:
            if current_item and current_item["name"]:
                candidates.append(current_item)
            
            current_item = {
                "name": cleaned_line,
                "price": price,
                "description": "",
                "section": current_section
            }
        else:
            if price and not current_item["price"]:
                current_item["price"] = price
            
            if cleaned_line:
                if current_item["description"]:
                    current_item["description"] += f" {cleaned_line}"
                else:
                    if len(current_item["name"]) < 15 and not current_item["description"]:
                        current_item["name"] += f" {cleaned_line}"
                    else:
                        current_item["description"] = cleaned_line

    if current_item and current_item["name"]:
        candidates.append(current_item)

    valid_candidates = []
    for c in candidates:
        if len(c["name"]) >= 3 and not c["name"].isdigit():
            valid_candidates.append(c)
            
    return valid_candidates


# ── Matching ──────────────────────────────────────────────────────────────────

from rapidfuzz import fuzz

def _match_name(
    extracted_name: str, db_names: List[Tuple[int, str]]
) -> Optional[Tuple[int, str, float]]:
    if not extracted_name or not db_names:
        return None
    best: Optional[Tuple[int, str, float]] = None
    best_score = 0.0
    for item_id, db_name in db_names:
        score = fuzz.token_set_ratio(extracted_name.lower(), db_name.lower()) / 100.0
        if score > best_score:
            best_score = score
            best = (item_id, db_name, score)
            
    if best and best_score >= 0.60:
        return best
    return None


# ── Diff ──────────────────────────────────────────────────────────────────────

def compute_diffs(
    google_cid: str,
    je_venue_id: Optional[str],
    candidates: List[Dict[str, Any]],
    db_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    db_by_id = {it["id"]: it for it in db_items}
    matched_ids = set()
    diffs: List[Dict[str, Any]] = []

    for cand in candidates:
        db_names = [(it["id"], it["name"]) for it in db_items]
        match = _match_name(cand["name"], db_names)
        
        if match:
            item_id, db_name, score = match
            db_item = db_by_id[item_id]
            matched_ids.add(item_id)

            diff_type = "match"
            db_price = db_item.get("price")
            if (
                cand["price"] is not None
                and db_price is not None
                and abs(cand["price"] - db_price) > 0.01
            ):
                diff_type = "price_changed"

            db_desc = (db_item.get("description") or "").strip()
            cand_desc = (cand.get("description") or "").strip()
            if (
                cand_desc
                and db_desc
                and fuzz.token_set_ratio(cand_desc.lower(), db_desc.lower()) < 60
            ):
                diff_type = diff_type if diff_type != "match" else "desc_changed"

            diffs.append({
                "diff_type": diff_type,
                "extracted_name": cand["name"],
                "db_name": db_name,
                "extracted_price": cand.get("price"),
                "db_price": db_price,
                "extracted_description": cand.get("description"),
                "db_description": db_desc,
                "menu_item_id": item_id,
                "match_score": round(score, 2),
                "section": cand.get("section", "general"),
            })
        else:
            diffs.append({
                "diff_type": "new",
                "extracted_name": cand["name"],
                "db_name": None,
                "extracted_price": cand.get("price"),
                "db_price": None,
                "extracted_description": cand.get("description"),
                "db_description": None,
                "menu_item_id": None,
                "match_score": None,
                "section": cand.get("section", "general"),
            })

    for it in db_items:
        if it["id"] not in matched_ids:
            diffs.append({
                "diff_type": "removed",
                "extracted_name": None,
                "db_name": it["name"],
                "extracted_price": None,
                "db_price": it.get("price"),
                "extracted_description": None,
                "db_description": it.get("description"),
                "menu_item_id": it["id"],
                "match_score": None,
                "section": it.get("section", "general"),
            })

    return diffs


# ── Main orchestrator ────────────────────────────────────────────────────────

class MenuExtractor:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Config.DB_PATH)
        self.image_root = str(Config.GOOGLE_IMAGES_DIR)

    def _get_je_venue_id(self, google_cid: str) -> Optional[str]:
        from src.database.init_db import get_session, Match

        place_id = CID_TO_PLACE_ID.get(google_cid)
        if not place_id:
            return None
        session = get_session(self.db_path)
        try:
            match = (
                session.query(Match)
                .filter(Match.google_venue_id == place_id)
                .first()
            )
            return match.je_venue_id if match else None
        except Exception as e:
            logger.error("Error resolving CID→venue: %s", e)
            return None
        finally:
            session.close()

    def _load_db_items(self, je_venue_id: str) -> List[Dict[str, Any]]:
        from src.database.init_db import get_session, MenuItem

        if not je_venue_id:
            return []
        session = get_session(self.db_path)
        try:
            rows = (
                session.query(MenuItem)
                .filter(MenuItem.je_venue_id == je_venue_id)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "price": r.price,
                    "description": r.description or "",
                    "section": r.section or "general",
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Error loading menu items: %s", e)
            return []
        finally:
            session.close()

    def _persist_extractions(
        self, google_cid: str, image_file: str, candidates: List[Dict[str, Any]]
    ):
        from src.database.init_db import get_session, MenuImageExtraction

        session = get_session(self.db_path)
        try:
            for c in candidates:
                extraction = MenuImageExtraction(
                    google_cid=google_cid,
                    image_file=image_file,
                    item_name=c["name"],
                    item_price=c.get("price"),
                    item_description=c.get("description"),
                    confidence=1.0,
                )
                session.add(extraction)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Error persisting extractions: %s", e)
        finally:
            session.close()

    def _persist_diffs(
        self,
        google_cid: str,
        je_venue_id: Optional[str],
        diffs: List[Dict[str, Any]],
    ):
        from src.database.init_db import get_session, MenuDiff

        session = get_session(self.db_path)
        try:
            for d in diffs:
                diff = MenuDiff(
                    google_cid=google_cid,
                    je_venue_id=je_venue_id,
                    diff_type=d["diff_type"],
                    extracted_name=d.get("extracted_name"),
                    db_name=d.get("db_name"),
                    extracted_price=d.get("extracted_price"),
                    db_price=d.get("db_price"),
                    extracted_description=d.get("extracted_description"),
                    db_description=d.get("db_description"),
                    menu_item_id=d.get("menu_item_id"),
                    match_score=d.get("match_score"),
                    section=d.get("section", "general"),
                )
                session.add(diff)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Error persisting diffs: %s", e)
        finally:
            session.close()

    def clear_venue_data(self, google_cid: str):
        from src.database.init_db import get_session, MenuImageExtraction, MenuDiff

        session = get_session(self.db_path)
        try:
            session.query(MenuImageExtraction).filter(
                MenuImageExtraction.google_cid == google_cid
            ).delete()
            session.query(MenuDiff).filter(
                MenuDiff.google_cid == google_cid
            ).delete()
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Error clearing venue data: %s", e)
        finally:
            session.close()

    def process_venue(self, google_cid: str) -> Dict[str, Any]:
        venue_dir = os.path.join(self.image_root, google_cid)
        if not os.path.isdir(venue_dir):
            return {"error": f"Image directory not found: {venue_dir}"}

        if not _HAS_EASYOCR:
            return {"error": "EasyOCR not installed. Run: pip install easyocr"}

        self.clear_venue_data(google_cid)
        je_venue_id = self._get_je_venue_id(google_cid)
        db_items = self._load_db_items(je_venue_id) if je_venue_id else []

        image_files = sorted(
            f
            for f in os.listdir(venue_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )
        all_diffs: List[Dict[str, Any]] = []

        for img_file in image_files:
            img_path = os.path.join(venue_dir, img_file)
            raw = ocr_image(img_path)
            if not raw:
                logger.info("No text in %s/%s", google_cid, img_file)
                continue

            candidates = parse_menu_text(raw)
            if not candidates:
                logger.info("No items parsed from %s/%s", google_cid, img_file)
                continue

            self._persist_extractions(google_cid, img_file, candidates)
            diffs = compute_diffs(google_cid, je_venue_id, candidates, db_items)
            self._persist_diffs(google_cid, je_venue_id, diffs)
            all_diffs.extend(diffs)
            logger.info(
                "EasyOCR: %d items from %s/%s", len(candidates), google_cid, img_file
            )

        return {
            "google_cid": google_cid,
            "je_venue_id": je_venue_id,
            "total_db_items": len(db_items),
            "extracted_items": len(all_diffs),
            "diffs": all_diffs,
        }
