"""
Hero icon template matching for OW2 Game Reports screenshots.
Each hero has a reference PNG in parser/hero_icons/{hero_slug}.png.
"""
import re
from pathlib import Path
import numpy as np

ICONS_DIR = Path(__file__).parent / "hero_icons"

# Hero portrait slots in the TEAMS tab (1920×1080).
# Portraits are circular crops inside the left side of the table.
# Row centres match MY_TEAM_ROW_Y / ENEMY_TEAM_ROW_Y in ocr.py (±28 px).
MY_TEAM_SLOTS = [
    (418, 242, 478, 298),
    (418, 310, 478, 366),
    (418, 378, 478, 434),
    (418, 446, 478, 502),
    (418, 514, 478, 570),
]
ENEMY_TEAM_SLOTS = [
    (418, 644, 478, 700),
    (418, 712, 478, 768),
    (418, 780, 478, 836),
    (418, 848, 478, 904),
    (418, 916, 478, 972),
]

_template_cache: dict = {}


def _hero_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def _load_templates() -> dict:
    if _template_cache:
        return _template_cache
    try:
        import cv2
        for path in ICONS_DIR.glob("*.png"):
            hero_name = path.stem.replace("_", " ").title()
            tmpl = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if tmpl is not None:
                _template_cache[hero_name] = tmpl
    except ImportError:
        pass
    return _template_cache


def _match_slot(img_bgr, slot: tuple, templates: dict) -> tuple[str, float]:
    try:
        import cv2
        l, t, r, b = slot
        crop = img_bgr[t:b, l:r]
        if crop.size == 0:
            return "", 0.0
        best_hero, best_score = "", 0.0
        for hero, tmpl in templates.items():
            resized = cv2.resize(tmpl, (r - l, b - t))
            result = cv2.matchTemplate(crop, resized, cv2.TM_CCOEFF_NORMED)
            score = float(result.max())
            if score > best_score:
                best_hero, best_score = hero, score
        return best_hero, best_score
    except Exception:
        return "", 0.0


def extract_heroes(img_path: str) -> dict:
    """
    Returns {"my_heroes": [...hero names...], "enemy_heroes": [...hero names...]}.
    Falls back to empty lists if opencv unavailable or icons not present.
    """
    templates = _load_templates()
    if not templates:
        return {"my_heroes": [], "enemy_heroes": [], "confidence": 0.0, "warning": "No icon templates found in parser/hero_icons/"}

    try:
        import cv2
        img = cv2.imread(img_path, cv2.IMREAD_COLOR)
        if img is None:
            return {"my_heroes": [], "enemy_heroes": [], "confidence": 0.0, "warning": f"Could not load image: {img_path}"}

        my_heroes, enemy_heroes = [], []
        scores = []

        for slot in MY_TEAM_SLOTS:
            hero, score = _match_slot(img, slot, templates)
            if hero:
                my_heroes.append(hero)
                scores.append(score)

        for slot in ENEMY_TEAM_SLOTS:
            hero, score = _match_slot(img, slot, templates)
            if hero:
                enemy_heroes.append(hero)
                scores.append(score)

        confidence = sum(scores) / len(scores) if scores else 0.0
        result = {
            "my_heroes":    my_heroes,
            "enemy_heroes": enemy_heroes,
            "confidence":   round(confidence, 2),
        }
        if confidence < 0.5:
            result["warning"] = f"Hero detection confidence low ({confidence:.0%}) — results may be wrong"
        return result
    except Exception as e:
        return {"my_heroes": [], "enemy_heroes": [], "confidence": 0.0, "warning": str(e)}


def download_icons(hero_names: list[str]):
    """
    Placeholder for downloading hero icons.
    Run `python -c "from parser.icons import download_icons; download_icons([...])"` to populate.
    """
    print(f"Icon download not yet implemented. Create {ICONS_DIR} and place hero PNGs there.")
    print("Naming convention: tracer.png, soldier__76.png (spaces→underscore, lowercase)")
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
