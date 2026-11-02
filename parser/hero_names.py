"""
Reads which heroes the player used from the name on each Summary hero card.

Tesseract can't read this font ("SIGMA" came back as "olbM"), but the game draws a hero's
name the same way every time, so the images match. Tested on 51 cards from 26 real
Summary screenshots (11 heroes): the same hero scored 0.974+, different heroes 0.706 at
most. A mouse cursor over the name caused the lowest true match.

Unlike player_names/, these templates are game text and ship with the repo. A hero with
no template yet is left for the player to pick once, and that pick teaches it.
"""
import os
from pathlib import Path
from urllib.parse import quote, unquote

import cv2
import numpy as np
from PIL import Image

HERO_NAMES_DIR = Path(os.environ.get("OW_TRACKER_HERO_NAMES") or (Path(__file__).parent / "hero_names"))

MATCH_THRESHOLD = 0.90

_NAME_BOX = (262, 272, 500, 322)  # first card's name, at 1920×1080
_CARD_STEP = 240
_INK_LEVEL = 170
_SLIDE = 6  # slack in pixels when comparing


def _card_ink(img: Image.Image, card: int) -> np.ndarray:
    gray = np.array(img.convert("L").resize((1920, 1080)))
    x1, y1, x2, y2 = _NAME_BOX
    crop = gray[y1 + card * _CARD_STEP:y2 + card * _CARD_STEP, x1:x2]
    return (crop > _INK_LEVEL).astype(np.uint8) * 255


def _score(a: np.ndarray, b: np.ndarray) -> float:
    padded = cv2.copyMakeBorder(a, _SLIDE, _SLIDE, _SLIDE, _SLIDE, cv2.BORDER_CONSTANT, value=0)
    return float(cv2.matchTemplate(padded, b, cv2.TM_CCOEFF_NORMED).max())


def _load_templates() -> dict[str, np.ndarray]:
    templates = {}
    for path in HERO_NAMES_DIR.glob("*.png"):
        # np.fromfile + imdecode because cv2.imread can't open non-ASCII paths on Windows.
        crop = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if crop is not None:
            templates[unquote(path.stem)] = crop
    return templates


def read_cards(img: Image.Image, cards: list[int], pcts: list[int]) -> list[dict]:
    """One entry per played hero card, in card order. `hero` is None if not recognised."""
    templates = _load_templates()
    played = []
    for card, pct in zip(cards, pcts):
        ink = _card_ink(img, card)
        best, best_score = None, 0.0
        for hero, template in templates.items():
            score = _score(ink, template)
            if score > best_score:
                best, best_score = hero, score
        played.append({"card": card, "pct": pct, "hero": best if best_score >= MATCH_THRESHOLD else None})
    return played


def _save_template(hero: str, ink: np.ndarray) -> bool:
    ok, buf = cv2.imencode(".png", ink)
    if not ok:
        return False
    HERO_NAMES_DIR.mkdir(parents=True, exist_ok=True)
    buf.tofile(str(HERO_NAMES_DIR / f"{quote(hero, safe='')}.png"))
    return True


def learn_cards(path: str, played: list[dict], confirmed: list[tuple[str, int]]) -> list[str]:
    """Teach unrecognised cards from what the player confirmed, as (hero, pct) pairs. A
    card is paired by its %, so anything ambiguous or edited is skipped, not guessed."""
    known = {c["hero"] for c in played if c.get("hero")}
    unread = [c for c in played if not c.get("hero")]
    existing = _load_templates()
    learned = []
    with Image.open(path) as img:
        for card in unread:
            heroes = [h for h, pct in confirmed if pct == card["pct"] and h not in known]
            same_pct = [c for c in unread if c["pct"] == card["pct"]]
            if len(heroes) != 1 or len(same_pct) != 1 or heroes[0] in existing:
                continue
            if _save_template(heroes[0], _card_ink(img, card["card"])):
                learned.append(heroes[0])
    return learned
