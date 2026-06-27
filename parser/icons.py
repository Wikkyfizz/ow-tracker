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

# Scoreboard slot order is always: tank, dps, dps, support, support
SLOT_ROLES = ["tank", "dps", "dps", "support", "support"]

# CSV hero names that differ from the code names used as template slugs.
# Template filenames use code names; CSV uses display names with special chars.
_CSV_NAME_ALIASES: dict[str, str] = {
    "Soldier: 76": "Soldier 76",
    "Torbjörn":    "Torbjorn",
    "D.Va":        "D Va",
}

_CSV_ROLE_MAP = {"damage": "dps", "support": "support", "tank": "tank"}


def _load_hero_roles_from_csv() -> dict[str, str]:
    """Build {code_name: role} from data/heroes.csv. Returns empty dict on failure."""
    import csv as _csv
    csv_path = Path(__file__).parent.parent / "data" / "heroes.csv"
    if not csv_path.exists():
        return {}
    result = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                name = _CSV_NAME_ALIASES.get(row["name"], row["name"])
                role = _CSV_ROLE_MAP.get(row["role"].strip().lower())
                if role:
                    result[name] = role
    except Exception:
        pass
    return result


# Loaded from heroes.csv at import time. Falls back to hardcoded dict if CSV unavailable.
HERO_ROLES: dict[str, str] = _load_hero_roles_from_csv() or {
    "D Va": "tank", "Domina": "tank", "Doomfist": "tank", "Hazard": "tank",
    "Junker Queen": "tank", "Mauga": "tank", "Orisa": "tank",
    "Ramattra": "tank", "Reinhardt": "tank", "Roadhog": "tank",
    "Sigma": "tank", "Winston": "tank", "Wrecking Ball": "tank", "Zarya": "tank",
    "Anran": "dps", "Ashe": "dps", "Bastion": "dps", "Cassidy": "dps", "Echo": "dps",
    "Emre": "dps", "Freja": "dps", "Genji": "dps", "Hanzo": "dps",
    "Junkrat": "dps", "Mei": "dps", "Pharah": "dps", "Reaper": "dps",
    "Sierra": "dps", "Shion": "dps", "Sojourn": "dps", "Soldier 76": "dps",
    "Sombra": "dps", "Symmetra": "dps", "Torbjorn": "dps", "Tracer": "dps",
    "Vendetta": "dps", "Venture": "dps", "Widowmaker": "dps",
    "Ana": "support", "Baptiste": "support", "Brigitte": "support",
    "Illari": "support", "Jetpack Cat": "support", "Juno": "support", "Kiriko": "support",
    "Lifeweaver": "support", "Lucio": "support", "Mercy": "support",
    "Mizuki": "support", "Moira": "support", "Wuyang": "support", "Zenyatta": "support",
}

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

CONFIDENCE_THRESHOLD = 0.65  # below this → slot shows "Unknown [Role]" instead of a wrong guess

_UNKNOWN_LABEL = {"tank": "Unknown [Tank]", "dps": "Unknown [DPS]", "support": "Unknown [Support]"}

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


def _match_slot(img_bgr, slot: tuple, templates: dict, role: str | None = None) -> tuple[str, float]:
    """Extract the portrait crop for a slot and score against role-filtered templates."""
    try:
        import cv2
        l, t, r, b = slot
        crop = img_bgr[t:b, l:r]
        if crop.size == 0:
            return "", 0.0
        crop_r = cv2.resize(crop, (CANONICAL_W, CANONICAL_H), interpolation=cv2.INTER_AREA)
        # Restrict candidates to the correct role; heroes with no role entry are included as fallback
        if role:
            candidates = {h: t for h, t in templates.items()
                          if HERO_ROLES.get(h) == role or h not in HERO_ROLES}
            if not candidates:
                candidates = templates
        else:
            candidates = templates
        best_hero, best_score = "", -1.0
        for hero, tmpl in candidates.items():
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

        my_slots, enemy_slots = row_slots(W, H, img_bgr)
        my_heroes, enemy_heroes, scores = [], [], []

        for i, slot in enumerate(my_slots):
            role = SLOT_ROLES[i]
            hero, score = _match_slot(img_bgr, slot, portraits["my"], role)
            display = hero if (hero and score >= CONFIDENCE_THRESHOLD) else _UNKNOWN_LABEL.get(role, "Unknown")
            my_heroes.append({"hero": display, "confidence": round(score, 2), "role": role})
            scores.append(score)

        for i, slot in enumerate(enemy_slots):
            role = SLOT_ROLES[i]
            hero, score = _match_slot(img_bgr, slot, portraits["enemy"], role)
            display = hero if (hero and score >= CONFIDENCE_THRESHOLD) else _UNKNOWN_LABEL.get(role, "Unknown")
            enemy_heroes.append({"hero": display, "confidence": round(score, 2), "role": role})
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
        my_slots, enemy_slots = row_slots(W, H, img_bgr)
        slots = my_slots if team == "my" else enemy_slots
        l, t, r, b = slots[row]
        crop = img_bgr[t:b, l:r]
        return cv2.resize(crop, (CANONICAL_W, CANONICAL_H), interpolation=cv2.INTER_AREA)
    except Exception:
        return None
