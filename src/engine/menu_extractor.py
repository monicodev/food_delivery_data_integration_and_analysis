"""
Menu Extractor — EasyOCR + parsing + matching + diff for venue menu images.
"""

from __future__ import annotations

import os
import re
import json
import logging
import unicodedata
from typing import Optional, Dict, Any, List, Tuple
from src.config import Config

# Required libraries for image rotation and preprocessing
import cv2
import numpy as np
from PIL import Image, ImageOps
from rapidfuzz import fuzz

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
    Detects the true optimal image orientation by thoroughly testing all 4 angles.
    Does not early-exit on low thresholds, ensuring horizontal menus are rotated correctly.
    """
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

    def _get_orientation_score(image_array: np.ndarray) -> int:
        cur_h, cur_w = image_array.shape[:2]
        crop_y1, crop_y2 = int(cur_h * 0.15), int(cur_h * 0.85)
        crop_x1, crop_x2 = int(cur_w * 0.15), int(cur_w * 0.85)
        sample = image_array[crop_y1:crop_y2, crop_x1:crop_x2]
        
        detected_texts = reader.readtext(sample, detail=0)
        
        score = 0
        for text in detected_texts:
            text_clean = text.lower().strip()
            if len(text_clean) >= 3 and not re.match(r'^[^a-zA-Z0-9]+$', text_clean):
                score += 1
                # Weight heavier for common menu linguistics/keywords found in this text
                if any(k in text_clean for k in ["pizz", "burg", "preu", "salsa", "amb", "formatge", "de"]):
                    score += 2
        return score

    # Generate all baseline rotation configurations
    img_90 = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    img_180 = cv2.rotate(img, cv2.ROTATE_180)
    img_270 = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

    scores = {
        "original": _get_orientation_score(img),
        "90": _get_orientation_score(img_90),
        "180": _get_orientation_score(img_180),
        "270": _get_orientation_score(img_270)
    }
    
    best_orientation = max(scores, key=scores.get)
    logger.info(f"Orientation analysis for {os.path.basename(image_path)}: {scores}. Selected: {best_orientation}")

    if best_orientation == "90":
        return img_90
    elif best_orientation == "180":
        return img_180
    elif best_orientation == "270":
        return img_270
        
    return img


# ── OCR (Column-Aware Processing) ───────────────────────────────────────────

def ocr_image(image_path: str) -> Optional[str]:
    """Extract raw text from an image keeping lines sorted vertically per column sequence."""
    if not _HAS_EASYOCR:
        logger.warning("EasyOCR not installed. Run: pip install easyocr")
        return None
    reader = _get_reader()
    if not reader:
        return None
    try:
        corrected_img = _rotate_image_if_needed(image_path)
        
        # Pull bounding box information (detail=1) to prevent mixed-column text stitching
        results = reader.readtext(corrected_img, detail=1, paragraph=False)
        if not results:
            return None
        
        w = corrected_img.shape[1]
        col_width = w / 2  # Assuming layout splits structurally down 2 primary vertical zones
        
        left_column = []
        right_column = []
        
        for bbox, text, conf in results:
            if conf < 0.35 or not text.strip():
                continue
            
            # Extract center X and Y coordinate points from polygon boundary
            center_x = sum(pt[0] for pt in bbox) / 4.0
            center_y = sum(pt[1] for pt in bbox) / 4.0
            
            if center_x < col_width:
                left_column.append((center_y, text))
            else:
                right_column.append((center_y, text))
                
        # Sequence layout elements linearly down each column lane independently
        left_column.sort(key=lambda x: x[0])
        right_column.sort(key=lambda x: x[0])
        
        combined_lines = [item[1] for item in left_column] + [item[1] for item in right_column]
        return "\n".join(combined_lines) if combined_lines else None

    except Exception as e:
        logger.error("EasyOCR failed for %s: %s", image_path, e)
        return None


# ── Parsing ──────────────────────────────────────────────────────────────────

_PRICE_RE = re.compile(
    r"(?P<price>\d{1,2}[.,]\d{1,2})\s*(?:€|EUR|euro)?|(?:€|EUR|euro)\s*(?P<price2>\d{1,2}[.,]\d{1,2})",
    re.IGNORECASE,
)

_ITEM_NUMBER_RE = re.compile(r"^\d+[\s.-]+")

# ── Garbage detection ─────────────────────────────────────────────────────────

_MENU_FOOTER_RE = re.compile(
    r"pedido\s*m[níi]*nimo|horario|tel[eé]fono|abierto|"
    r"domingo|s[bá]bado|viernes|lunes|martes|mi[eé]rcoles|"
    r"reparto|recoger|€\s*\d+[,.]\d{2}\s*(iva|tva|vat)",
    re.IGNORECASE,
)

def _is_garbage(text: str) -> bool:
    if not text or len(text) < 3:
        return True

    total = len(text)
    digits = sum(1 for c in text if c.isdigit())
    letters = sum(1 for c in text if c.isalpha())
    alphanum = digits + letters
    symbols = total - alphanum

    if digits / total > 0.60:
        return True

    if symbols / total > 0.40:
        return True

    if letters > 0 and letters / total < 0.20:
        return True

    stripped = text.replace(" ", "").replace(".", "").replace(",", "")
    if stripped and not any(c.isalpha() for c in stripped):
        return True

    if re.search(r"www\.|\.com|\.es\b", text, re.IGNORECASE):
        return True

    if _MENU_FOOTER_RE.search(text):
        return True

    words = text.split()
    if any(len(set(w)) == 1 and len(w) > 2 for w in words):
        return True

    unique = set(text.replace(" ", "").lower())
    if len(unique) <= 3 and total > 6 and letters / total < 0.5:
        return True

    if 3 < len(text) < 6 and digits > 0 and letters > 0 and not any(c.isspace() for c in text):
        return True

    if "€" in text and digits / total > 0.3 and letters < 3:
        return True

    if len(words) >= 2 and len(set(words)) == 1:
        return True

    if len(words) >= 3 and any(words.count(w) > 1 for w in set(words)):
        return True

    price_match = re.search(r"\d+\s*€", text)
    if price_match:
        rest = text[price_match.end():].strip()
        if rest and len(rest) < 12 and letters / total < 0.65:
            return True

    mangled_price = re.match(r"\d+[,.]\d*[a-zA-Z]", text)
    if mangled_price:
        return True

    consonant_run = re.findall(r"[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{4,}", text)
    if consonant_run:
        return True

    return False


_SECTION_HEADER_RE = re.compile(
    r"^(PIZZES|PIZZAS|BURGERS|ENTREPANS|AMANIDES|PASTES|DOLÇOS|SALSES|TOPPINGS|LES CASSOLETES|COSETES BONES|POSTRES|BEBIDAS|ENTRANTS|ENTRANTES|SEGONS|SEGUNDOS|PLATES|COMBINADOS|ESPECIALITAT|DRINKS|CURRIES)$",
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
        name = c["name"]
        if len(name) >= 3 and not name.isdigit() and not _is_garbage(name):
            valid_candidates.append(c)

    return valid_candidates


# ── Matching ──────────────────────────────────────────────────────────────────

def _normalize_match(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"^\d+[\s.\-)]*", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _match_name(
    extracted_name: str, db_names: List[Tuple[int, str]]
) -> Optional[Tuple[int, str, float]]:
    if not extracted_name or not db_names:
        return None
    norm_extracted = _normalize_match(extracted_name)
    best: Optional[Tuple[int, str, float]] = None
    best_score = 0.0
    for item_id, db_name in db_names:
        norm_db = _normalize_match(db_name)
        score = fuzz.token_set_ratio(norm_extracted, norm_db) / 100.0
        if score > best_score:
            best_score = score
            best = (item_id, db_name, score)
            
    if best and best_score >= 0.55:
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
                and fuzz.token_set_ratio(_normalize_match(cand_desc), _normalize_match(db_desc)) < 60
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
