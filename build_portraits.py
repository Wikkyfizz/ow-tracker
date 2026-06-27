"""
Build the in-game portrait template library from labeled screenshot crops.

Usage:
  python build_portraits.py                    # interactive: show all crops, prompt for hero names
  python build_portraits.py --sheet            # save review sheets only, don't prompt
  python build_portraits.py --missing          # list heroes with no template yet

Templates are saved to parser/portraits/{my|enemy}/{hero_slug}.png
"""
import sys
import re
from pathlib import Path
from PIL import Image, ImageDraw

PORTRAITS_DIR = Path(__file__).parent / "parser" / "portraits"
INBOX         = Path(r"E:\Claude stuff\OW screenshots")
SHEETS_DIR    = Path(r"E:\Claude stuff\OW screenshots\portrait_library\sheets_v2")

PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
(PORTRAITS_DIR / "my").mkdir(exist_ok=True)
(PORTRAITS_DIR / "enemy").mkdir(exist_ok=True)
SHEETS_DIR.mkdir(parents=True, exist_ok=True)

ALL_HEROES = [
    "Ana", "Anran", "Ashe", "Baptiste", "Bastion", "Brigitte", "Cassidy",
    "D Va", "Doomfist", "Echo", "Emre", "Freja", "Genji", "Hanzo", "Hazard",
    "Illari", "Junkrat", "Junker Queen", "Jetpack Cat", "Kiriko", "Lifeweaver",
    "Lucio", "Mauga", "Mei", "Mercy", "Mizuki", "Moira", "Orisa", "Pharah",
    "Ramattra", "Reaper", "Reinhardt", "Roadhog", "Sigma", "Sierra", "Shion",
    "Sojourn", "Soldier 76", "Sombra", "Symmetra", "Torbjorn", "Tracer",
    "Venture", "Widowmaker", "Winston", "Wrecking Ball", "Wuyang", "Zarya",
    "Zenyatta", "Domina", "Persephone",
]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")


def _has_template(hero: str, team: str) -> bool:
    return (PORTRAITS_DIR / team / f"{_slug(hero)}.png").exists()


def _save_template(crop_bgr, hero: str, team: str):
    import cv2
    path = PORTRAITS_DIR / team / f"{_slug(hero)}.png"
    cv2.imwrite(str(path), crop_bgr)


def get_team_screenshots():
    from parser.ocr import detect_tab
    results = []
    for p in sorted(INBOX.glob("*.png")):
        img = Image.open(p)
        if detect_tab(img) == "TEAM":
            results.append(p)
    return results


def save_sheets(screenshots):
    """Save review sheets (5×2 grid per screenshot) for manual identification."""
    from parser.icons import extract_portrait_crop, CANONICAL_W, CANONICAL_H
    import cv2
    import numpy as np

    pad, zoom = 4, 4
    labels = [f"MY-{i+1}" for i in range(5)] + [f"EN-{i+1}" for i in range(5)]
    colors = [(100, 200, 255)] * 5 + [(255, 100, 100)] * 5

    for p in screenshots:
        cw, ch = CANONICAL_W * zoom, CANONICAL_H * zoom
        sheet_w = (cw + pad) * 5 + pad
        sheet_h = (ch + pad) * 2 + pad + 16
        sheet   = Image.new("RGB", (sheet_w, sheet_h), (30, 30, 30))
        draw    = ImageDraw.Draw(sheet)

        for idx, (team, row_i) in enumerate([("my", i) for i in range(5)] + [("enemy", i) for i in range(5)]):
            crop_bgr = extract_portrait_crop(str(p), team, row_i)
            if crop_bgr is None:
                continue
            crop_rgb = cv2.cvtColor(
                cv2.resize(crop_bgr, (cw, ch), interpolation=cv2.INTER_LANCZOS4),
                cv2.COLOR_BGR2RGB
            )
            col = idx % 5
            row = idx // 5
            x = pad + col * (cw + pad)
            y = pad + 14 + row * (ch + pad)
            sheet.paste(Image.fromarray(crop_rgb), (x, y))
            draw.text((x + 2, y - 13), labels[idx], fill=colors[idx])

        out = SHEETS_DIR / f"{p.stem}.png"
        sheet.save(out)
        print(f"  Sheet: {out.name}")


def missing_heroes():
    for team in ("my", "enemy"):
        have = {p.stem for p in (PORTRAITS_DIR / team).glob("*.png")}
        missing = [h for h in ALL_HEROES if _slug(h) not in have]
        print(f"\n{team.upper()} team — missing templates ({len(missing)}/{len(ALL_HEROES)}):")
        for h in missing:
            print(f"  {h}")


def interactive_label(screenshots):
    """Show each crop on the command line and prompt for a hero name."""
    from parser.icons import extract_portrait_crop, CANONICAL_W, CANONICAL_H
    import cv2

    print("\nFor each portrait, type the hero name (or Enter to skip, 'q' to quit).")
    print("Existing templates are skipped automatically.\n")

    for p in screenshots:
        print(f"\n--- {p.stem} ---")
        for team, row_i in [("my", i) for i in range(5)] + [("enemy", i) for i in range(5)]:
            crop = extract_portrait_crop(str(p), team, row_i)
            if crop is None:
                continue
            label = f"{'MY' if team == 'my' else 'EN'}-{row_i+1}"
            ans = input(f"  {label} hero name (Enter=skip): ").strip()
            if ans.lower() == "q":
                return
            if not ans:
                continue
            hero = ans.title()
            _save_template(crop, hero, team)
            print(f"    Saved: {team}/{_slug(hero)}.png")


if __name__ == "__main__":
    shots = get_team_screenshots()
    print(f"Found {len(shots)} TEAM screenshots in {INBOX}")

    if "--missing" in sys.argv:
        missing_heroes()
    elif "--sheet" in sys.argv or not sys.stdin.isatty():
        print("Saving review sheets...")
        save_sheets(shots)
        print("Done. Open the sheets folder to identify heroes, then re-run without --sheet.")
        missing_heroes()
    else:
        print("Saving review sheets first...")
        save_sheets(shots)
        interactive_label(shots)
        missing_heroes()
