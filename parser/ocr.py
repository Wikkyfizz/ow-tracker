"""
OCR utilities for OW2 Game Reports screenshots.
All layout constants are stored as fractions of image dimensions (reference: 1920×1080)
so they work at any resolution. Use px() / layout() to convert to pixels at runtime.

Handles three screenshot types:
  - TEAM tab:     player stats (E/A/D/DMG/H/MIT) for all 10 players
  - SUMMARY tab:  map name, outcome, game length, date, game mode, heroes played
                  (new 3-panel layout as of OW2 Season 16+)
  - PERSONAL tab: hero-specific stats — detection only; full parse is a future feature
"""
import re
import unicodedata
import pytesseract
from pytesseract import Output
from PIL import Image, ImageFilter, ImageEnhance
from datetime import datetime

from parser import digits
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

RANK_TIERS       = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster", "Champion"]
KNOWN_GAME_MODES = ["Control", "Escort", "Hybrid", "Push", "Flashpoint", "Clash"]

# ── Resolution-independent layout (fractions of image width / height) ─────────
# Reference resolution: 1920×1080.  Divide pixel values by W or H accordingly.

_REF_W, _REF_H = 1920, 1080

# TEAM tab — row y-centres as fraction of image height
MY_TEAM_ROW_Y_FRAC    = [y / _REF_H for y in [270, 338, 406, 474, 542]]
ENEMY_TEAM_ROW_Y_FRAC = [y / _REF_H for y in [688, 756, 824, 892, 960]]
ROW_HALF_H_FRAC       = 28 / _REF_H
ROW_SCAN_START_FRAC   = 240 / _REF_H   # just below the column-header bar

# Stat columns (x_left_frac, x_right_frac) — calibrated from 1920×1080.
# Column order on screen: E (elims), A (assists), D (deaths), DMG, H (healing), MIT.
STAT_COLS_FRAC = {
    "elims":       (912  / _REF_W, 962  / _REF_W),
    "assists":     (968  / _REF_W, 1012 / _REF_W),
    "deaths":      (1018 / _REF_W, 1082 / _REF_W),
    "damage":      (1092 / _REF_W, 1200 / _REF_W),
    "healing":     (1204 / _REF_W, 1296 / _REF_W),
    "mitigation":  (1296 / _REF_W, 1430 / _REF_W),
}

# Hero portrait face crop (x only; y uses row centres above)
PORTRAIT_X_FRAC = (558 / _REF_W, 628 / _REF_W)   # (x1_frac, x2_frac)

def _px(frac, dim):
    return int(frac * dim)


MIN_TEAM_ROWS = 3  # a team is 5 rows, or fewer when someone left the game


