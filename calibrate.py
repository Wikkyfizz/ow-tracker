"""
OCR calibration script — run against inbox screenshots to verify region accuracy.
Usage:  python calibrate.py
        python calibrate.py path/to/specific/screenshot.png
"""
import sys
import json
from pathlib import Path
from PIL import Image

from parser.ocr import (
    detect_tab, extract_summary, extract_all_rows, extract_personal,
    SUMMARY_REGIONS, _ocr_line, _preprocess,
)


INBOX = Path(r"E:\Claude stuff\OW screenshots")
KNOWN_MAPS = [
    "Antarctic Peninsula", "Busan", "Ilios", "Lijiang Tower", "Nepal", "Oasis", "Samoa",
    "Circuit Royal", "Dorado", "Havana", "Junkertown", "Rialto", "Route 66",
    "Shambali Monastery", "Watchpoint: Gibraltar",
    "Blizzard World", "Eichenwalde", "Hollywood", "King's Row", "Midtown", "Numbani", "Paraiso",
    "Colosseo", "Esperanca", "New Junk City", "Suravasa",
    "New Queen Street", "Runasapi", "Throne of Anubis",
    "Hanaoka", "Neon Junction", "Overwatch Headquarters",
    "Ramattra Null Sector", "Timelocked Sanctum",
    "Aatlis",
]


def _divider(char="-", n=60):
    print(char * n)


def calibrate_summary(img: Image.Image, name: str):
    print(f"\n[SUMMARY] {name}")
    _divider()

    # Show raw OCR for each region
    for field, region in SUMMARY_REGIONS.items():
        raw = _ocr_line(img, region)
        print(f"  {field:12s} region {region}  →  '{raw}'")

    print()
    data = extract_summary(img, KNOWN_MAPS)
    print(f"  map:          {data['map']!r}")
    print(f"  outcome:      {data['outcome']!r}")
    print(f"  game_mode:    {data['game_mode']!r}")
    print(f"  played_at:    {data['played_at']!r}")
    print(f"  game_length:  {data['game_length_s']}s")
    if data["warnings"]:
        for w in data["warnings"]:
            print(f"  WARNING: {w}")


def calibrate_team(img: Image.Image, name: str):
    print(f"\n[TEAM] {name}")
    _divider()
    rows = extract_all_rows(img)
    print("  My team:")
    for r in rows["my_team"]:
        print(f"    {r['name']!r:30s}  E={r['elims']} A={r['assists']} D={r['deaths']} "
              f"DMG={r['damage']} H={r['healing']} MIT={r['mitigation']}")
    print("  Enemy team:")
    for r in rows["enemy_team"]:
        print(f"    {r['name']!r:30s}  E={r['elims']} A={r['assists']} D={r['deaths']} "
              f"DMG={r['damage']} H={r['healing']} MIT={r['mitigation']}")


def calibrate_personal(img: Image.Image, name: str):
    print(f"\n[PERSONAL] {name}")
    _divider()
    data = extract_personal(img)
    print(f"  detected hero: {data['hero']!r}")
    for w in data.get("warnings", []):
        print(f"  NOTE: {w}")


def run(paths):
    for p in paths:
        p = Path(p)
        if not p.exists():
            print(f"NOT FOUND: {p}")
            continue
        img = Image.open(p)
        tab = detect_tab(img)
        name = p.name

        if tab == "SUMMARY":
            calibrate_summary(img, name)
        elif tab == "TEAM":
            calibrate_team(img, name)
        elif tab == "PERSONAL":
            calibrate_personal(img, name)
        else:
            print(f"\n[UNKNOWN] {name}")
            # Dump raw OCR from key regions to help diagnose
            for label, region in [
                ("outcome_new", SUMMARY_REGIONS["outcome"]),
                ("team_header", (900, 208, 1080, 232)),
                ("personal_pct", (305, 255, 520, 295)),
            ]:
                print(f"  {label}: {_ocr_line(img, region)!r}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
    else:
        paths = sorted(INBOX.glob("*.png")) + sorted(INBOX.glob("*.jpg"))

    if not paths:
        print(f"No screenshots found in {INBOX}")
        sys.exit(1)

    print(f"Calibrating {len(paths)} screenshot(s)...")
    run(paths)
    print("\nDone.")
