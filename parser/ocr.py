"""
OCR utilities for extracting text from OW2 Game Reports screenshots.
Requires Tesseract-OCR installed and in PATH.
"""
import re
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np

RANK_TIERS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster", "Champion"]

# These are best-guess pixel regions for a 1920×1080 Game Reports screenshot.
# All values are (left, top, right, bottom) in pixels.
# Tune these once you have actual screenshots.
REGIONS = {
    "map_name":   (680, 30,  1240, 80),   # top-center text area
    "outcome":    (820, 85,  1100, 130),  # "VICTORY" / "DEFEAT" banner
    "team1_rows": (200, 230, 960, 680),   # your team's 5 rows
    "team2_rows": (960, 230, 1720, 680),  # enemy team's 5 rows
}

# Stat column X-centers (approximate, 1920×1080)
STAT_COLS = {
    "elims":      550,
    "deaths":     640,
    "assists":    730,
    "damage":     870,
    "healing":    990,
    "mitigation": 1110,
}


def _preprocess(img: Image.Image) -> Image.Image:
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def _crop(img: Image.Image, region: tuple) -> Image.Image:
    return img.crop(region)


def _ocr(img: Image.Image, config: str = "--psm 7 -l eng") -> str:
    return pytesseract.image_to_string(_preprocess(img), config=config).strip()


def extract_map_name(img: Image.Image, known_maps: list[str]) -> tuple[str, float]:
    region = _crop(img, REGIONS["map_name"])
    raw = _ocr(region, config="--psm 7 -l eng")
    raw = raw.strip().title()
    best, best_score = "", 0.0
    for m in known_maps:
        score = _fuzzy_score(raw.lower(), m.lower())
        if score > best_score:
            best, best_score = m, score
    return best, best_score


def extract_outcome(img: Image.Image) -> tuple[str, float]:
    region = _crop(img, REGIONS["outcome"])
    raw = _ocr(region).upper()
    if "VICTORY" in raw or "WIN" in raw:
        return "Win", 0.95
    if "DEFEAT" in raw or "LOSS" in raw:
        return "Loss", 0.95
    if "DRAW" in raw:
        return "Draw", 0.90
    return "", 0.0


def extract_player_rows(img: Image.Image, team: str = "my") -> list[dict]:
    """
    Returns a list of dicts {name, elims, deaths, assists, damage, healing, mitigation}
    for each player in the specified team (my / enemy).
    Each row is extracted from the team's section.
    """
    region = REGIONS["team1_rows"] if team == "my" else REGIONS["team2_rows"]
    cropped = _crop(img, region)
    raw = _ocr(cropped, config="--psm 6 -l eng")
    return _parse_stat_block(raw)


def find_my_row(rows: list[dict], username: str) -> dict | None:
    username_lower = username.lower()
    for row in rows:
        if username_lower in row.get("name", "").lower():
            return row
    return None


def _parse_stat_block(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        nums = re.findall(r"\d+", line)
        name_part = re.sub(r"\d", "", line).strip(" |-")
        if len(nums) >= 4 and name_part:
            row = {
                "name": name_part,
                "elims":      int(nums[0]) if len(nums) > 0 else None,
                "deaths":     int(nums[1]) if len(nums) > 1 else None,
                "assists":    int(nums[2]) if len(nums) > 2 else None,
                "damage":     int(nums[3]) if len(nums) > 3 else None,
                "healing":    int(nums[4]) if len(nums) > 4 else None,
                "mitigation": int(nums[5]) if len(nums) > 5 else None,
            }
            rows.append(row)
    return rows


def extract_tracked_players(rows: list[dict], tracked: list[str]) -> list[str]:
    found = []
    for name in tracked:
        for row in rows:
            if name.lower() in row.get("name", "").lower():
                found.append(name)
                break
    return found


def _fuzzy_score(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if b in a or a in b:
        return 0.8
    overlap = sum(1 for c in a if c in b)
    return overlap / max(len(a), len(b), 1)
