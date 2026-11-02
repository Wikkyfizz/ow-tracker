"""
Recognises players by comparing the image of their scoreboard name.

Tesseract can't read these names reliably (styled fonts, CJK), but the game draws a
given name the same way every time, so the images match. Tested on 24 real scoreboards
from two different days (27,600 pairs): every pair scoring 0.865+ was the same player
and the first false match scored 0.862. True matches can score lower (animated
nameplates reached 0.83), so a match only prefills a choice the user confirms.

Templates are per-user data: player_names/ is gitignored and nothing here is shipped.
"""
import difflib
import os
from pathlib import Path
from urllib.parse import quote

import cv2
import numpy as np
import pytesseract

from parser.ocr import ENEMY_TEAM_ROW_Y, MY_TEAM_ROW_Y, _find_row_centers

NAMES_DIR = Path(os.environ.get("OW_TRACKER_NAMES") or (Path(__file__).parent.parent / "player_names"))

NAME_MATCH_THRESHOLD = 0.87
NEW_TEMPLATE_BELOW = 0.97  # a confirmed crop this different is worth keeping as a variant
MAX_TEMPLATES_PER_PLAYER = 5
OWN_NAME_MIN_RATIO = 0.75

_X_RANGE = (635, 905)          # the name column, including any nameplate banner
_OCR_X_START = 690             # past the rank badge that sits left of most names
_ROW_ABOVE, _ROW_BELOW = 26, 4  # name line, above the title line
_DISPLAY_BELOW = 16             # matching stops above the title; people need the whole name
_INK_LEVEL = 165
_CROP_TRIM_Y, _CROP_TRIM_X = 6, 10  # slack for the slide when matching


def _team_centers(img_bgr) -> tuple[list[int], list[int]]:
    h, w = img_bgr.shape[:2]
    measured = _find_row_centers(img_bgr, w, h)
    return measured or ([int(y * h / 1080) for y in MY_TEAM_ROW_Y],
                        [int(y * h / 1080) for y in ENEMY_TEAM_ROW_Y])


def name_rows(path: str, below: int = _ROW_BELOW, allies_only: bool = False) -> list[np.ndarray]:
    """The name regions in row order (allies, then enemies), normalised to 1920×1080.
    A team that lost a player has fewer than 5 rows."""
    img = cv2.imread(path)
    if img is None:
        return []
    if img.shape[:2] != (1080, 1920):
        img = cv2.resize(img, (1920, 1080), interpolation=cv2.INTER_AREA)
    my, enemy = _team_centers(img)
    centers = my if allies_only else my + enemy
    return [img[cy - _ROW_ABOVE:cy + below, _X_RANGE[0]:_X_RANGE[1]] for cy in centers]


def _ink(crop_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    return (gray > _INK_LEVEL).astype(np.uint8) * 255


def _slide_score(a: np.ndarray, b: np.ndarray) -> float:
    inner = a[_CROP_TRIM_Y:-_CROP_TRIM_Y, _CROP_TRIM_X:-_CROP_TRIM_X].astype(np.float32)
    if inner.std() == 0 or b.std() == 0:
        return 0.0
    return float(cv2.matchTemplate(b.astype(np.float32), inner, cv2.TM_CCOEFF_NORMED).max())


def name_score(ink_a: np.ndarray, ink_b: np.ndarray) -> float:
    """Slide each name over the other and keep the weaker result: a short name can sit
    inside a longer one, which only scores high in one direction."""
    return min(_slide_score(ink_a, ink_b), _slide_score(ink_b, ink_a))


def _player_dir(player: str) -> Path:
    return NAMES_DIR / quote(player, safe="")


def _read_png(path: Path):
    # np.fromfile + imdecode because cv2.imread can't open non-ASCII paths on Windows.
    return cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)


def load_templates(players: list[str]) -> dict[str, list[np.ndarray]]:
    templates = {}
    for player in players:
        folder = _player_dir(player)
        loaded = [_read_png(p) for p in sorted(folder.glob("*.png"))] if folder.is_dir() else []
        templates[player] = [t for t in loaded if t is not None]
    return templates


def best_match(ink: np.ndarray, templates: dict) -> tuple[str | None, float]:
    best_player, best_score = None, 0.0
    for player, crops in templates.items():
        for crop in crops:
            score = name_score(ink, crop)
            if score > best_score:
                best_player, best_score = player, score
    return (best_player, best_score) if best_score >= NAME_MATCH_THRESHOLD else (None, best_score)


def read_name(crop_bgr: np.ndarray) -> str:
    """Best-effort text for an unknown name, offered as a suggestion the user edits."""
    region = cv2.cvtColor(crop_bgr[:, _OCR_X_START - _X_RANGE[0]:], cv2.COLOR_BGR2GRAY)
    region = cv2.resize(region, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)
    binary = np.where(region > 170, 0, 255).astype(np.uint8)
    cfg = "--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return pytesseract.image_to_string(binary, config=cfg).strip()


def find_own_row(path: str, username: str) -> int | None:
    """Which ally row reads as the user's own name."""
    if not username:
        return None
    wanted = username.upper()
    best_row, best_ratio = None, 0.0
    for row, crop in enumerate(name_rows(path, allies_only=True)):
        ratio = difflib.SequenceMatcher(None, wanted, read_name(crop)).ratio()
        if ratio > best_ratio:
            best_row, best_ratio = row, ratio
    return best_row if best_ratio >= OWN_NAME_MIN_RATIO else None


def identify_allies(path: str, players: list[str], username: str = "") -> dict:
    """For each ally row: the known player it matches, or a text suggestion if none."""
    crops = name_rows(path, allies_only=True)
    templates = load_templates(players)
    rows = []
    for row, crop in enumerate(crops):
        player, score = best_match(_ink(crop), templates)
        rows.append({"row": row, "player": player, "score": round(score, 3),
                     "suggestion": "" if player else read_name(crop)})
    return {"rows": rows, "own_row": find_own_row(path, username)}


def remember_player(path: str, row: int, player: str) -> bool:
    """Keep this row's name as a template for the player unless it adds nothing."""
    crops = name_rows(path)
    if not 0 <= row < len(crops):
        return False
    ink = _ink(crops[row])
    existing = load_templates([player])[player]
    if len(existing) >= MAX_TEMPLATES_PER_PLAYER:
        return False
    if any(name_score(ink, t) >= NEW_TEMPLATE_BELOW for t in existing):
        return False
    folder = _player_dir(player)
    folder.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(".png", ink)
    if not ok:
        return False
    buf.tofile(str(folder / f"{len(existing)}.png"))
    return True


def row_image_png(path: str, row: int) -> bytes | None:
    crops = name_rows(path, below=_DISPLAY_BELOW)
    if not 0 <= row < len(crops):
        return None
    ok, buf = cv2.imencode(".png", crops[row])
    return buf.tobytes() if ok else None

