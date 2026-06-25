"""
OCR utilities for OW2 Game Reports screenshots (1920×1080).
Handles two screenshot types:
  - TEAM tab:    player stats (E/A/D/DMG/H/MIT) for all 10 players
  - SUMMARY tab: map name, outcome, game length, date, game mode, hero played
"""
import re
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
from datetime import datetime
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

RANK_TIERS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster", "Champion"]

# ── TEAM tab layout ───────────────────────────────────────────────────────────

MY_TEAM_ROW_Y    = [270, 338, 406, 474, 542]
ENEMY_TEAM_ROW_Y = [672, 740, 808, 876, 944]
ROW_HALF_H = 28

# Stat columns (x_left, x_right) — non-overlapping, calibrated from 1920×1080 screenshots.
# Column order on screen: E (elims), A (assists), D (deaths), DMG, H (healing), MIT.
STAT_COLS = {
    "elims":       (912, 962),
    "assists":     (968, 1012),
    "deaths":     (1018, 1082),
    "damage":     (1092, 1200),
    "healing":    (1204, 1296),
    "mitigation": (1296, 1430),
}

NAME_X_START = 150
NAME_X_END   = 900

# ── SUMMARY tab layout ────────────────────────────────────────────────────────

# Calibrated from bounding-box scan of actual screenshots.
SUMMARY_REGIONS = {
    "map_name":    (1270, 183, 1510, 220),   # "NEON JUNCTION"
    "outcome":     (1270, 590, 1520, 670),   # "DEFEAT" / "VICTORY" / "DRAW"
    "game_length": (1458, 740, 1545, 800),   # "16:03" — tightened to avoid left-edge icon noise
    "date_time":   (1370, 695, 1545, 725),   # "06/24/26 - 17:21"
    "game_mode":   (1448, 728, 1520, 756),   # "HYBRID" — starts after "GAME MODE:" label
}

# ── Preprocessing ─────────────────────────────────────────────────────────────

def _preprocess(img: Image.Image, invert: bool = False) -> Image.Image:
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(3.0)
    img = img.filter(ImageFilter.SHARPEN)
    if invert:
        img = Image.fromarray(255 - np.array(img))
    return img


def _ocr_number(img: Image.Image, region: tuple) -> int | None:
    """Extract a single integer from a region using multiple fallback strategies.
    Handles OW2's complex backgrounds including the gold-highlighted own-player row.
    """
    crop = img.crop(region)
    cfg = "--psm 7 -c tessedit_char_whitelist=0123456789"

    def _try(processed: Image.Image) -> int | None:
        raw = pytesseract.image_to_string(processed, config=cfg).strip()
        # Extract first contiguous digit sequence (ignores noise like "1160 7" → 1160)
        m = re.search(r'\d+', raw)
        if m:
            try:
                return int(m.group())
            except ValueError:
                pass
        return None

    for proc in (
        lambda c: _preprocess(c),
        lambda c: Image.fromarray(255 - np.array(c.convert("L"))),   # inverted
        lambda c: c.split()[1],                                        # green channel (gold row)
        lambda c: Image.fromarray(np.where(np.array(c.split()[0]) > 150, 255, 0).astype(np.uint8)),  # red threshold
        lambda c: Image.fromarray(np.where(np.array(c.convert("L")) > 200, 255, 0).astype(np.uint8)),
    ):
        result = _try(proc(crop))
        if result is not None:
            return result
    return None


def _ocr_line(img: Image.Image, region: tuple, config: str = "--psm 7 -l eng") -> str:
    """OCR a single line of text from a region. Tries normal then inverted."""
    crop = img.crop(region)
    raw_n = pytesseract.image_to_string(_preprocess(crop, invert=False), config=config).strip()
    raw_i = pytesseract.image_to_string(_preprocess(crop, invert=True),  config=config).strip()
    return raw_n if len(raw_n) >= len(raw_i) else raw_i


# ── Tab type detection ────────────────────────────────────────────────────────

def detect_tab(img: Image.Image) -> str:
    """Return 'SUMMARY', 'TEAM', or 'UNKNOWN'."""
    # Check for SUMMARY tab: outcome word appears in right panel
    region = SUMMARY_REGIONS["outcome"]
    raw = _ocr_line(img, region).upper()
    if any(w in raw for w in ("VICTORY", "DEFEAT", "DRAW")):
        return "SUMMARY"
    # Check for TEAM tab: E/A/D column headers appear at y≈216
    raw_header = _ocr_line(img, (900, 208, 1080, 232)).upper()
    if "E" in raw_header and "A" in raw_header:
        return "TEAM"
    return "UNKNOWN"


# ── SUMMARY tab extraction ────────────────────────────────────────────────────