def _find_row_centers(img_bgr, img_w, img_h):
    """
    Locate the y-center of every player row from the bright digits in the
    DMG→MIT columns. Rows vary in height (optional player titles shift them), so
    positions are measured rather than assumed. The scan starts below the white
    column-header bar. A leaver's row disappears from the scoreboard, so a team can
    have fewer than 5; the widest gap, at the "VS" divider, separates the teams.
    Returns (my_team_ys, enemy_team_ys), or None if the rows don't look like two teams.
    """
    x1 = int(STAT_COLS_FRAC["damage"][0]     * img_w)
    x2 = int(STAT_COLS_FRAC["mitigation"][1] * img_w)
    y_start = _px(ROW_SCAN_START_FRAC, img_h)
    bright_per_line = (img_bgr[y_start:img_h, x1:x2].mean(axis=2) > 190).sum(axis=1)

    bands = []
    for y, count in enumerate(bright_per_line):
        if count < 3:
            continue
        if bands and y - bands[-1][1] <= 3:
            bands[-1][1] = y
        else:
            bands.append([y, y])

    # Keep digit-height bands, which drops thin lines such as the "VS" divider.
    min_h, max_h = _px(8 / _REF_H, img_h), _px(30 / _REF_H, img_h)
    centers = [y_start + (top + bot) // 2 for top, bot in bands if min_h <= bot - top <= max_h]
    if len(centers) < 2 * MIN_TEAM_ROWS:
        return None
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    split = gaps.index(max(gaps)) + 1
    my, enemy = centers[:split], centers[split:]
    within = gaps[:split - 1] + gaps[split:]
    if not (MIN_TEAM_ROWS <= len(my) <= 5 and MIN_TEAM_ROWS <= len(enemy) <= 5):
        return None
    if max(gaps) < 1.5 * max(within):  # no clear divider: not a scoreboard we can read
        return None
    return my, enemy


def row_slots(img_w, img_h, img_bgr=None):
    """
    Return (my_team_rows, enemy_team_rows) as lists of (x1,y1,x2,y2) pixel tuples.
    When img_bgr is supplied, each row's y-center is measured from the image, and a
    team that lost a player has fewer rows; otherwise (or if measuring fails) the
    typical 5 + 5 row positions are used.
    """
    px1 = _px(PORTRAIT_X_FRAC[0], img_w)
    px2 = _px(PORTRAIT_X_FRAC[1], img_w)
    half_h = _px(ROW_HALF_H_FRAC, img_h)

    my_ys    = [_px(f, img_h) for f in MY_TEAM_ROW_Y_FRAC]
    enemy_ys = [_px(f, img_h) for f in ENEMY_TEAM_ROW_Y_FRAC]

    if img_bgr is not None:
        measured = _find_row_centers(img_bgr, img_w, img_h)
        if measured:
            my_ys, enemy_ys = measured

    my_rows    = [(px1, cy - half_h, px2, cy + half_h) for cy in my_ys]
    enemy_rows = [(px1, cy - half_h, px2, cy + half_h) for cy in enemy_ys]
    return my_rows, enemy_rows

# Legacy pixel constants kept for callers that haven't migrated yet (1920×1080 assumed)
MY_TEAM_ROW_Y    = [int(f * _REF_H) for f in MY_TEAM_ROW_Y_FRAC]
ENEMY_TEAM_ROW_Y = [int(f * _REF_H) for f in ENEMY_TEAM_ROW_Y_FRAC]
ROW_HALF_H       = int(ROW_HALF_H_FRAC * _REF_H)
STAT_COLS        = {k: (int(x1 * _REF_W), int(x2 * _REF_W)) for k, (x1, x2) in STAT_COLS_FRAC.items()}

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
# The player's own totals in large type (middle panel). More reliable than the
# TEAM grid, which drops leading 1s; also what identifies the player's TEAM row.
SUMMARY_STAT_REGIONS = {
    "elims":   (880, 315, 1100, 352),
    "assists": (880, 556, 1100, 593),
    "deaths":  (880, 797, 1100, 834),
}
SUMMARY_PCT_REGIONS = [(262, 322, 420, 350), (262, 562, 420, 590), (262, 802, 420, 830)]  # hero-card "% played"

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


def _ocr_summary_int(img: Image.Image, region: tuple) -> int | None:
    """Read white-on-dark digits from the SUMMARY panels (upscale + threshold)."""
    crop = img.crop(region).convert("L")
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    binary = Image.fromarray(np.where(np.array(crop) > 105, 0, 255).astype(np.uint8))
    raw = pytesseract.image_to_string(
        binary, config="--psm 7 -c tessedit_char_whitelist=0123456789%"
    )
    m = re.search(r'\d+', raw)
    return int(m.group()) if m else None


def extract_summary_stats(img: Image.Image) -> dict:
    """The player's own E/A/D and the % played on each hero card (0% cards dropped)."""
    stats = {k: _ocr_summary_int(img, r) for k, r in SUMMARY_STAT_REGIONS.items()}
    pcts = [_ocr_summary_int(img, r) for r in SUMMARY_PCT_REGIONS]
    stats["played_pcts"] = [p for p in pcts if p]
    stats["played_cards"] = [i for i, p in enumerate(pcts) if p]
    return stats


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
        **extract_summary_stats(img),
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


def _fold_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _best_map_match(raw: str, known_maps: list[str]) -> tuple[str, float]:
    best, best_score = "", 0.0
    raw_folded = _fold_accents(raw).lower()
    for m in known_maps:
        # OCR rarely keeps accents, so compare folded but return the real name.
        score = _fuzzy_score(raw_folded, _fold_accents(m).lower())
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

def _ocr_team_numbers_fast(img: Image.Image, row_ys: list[int]) -> tuple[list[dict], list[int | None], int]:
    """
    Read every stat number for a whole 5-row team block in ONE Tesseract pass.

    OCRs the entire stat block (elims → mitigation, spanning all rows) with
    word-level boxes, then bins each detected digit-word by its y-centre (→ row)
    and x-centre (→ column). Returns one {stat: int | None} dict per row; a None
    means that cell was not confidently read and the caller should fall back to
    the slower multi-strategy per-cell _ocr_number. Also returns, per row, the
    y-centre of the digits actually found there (None if none were), so that
    fallback can crop the real row rather than the fixed estimate. Last, the number
    of digit-words that landed inside a row band: a row set that misses the digits
    (rows drifted off it) bins fewer, which is how extract_all_rows picks between them.

    This collapses the previous 30-cells × up-to-7-passes-each approach (up to
    ~210 subprocess spawns per team) into a single spawn for the common case.
    """
    empty = ([{s: None for s in STAT_COLS} for _ in row_ys], [None] * len(row_ys), 0)
    x1 = STAT_COLS["elims"][0]
    x2 = STAT_COLS["mitigation"][1]
    y_top = min(row_ys) - ROW_HALF_H
    y_bot = max(row_ys) + ROW_HALF_H
    block = img.crop((x1, y_top, x2, y_bot))
    cfg = "--psm 6 -c tessedit_char_whitelist=0123456789,"
    try:
        data = pytesseract.image_to_data(_preprocess(block), config=cfg, output_type=Output.DICT)
    except Exception:
        return empty

    col_centres = {s: (cl + cr) / 2.0 for s, (cl, cr) in STAT_COLS.items()}
    buckets = [{s: [] for s in STAT_COLS} for _ in row_ys]
    seen_ys = [[] for _ in row_ys]
    binned = 0
    for i in range(len(data["text"])):
        digits = (data["text"][i] or "").strip().replace(",", "")
        if not digits.isdigit():
            continue
        wl = x1 + data["left"][i]
        wr = wl + data["width"][i]
        cx = (wl + wr) / 2.0
        cy = y_top + data["top"][i] + data["height"][i] / 2.0
        ri = min(range(len(row_ys)), key=lambda k: abs(row_ys[k] - cy))
        if abs(row_ys[ri] - cy) > ROW_HALF_H:   # not inside any row band — drop noise
            continue
        seen_ys[ri].append(cy)
        binned += 1
        if _spans_columns(wl, wr):
            # Tesseract sometimes returns a row's E, A and D digits as one word
            # ("13 0 8" -> "1308"), which would land in the middle column. Skip it so
            # those cells fall back to the per-cell read, which can't merge columns.
            continue
        col = next((s for s, (cl, cr) in STAT_COLS.items() if cl <= cx < cr), None)
        if col is None:  # landed in a gutter between columns — snap to nearest
            col = min(col_centres, key=lambda s: abs(col_centres[s] - cx))
        buckets[ri][col].append((data["left"][i], digits))

    out = []
    for row_buckets in buckets:
        row = {}
        for s, words in row_buckets.items():
            if not words:
                row[s] = None
            else:
                words.sort()  # left-to-right, so comma-split numbers rejoin in order
                v = int("".join(d for _, d in words))
                # E/A/D are never 3 digits; a bigger value is a merged read.
                row[s] = None if s in _SMALL_STATS and v > _SMALL_STAT_MAX else v
        out.append(row)
    found = [int(sorted(ys)[len(ys) // 2]) if ys else None for ys in seen_ys]
    return out, found, binned


_SMALL_STATS = ("elims", "assists", "deaths")
_SMALL_STAT_MAX = 99
_COLUMN_OVERLAP_PX = 4  # a word reaching this far into a second column spans two
_ROW_SHIFT_PX = int(1.5 * ROW_HALF_H)  # a full team this far off the fixed rows is measured
_ROW_DRIFT_PX = ROW_HALF_H // 2  # further off than this, digits can leave the fixed rows' bands
_DRIFT_MIN_GAIN = 2  # Tesseract's word count varies by about 1 between two crops of one block


def _spans_columns(left: float, right: float) -> bool:
    """True if a word's x-extent [left, right) overlaps more than one stat column."""
    hit = sum(1 for cl, cr in STAT_COLS.values() if min(right, cr) - max(left, cl) >= _COLUMN_OVERLAP_PX)
    return hit > 1


def extract_all_rows(img: Image.Image) -> dict:
    """
    Extract stats for every player row on a TEAM tab screenshot (10, or fewer after a leaver).
    Returns {"my_team": [...], "enemy_team": [...]}.
    Each row: {elims, assists, deaths, damage, healing, mitigation}.

    Each cell is read first by matching its digits against templates (parser.digits),
    which unlike Tesseract doesn't drop a "1" from "11" or miss a dim grey "0". A cell
    it can't read with confidence (or every cell, if the templates are missing) falls
    back to Tesseract: one pass per 5-row team block that bins all numbers by row and
    column, then the multi-strategy per-cell _ocr_number for what's still empty.
    Names are handled by parser.names, not here.
    """
    def _read_rows(row_ys, fast_rows, found_ys, digit_ys):
        rows = []
        for row_y, found_y, digit_y, fast in zip(row_ys, found_ys, digit_ys, fast_rows):
            # Rows with player titles sit up to ~20px off the fixed estimate; a crop
            # around the estimate can cut the digits in half, so use where they were found.
            row_y = found_y if found_y is not None else row_y
            # The measured row centre is where the digits are; the templates need them whole.
            cy = digit_y if digit_y is not None else row_y
            row = {}
            for s, (xl, xr) in STAT_COLS.items():
                v = digits.read_cell(img.crop((xl, cy - ROW_HALF_H, xr, cy + ROW_HALF_H)))
                if v is not None and s in _SMALL_STATS and v > _SMALL_STAT_MAX:
                    v = None
                if v is None:
                    v = fast.get(s)
                if v is None:
                    v = _ocr_number(img, (xl, row_y - ROW_HALF_H, xr, row_y + ROW_HALF_H))
                row[s] = v
            rows.append(row)
        return rows

    # Full teams keep the fixed rows: measured ones shifted the binning and changed reads on
    # 29 of 43 real scoreboards, some for the worse. A team short a player has no fixed rows,
    # and a full enemy team below a short one sits ~66px above the fixed rows, which would
    # drop its first row and shift the rest up a slot. Player titles move rows by up to ~36px,
    # so only a bigger shift than that switches a full team to measured rows outright.
    # Between the two, a team drifted >14px (~30px on some enemy teams) can lose its digits
    # outside the fixed rows' bands, or its last row below the OCR'd block, so it is read at
    # both and the measured rows are kept only if they bin clearly more digit-words.
    def _read_team(measured_ys, fixed_ys):
        shift = (max(abs(m - f) for m, f in zip(measured_ys, fixed_ys))
                 if len(measured_ys) == 5 else 0)
        if 0 < len(measured_ys) < 5 or shift > _ROW_SHIFT_PX:
            ys = measured_ys
            fast_rows, found_ys, _ = _ocr_team_numbers_fast(img, ys)
        else:
            ys = fixed_ys
            fast_rows, found_ys, binned = _ocr_team_numbers_fast(img, ys)
            if shift > _ROW_DRIFT_PX:
                alt = _ocr_team_numbers_fast(img, measured_ys)
                if alt[2] >= binned + _DRIFT_MIN_GAIN:
                    ys, (fast_rows, found_ys, _) = measured_ys, alt
        digit_ys = measured_ys if len(measured_ys) == len(ys) else [None] * len(ys)
        return _read_rows(ys, fast_rows, found_ys, digit_ys)

    img_bgr = np.array(img.convert("RGB"))[:, :, ::-1]
    measured = _find_row_centers(img_bgr, img.width, img.height) or ([], [])
    return {"my_team": _read_team(measured[0], MY_TEAM_ROW_Y),
            "enemy_team": _read_team(measured[1], ENEMY_TEAM_ROW_Y)}


def extract_player_rows(img: Image.Image, team: str = "my") -> list[dict]:
    result = extract_all_rows(img)
    return result["my_team"] if team == "my" else result["enemy_team"]


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
