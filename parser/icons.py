"""
Hero portrait matching for OW2 Game Reports screenshots.
Templates are in-game portrait crops stored in parser/portraits/{my|enemy}/{hero}.png.
All layout coordinates are resolution-independent (fraction-based via ocr.row_slots).
"""
import re
from pathlib import Path
import numpy as np

ICONS_DIR     = Path(__file__).parent / "hero_icons"      # legacy reference PNGs (unused for matching)
PORTRAITS_DIR = Path(__file__).parent / "portraits"        # in-game crop templates

# Canonical size all portrait crops are resized to before matching.
# Based on the 1920×1080 portrait region (70×56 px).
CANONICAL_W, CANONICAL_H = 70, 56

# Legacy slot constants kept for any callers that reference them directly.
# These now match the calibrated face coordinates in ocr.py.
MY_TEAM_SLOTS = [
    (558, 242, 628, 298),
    (558, 310, 628, 366),
    (558, 378, 628, 434),
    (558, 446, 628, 502),
    (558, 514, 628, 570),
]
ENEMY_TEAM_SLOTS = [
    (558, 660, 628, 716),
    (558, 728, 628, 784),
    (558, 796, 628, 852),
    (558, 864, 628, 920),
    (558, 932, 628, 988),
]

_portrait_cache: dict = {"my": {}, "enemy": {}}


def _hero_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def _load_portraits() -> dict:
    """Load in-game portrait templates from parser/portraits/{my|enemy}/{hero}.png."""
    if _portrait_cache["my"] or _portrait_cache["enemy"]:
        return _portrait_cache
    try:
        import cv2
        for team in ("my", "enemy"):
            team_dir = PORTRAITS_DIR / team
            if not team_dir.exists():
                continue
            for path in team_dir.glob("*.png"):
                hero = path.stem.replace("_", " ").title()
                img = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if img is not None:
                    # Store already resized to canonical dimensions
                    _portrait_cache[team][hero] = cv2.resize(
                        img, (CANONICAL_W, CANONICAL_H), interpolation=cv2.INTER_AREA
                    ).astype(np.float32)
    except ImportError:
        pass
    return _portrait_cache


def _ccoeff_normed(crop_bgr, tmpl_f32) -> float:
    """Normalised cross-correlation (TM_CCOEFF_NORMED equivalent, no mask needed)."""
    c = crop_bgr.astype(np.float32)
    cc = c - c.mean(); ct = tmpl_f32 - tmpl_f32.mean()
    num = (cc * ct).sum()
    den = np.sqrt((cc**2).sum() * (ct**2).sum())
    return float(num / den) if den > 0 else 0.0


def _match_slot(img_bgr, slot: tuple, templates: dict) -> tuple[str, float]:
    """Extract the portrait crop for a slot and score against all templates."""
    try:
        import cv2
        l, t, r, b = slot
        crop = img_bgr[t:b, l:r]
        if crop.size == 0:
            return "", 0.0
        crop_r = cv2.resize(crop, (CANONICAL_W, CANONICAL_H), interpolation=cv2.INTER_AREA)
        best_hero, best_score = "", -1.0
        for hero, tmpl in templates.items():
            score = _ccoeff_normed(crop_r, tmpl)
            if score > best_score:
                best_hero, best_score = hero, score
        return best_hero, best_score
    except Exception:
        return "", 0.0


def extract_heroes(img_path: str) -> dict:
    """
    Identify heroes from a TEAMS tab screenshot using in-game portrait templates.
    Templates must exist in parser/portraits/my/ and parser/portraits/enemy/.
    Returns {"my_heroes": [...], "enemy_heroes": [...], "confidence": float}.
    """
    from parser.ocr import row_slots
    portraits = _load_portraits()
    if not portraits["my"] and not portraits["enemy"]:
        return {
            "my_heroes": [], "enemy_heroes": [], "confidence": 0.0,
            "warning": f"No portrait templates found in {PORTRAITS_DIR}. Run build_portraits.py to create them.",
        }

    try:
        import cv2
        from PIL import Image
        img_pil = Image.open(img_path)
        W, H    = img_pil.size
        img_bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return {"my_heroes": [], "enemy_heroes": [], "confidence": 0.0, "warning": f"Could not load image: {img_path}"}

        my_slots, enemy_slots = row_slots(W, H)
        my_heroes, enemy_heroes, scores = [], [], []

        for slot in my_slots:
            hero, score = _match_slot(img_bgr, slot, portraits["my"])
            my_heroes.append(hero)
            if hero:
                scores.append(score)

        for slot in enemy_slots:
            hero, score = _match_slot(img_bgr, slot, portraits["enemy"])
            enemy_heroes.append(hero)
            if hero:
                scores.append(score)

        confidence = sum(scores) / len(scores) if scores else 0.0
        result = {"my_heroes": my_heroes, "enemy_heroes": enemy_heroes, "confidence": round(confidence, 2)}
        if confidence < 0.5:
            result["warning"] = f"Hero detection confidence low ({confidence:.0%}) — results may be wrong"
        return result
    except Exception as e:
        return {"my_heroes": [], "enemy_heroes": [], "confidence": 0.0, "warning": str(e)}


def extract_portrait_crop(img_path: str, team: str, row: int) -> "np.ndarray | None":
    """
    Extract and return the canonical portrait crop (CANONICAL_W×CANONICAL_H BGR)
    for a given team ('my'/'enemy') and row index (0-4).
    Used by build_portraits.py to create new templates.
    """
    from parser.ocr import row_slots
    try:
        import cv2
        from PIL import Image
        img_pil = Image.open(img_path)
        W, H    = img_pil.size
        img_bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return None
        my_slots, enemy_slots = row_slots(W, H)
        slots = my_slots if team == "my" else enemy_slots
        l, t, r, b = slots[row]
        crop = img_bgr[t:b, l:r]
        return cv2.resize(crop, (CANONICAL_W, CANONICAL_H), interpolation=cv2.INTER_AREA)
    except Exception:
        return None