def extract_summary(img: Image.Image, known_maps: list[str]) -> dict:
    """
    Parse a SUMMARY tab screenshot.
    Returns dict with: map, outcome, game_length_s, played_at, game_mode, warnings.
    """
    warnings = []

    # Map name
    raw_map = _ocr_line(img, SUMMARY_REGIONS["map_name"]).strip().title()
    map_name, map_conf = _best_map_match(raw_map, known_maps)
    if map_conf < 0.5:
        warnings.append(f"Low map confidence ({map_conf:.0%}): '{raw_map}'")

    # Outcome
    raw_outcome = _ocr_line(img, SUMMARY_REGIONS["outcome"]).upper()
    if "VICTORY" in raw_outcome:
        outcome, outcome_conf = "Win", 0.95
    elif "DEFEAT" in raw_outcome:
        outcome, outcome_conf = "Loss", 0.95
    elif "DRAW" in raw_outcome:
        outcome, outcome_conf = "Draw", 0.90
    else:
        outcome, outcome_conf = "", 0.0
        warnings.append(f"Could not detect outcome (got: '{raw_outcome[:40]}')")

    # Game length
    raw_len = _ocr_line(img, SUMMARY_REGIONS["game_length"]).strip()
    game_length_s = _parse_mmss(raw_len)
    if game_length_s is None:
        warnings.append(f"Could not parse game length: '{raw_len}'")

    # Date/time → played_at ISO string
    raw_dt = _ocr_line(img, SUMMARY_REGIONS["date_time"]).strip()
    played_at = _parse_datetime(raw_dt)
    if played_at is None:
        warnings.append(f"Could not parse date: '{raw_dt}'")

    # Game mode — strip leading non-alpha noise (e.g. "|" from adjacent UI element)
    raw_mode = re.sub(r'^[^A-Za-z]+', '', _ocr_line(img, SUMMARY_REGIONS["game_mode"])).strip().title()

    return {
        "map":          map_name,
        "outcome":      outcome,
        "game_length_s": game_length_s,
        "played_at":    played_at,
        "game_mode":    raw_mode,
        "warnings":     warnings,
    }


def _best_map_match(raw: str, known_maps: list[str]) -> tuple[str, float]:
    best, best_score = "", 0.0
    for m in known_maps:
        score = _fuzzy_score(raw.lower(), m.lower())
        if score > best_score:
            best, best_score = m, score
    return best, best_score


def _parse_mmss(raw: str) -> int | None:
    # Standard "MM:SS" with colon
    m = re.search(r'(\d{1,2}):(\d{2})', raw)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # Colon sometimes dropped by OCR — extract 4-digit sequence and treat as MMSS
    m = re.search(r'\d{4}', raw)
    if m:
        s = m.group()
        mins, secs = int(s[:2]), int(s[2:])
        if 0 <= secs < 60:
            return mins * 60 + secs
    # 3-digit: treat as M:SS
    m = re.search(r'\d{3}', raw)
    if m:
        s = m.group()
        return int(s[0]) * 60 + int(s[1:])
    return None


def _parse_datetime(raw: str) -> str | None:
    """Parse 'MM/DD/YY - HH:MM' or similar into ISO datetime string."""
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})\s*[-–]\s*(\d{1,2}):(\d{2})', raw)
    if m:
        mo, day, yr, hr, mi = m.groups()
        yr = int(yr)
        if yr < 100:
            yr += 2000
        try:
            dt = datetime(yr, int(mo), int(day), int(hr), int(mi))
            return dt.isoformat()
        except ValueError:
            pass
    return None


# ── TEAM tab extraction ───────────────────────────────────────────────────────

def extract_all_rows(img: Image.Image) -> dict:
    """
    Extract stats for all 10 players from a TEAM tab screenshot.
    Returns {"my_team": [...], "enemy_team": [...]}.
    Each row: {name, elims, assists, deaths, damage, healing, mitigation}.
    """
    my_team, enemy_team = [], []
    for row_y in MY_TEAM_ROW_Y:
        row = {s: _ocr_number(img, (xl, row_y - ROW_HALF_H, xr, row_y + ROW_HALF_H))
               for s, (xl, xr) in STAT_COLS.items()}
        row["name"] = _ocr_line(img, (NAME_X_START, row_y - ROW_HALF_H, NAME_X_END, row_y + ROW_HALF_H))
        my_team.append(row)
    for row_y in ENEMY_TEAM_ROW_Y:
        row = {s: _ocr_number(img, (xl, row_y - ROW_HALF_H, xr, row_y + ROW_HALF_H))
               for s, (xl, xr) in STAT_COLS.items()}
        row["name"] = _ocr_line(img, (NAME_X_START, row_y - ROW_HALF_H, NAME_X_END, row_y + ROW_HALF_H))
        enemy_team.append(row)
    return {"my_team": my_team, "enemy_team": enemy_team}


def find_my_row(rows: list[dict], username: str) -> dict | None:
    """OW2 always puts your own row first. Name matching used as confirmation only."""
    if not rows:
        return None
    username_lower = username.lower()
    for row in rows:
        if _fuzzy_score(username_lower, row.get("name", "").lower()) > 0.5:
            return row
    return rows[0]


def extract_player_rows(img: Image.Image, team: str = "my") -> list[dict]:
    result = extract_all_rows(img)
    return result["my_team"] if team == "my" else result["enemy_team"]


def extract_tracked_players(rows: list[dict], tracked: list[str]) -> list[str]:
    found = []
    for name in tracked:
        for row in rows:
            if name.lower() in row.get("name", "").lower():
                found.append(name)
                break
    return found


# ── Legacy stubs ──────────────────────────────────────────────────────────────

def extract_map_name(img: Image.Image, known_maps: list[str]) -> tuple[str, float]:
    """Use extract_summary() for SUMMARY tab screenshots instead."""
    return "", 0.0


def extract_outcome(img: Image.Image) -> tuple[str, float]:
    """Use extract_summary() for SUMMARY tab screenshots instead."""
    return "", 0.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fuzzy_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if b in a or a in b:
        return 0.8
    overlap = sum(1 for c in a if c in b)
    return overlap / max(len(a), len(b), 1)
