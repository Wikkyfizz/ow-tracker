"""
OCR utilities for OW2 Game Reports screenshots (1920×1080).
Handles three screenshot types:
  - TEAM tab:     player stats (E/A/D/DMG/H/MIT) for all 10 players
  - SUMMARY tab:  map name, outcome, game length, date, game mode, heroes played
                  (new 3-panel layout as of OW2 Season 16+)
  - PERSONAL tab: hero-specific stats — detection only; full parse is a future feature
"""
import re
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
from datetime import datetime
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

RANK_TIERS      = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster", "Champion"]
KNOWN_GAME_MODES = ["Control", "Escort", "Hybrid", "Push", "Flashpoint", "Clash"]

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

# ── SUMMARY tab layout (new 3-panel layout, OW2 Season 16+) ──────────────────
#
# Layout: [HEROES PLAYED | TOTAL PERFORMANCE | MAP INFO PANEL]
# The right panel (x≈985–1390) contains:
#   • Map name header at top
#   • Map image (~y 175–450)
#   • DEFEAT / VICTORY / DRAW text (large italic)
#   • Bullet list: · FINAL SCORE / · DATE / · GAME MODE / · GAME LENGTH
#
# Calibrated from 1920×1080 screenshots.
SUMMARY_REGIONS = {
    "map_name":    (986, 185, 1500, 215),   # right-panel header text
    "final_score": (1200, 660, 1505, 692),  # "· FINAL SCORE: X VS Y" — derive outcome from scores
    "date_time":   (1200, 685, 1525, 722),  # "· DATE: 06/24/26 - 17:21" (1525 to capture full time)
}
# GAME MODE and GAME LENGTH bullet positions vary by game mode (Push skips GAME MODE).
# _scan_summary_bullets() scans this y range dynamically.
SUMMARY_BULLET_SCAN_Y = (712, 790)  # y range to scan for GAME MODE / GAME LENGTH

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
        lambda c: c.convert("L"),                                      # raw grayscale (catches dim "0")
        lambda c: Image.fromarray(np.where(np.array(c.convert("L")) > 20, 255, 0).astype(np.uint8)),  # very low threshold
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
    """Return 'SUMMARY', 'TEAM', 'PERSONAL', or 'UNKNOWN'."""
    # PERSONAL first — hero card overlaps with SUMMARY left panel region
    raw_personal = _ocr_line(img, (305, 315, 680, 345)).upper()
    if "PERCENT" in raw_personal:
        return "PERSONAL"

    # SUMMARY: "· FINAL SCORE: X VS Y" in right panel — present on all game modes
    raw = _ocr_line(img, SUMMARY_REGIONS["final_score"]).upper()
    if "FINAL" in raw and "SCORE" in raw:
        return "SUMMARY"

    # TEAM: E/A/D column headers at y≈216
    raw_header = _ocr_line(img, (900, 208, 1080, 232)).upper()
    if "E" in raw_header and "A" in raw_header:
        return "TEAM"

    return "UNKNOWN"


# ── SUMMARY tab extraction ────────────────────────────────────────────────────

def _scan_summary_bullets(img: Image.Image) -> dict:
    """
    Scan for GAME MODE and GAME LENGTH bullets in the right panel.
    GAME MODE is absent on some game types (Push); callers must handle missing keys.
    FINAL SCORE and DATE are at fixed positions and read separately in extract_summary().
    """
    y_start, y_end = SUMMARY_BULLET_SCAN_Y
    window, step, x1, x2 = 34, 17, 1200, 1510
    found = {}
    for y in range(y_start, y_end - window, step):
        line = _ocr_line(img, (x1, y, x2, y + window))
        u = line.upper()
        for label, key in [("GAME MODE", "game_mode"), ("GAME LENGTH", "game_length")]:
            if label in u and key not in found:
                found[key] = line.split(':', 1)[1].strip() if ':' in line else line
    return found


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

    bullets = _scan_summary_bullets(img)

    # Outcome — "· FINAL SCORE: X VS Y"; player score is always the LEFT number
    raw_score = _ocr_line(img, SUMMARY_REGIONS["final_score"])
    score_m = re.search(r'([O\d]+)\W{0,3}vs\W{0,3}([O\d]+)', raw_score, re.IGNORECASE)
    if score_m:
        left  = int(score_m.group(1).upper().replace('O', '0'))
        right = int(score_m.group(2).upper().replace('O', '0'))
        outcome = "Win" if left > right else ("Loss" if left < right else "Draw")
    else:
        outcome = ""
        warnings.append(f"Could not parse FINAL SCORE: '{raw_score}'")

    # Game length
    raw_len = bullets.get("game_length", "")
    game_length_s = _parse_mmss(raw_len)
    if game_length_s is None:
        warnings.append(f"Could not parse game length: '{raw_len}'")

    # Date/time — fixed position
    raw_dt = _ocr_line(img, SUMMARY_REGIONS["date_time"])
    played_at = _parse_datetime(raw_dt)
    if played_at is None:
        warnings.append(f"Could not parse date: '{raw_dt}'")

    # Game mode (absent on some game types — e.g. Push); fuzzy-match to known values
    raw_mode = re.sub(r'^[^A-Za-z]+', '', bullets.get("game_mode", ""))
    raw_mode = re.sub(r'[^A-Za-z]+$', '', raw_mode).strip()
    if raw_mode:
        mode_match, mode_conf = _best_mode_match(raw_mode, KNOWN_GAME_MODES)
        raw_mode = mode_match if mode_conf >= 0.5 else raw_mode.title()

    return {
        "map":           map_name,
        "outcome":       outcome,
        "game_length_s": game_length_s,
        "played_at":     played_at,
        "game_mode":     raw_mode,
        "warnings":      warnings,
    }


def _best_mode_match(raw: str, known_modes: list[str]) -> tuple[str, float]:
    """Match a possibly-truncated game mode string using positional prefix similarity."""
    raw_u = raw.upper()
    best, best_score = "", 0.0
    for m in known_modes:
        m_u = m.upper()
        n = min(len(raw_u), len(m_u))
        if n == 0:
            continue
        matches = sum(1 for i in range(n) if raw_u[i] == m_u[i])
        score = matches / n
        if score > best_score:
            best, best_score = m, score
    if best_score >= 0.6:
        return best, best_score
    return _best_map_match(raw, known_modes)


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


# ── PERSONAL tab (stub — full parse is a future feature) ─────────────────────

def extract_personal(img: Image.Image) -> dict:
    """
    Detect hero and basic play-time from a PERSONAL tab screenshot.
    Full hero-specific stat parsing is a future feature; returns a typed stub.
    """
    hero_name = _ocr_line(img, (40, 165, 285, 200)).strip().title()
    return {"hero": hero_name, "warnings": ["PERSONAL tab stats not yet parsed"]}


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
