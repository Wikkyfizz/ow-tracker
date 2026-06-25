"""
Hero icon template matching for OW2 Game Reports screenshots.
Each hero has a reference PNG in parser/hero_icons/{hero_slug}.png.
"""
import re
from pathlib import Path
import numpy as np

ICONS_DIR = Path(__file__).parent / "hero_icons"

# Approximate bounding boxes for each hero portrait slot in a 1920x1080 screenshot.
# Slot order (top to bottom): player 1–5 on each side.
# These are placeholder values — tune once you have real screenshots.
MY_TEAM_SLOTS = [
    (18, 244, 80, 296),
    (18, 312, 80, 364),
    (18, 380, 80, 432),
    (18, 448, 80, 500),
    (18, 516, 80, 568),
]
ENEMY_TEAM_SLOTS = [
    (18, 646, 80, 698),
    (18, 714, 80, 766),
    (18, 782, 80, 834),
    (18, 850, 80, 902),
    (18, 918, 80, 970),
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
        # Template matching on OW2's in-game portraits is unreliable below ~0.5
        if confidence < 0.5:
            return {
                "my_heroes": [],
                "enemy_heroes": [],
                "confidence": round(confidence, 2),
                "warning": f"Hero detection confidence too low ({confidence:.0%}) — enter heroes manually",
            }
        return {
            "my_heroes": my_heroes,
            "enemy_heroes": enemy_heroes,
            "confidence": round(confidence, 2),
        }
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
