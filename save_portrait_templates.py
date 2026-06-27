"""
Save hero portrait templates from hand-labeled TEAM screenshot crops.
Run once: venv/Scripts/python.exe save_portrait_templates.py
"""
import sys
import re
import cv2
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parser.icons import extract_portrait_crop, PORTRAITS_DIR

INBOX = Path(r"E:\Claude stuff\OW screenshots")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")


# (screenshot_stem, team, row_0based, hero_name)
# All entries confirmed by user unless marked [unconfirmed].
# Entries for heroes whose template already exists are kept for reference but skipped.
LABELS = [
    # --- Overwatch_06W2CnsgI0 --- (sheet 1, fully confirmed)
    ("Overwatch_06W2CnsgI0", "my",    0, "Zarya"),
    ("Overwatch_06W2CnsgI0", "my",    1, "Cassidy"),
    ("Overwatch_06W2CnsgI0", "my",    2, "Tracer"),
    ("Overwatch_06W2CnsgI0", "my",    3, "Kiriko"),
    ("Overwatch_06W2CnsgI0", "my",    4, "Mizuki"),
    ("Overwatch_06W2CnsgI0", "enemy", 0, "Sigma"),
    ("Overwatch_06W2CnsgI0", "enemy", 1, "Sierra"),
    ("Overwatch_06W2CnsgI0", "enemy", 2, "Cassidy"),
    ("Overwatch_06W2CnsgI0", "enemy", 3, "Mizuki"),
    ("Overwatch_06W2CnsgI0", "enemy", 4, "Kiriko"),

    # --- Overwatch_1R56cHZndv --- (sheet 2, confirmed — bad crops excluded)
    # MY-1: Sigma — crop cut off at bottom, skip
    ("Overwatch_1R56cHZndv", "my",    1, "Sojourn"),
    ("Overwatch_1R56cHZndv", "my",    2, "Ashe"),
    ("Overwatch_1R56cHZndv", "my",    3, "Baptiste"),
    ("Overwatch_1R56cHZndv", "my",    4, "Zenyatta"),
    # EN-1: Sigma — crop cut off at bottom, skip
    # EN-2: Widowmaker — row displaced by Sigma bleed, skip
    ("Overwatch_1R56cHZndv", "enemy", 2, "Genji"),
    ("Overwatch_1R56cHZndv", "enemy", 3, "Kiriko"),
    ("Overwatch_1R56cHZndv", "enemy", 4, "Zenyatta"),

    # --- Overwatch_1R6DGlPdQ2 --- (sheet 3, partially confirmed)
    ("Overwatch_1R6DGlPdQ2", "my",    0, "Zarya"),
    ("Overwatch_1R6DGlPdQ2", "my",    1, "Shion"),
    ("Overwatch_1R6DGlPdQ2", "my",    2, "Cassidy"),
    ("Overwatch_1R6DGlPdQ2", "my",    3, "Kiriko"),
    ("Overwatch_1R6DGlPdQ2", "my",    4, "Illari"),
    ("Overwatch_1R6DGlPdQ2", "enemy", 0, "Zarya"),
    ("Overwatch_1R6DGlPdQ2", "enemy", 1, "Cassidy"),
    ("Overwatch_1R6DGlPdQ2", "enemy", 2, "Shion"),
    ("Overwatch_1R6DGlPdQ2", "enemy", 3, "Juno"),
    ("Overwatch_1R6DGlPdQ2", "enemy", 4, "Kiriko"),

    # --- Overwatch_4Zaakta4kE --- (sheet 4, fully confirmed)
    ("Overwatch_4Zaakta4kE", "my",    0, "Zarya"),
    ("Overwatch_4Zaakta4kE", "my",    1, "Mei"),
    ("Overwatch_4Zaakta4kE", "my",    2, "Genji"),
    ("Overwatch_4Zaakta4kE", "my",    3, "Moira"),
    ("Overwatch_4Zaakta4kE", "my",    4, "Kiriko"),
    ("Overwatch_4Zaakta4kE", "enemy", 0, "Wrecking Ball"),
    ("Overwatch_4Zaakta4kE", "enemy", 1, "Tracer"),
    ("Overwatch_4Zaakta4kE", "enemy", 2, "Sojourn"),
    ("Overwatch_4Zaakta4kE", "enemy", 3, "Kiriko"),
    ("Overwatch_4Zaakta4kE", "enemy", 4, "Wuyang"),

    # --- Overwatch_7www0b0WoJ --- (sheet 5, confirmed except MY-3)
    # MY-1: Junker Queen — crop cut off at bottom, skip
    ("Overwatch_7www0b0WoJ", "my",    1, "Torbjorn"),
    ("Overwatch_7www0b0WoJ", "my",    2, "Vendetta"),
    ("Overwatch_7www0b0WoJ", "my",    3, "Wuyang"),
    ("Overwatch_7www0b0WoJ", "my",    4, "Kiriko"),
    ("Overwatch_7www0b0WoJ", "enemy", 0, "Orisa"),
    ("Overwatch_7www0b0WoJ", "enemy", 1, "Shion"),
    ("Overwatch_7www0b0WoJ", "enemy", 2, "Reaper"),
    ("Overwatch_7www0b0WoJ", "enemy", 3, "Kiriko"),
    ("Overwatch_7www0b0WoJ", "enemy", 4, "Zenyatta"),

    # --- Overwatch_a3ozeQBJlu --- (sheet 6, MY only — enemy rows misplaced)
    ("Overwatch_a3ozeQBJlu", "my",    0, "Zarya"),
    ("Overwatch_a3ozeQBJlu", "my",    1, "Cassidy"),
    ("Overwatch_a3ozeQBJlu", "my",    2, "Junkrat"),
    ("Overwatch_a3ozeQBJlu", "my",    3, "Kiriko"),
    ("Overwatch_a3ozeQBJlu", "my",    4, "Ana"),

    # --- Overwatch_bMzBrYEn8M --- (sheet 7, confirmed)
    ("Overwatch_bMzBrYEn8M", "my",    0, "Zarya"),
    ("Overwatch_bMzBrYEn8M", "my",    1, "Sojourn"),
    ("Overwatch_bMzBrYEn8M", "my",    2, "Shion"),
    ("Overwatch_bMzBrYEn8M", "my",    3, "Kiriko"),
    ("Overwatch_bMzBrYEn8M", "my",    4, "Wuyang"),
    ("Overwatch_bMzBrYEn8M", "enemy", 0, "Zarya"),
    ("Overwatch_bMzBrYEn8M", "enemy", 1, "Tracer"),
    ("Overwatch_bMzBrYEn8M", "enemy", 2, "Cassidy"),
    ("Overwatch_bMzBrYEn8M", "enemy", 3, "Wuyang"),
    ("Overwatch_bMzBrYEn8M", "enemy", 4, "Kiriko"),

    # --- Overwatch_glEGeuSkaU --- (sheet 8, confirmed)
    ("Overwatch_glEGeuSkaU", "my",    0, "Sigma"),
    ("Overwatch_glEGeuSkaU", "my",    1, "Ashe"),
    ("Overwatch_glEGeuSkaU", "my",    2, "Widowmaker"),
    ("Overwatch_glEGeuSkaU", "my",    3, "Kiriko"),
    ("Overwatch_glEGeuSkaU", "my",    4, "Ana"),
    ("Overwatch_glEGeuSkaU", "enemy", 0, "Sigma"),
    ("Overwatch_glEGeuSkaU", "enemy", 1, "Shion"),
    ("Overwatch_glEGeuSkaU", "enemy", 2, "Mei"),
    ("Overwatch_glEGeuSkaU", "enemy", 3, "Kiriko"),
    ("Overwatch_glEGeuSkaU", "enemy", 4, "Wuyang"),

    # --- Overwatch_Q6vAdOYyVP --- (sheet 9)
    # MY-1: bad crop (tank portrait cut off at bottom) — skip
    ("Overwatch_Q6vAdOYyVP", "my",    1, "Shion"),
    ("Overwatch_Q6vAdOYyVP", "my",    2, "Mei"),
    ("Overwatch_Q6vAdOYyVP", "my",    3, "Mizuki"),
    ("Overwatch_Q6vAdOYyVP", "my",    4, "Moira"),
    ("Overwatch_Q6vAdOYyVP", "enemy", 0, "Reaper"),
    ("Overwatch_Q6vAdOYyVP", "enemy", 1, "Cassidy"),
    # EN-3: bad crop
    # EN-4: bad crop
    ("Overwatch_Q6vAdOYyVP", "enemy", 4, "Kiriko"),

    # --- Overwatch_RsmH1RshlB --- (sheet 10)
    ("Overwatch_RsmH1RshlB", "my",    0, "Zarya"),
    ("Overwatch_RsmH1RshlB", "my",    1, "Cassidy"),
    ("Overwatch_RsmH1RshlB", "my",    2, "Reaper"),
    ("Overwatch_RsmH1RshlB", "my",    3, "Kiriko"),
    ("Overwatch_RsmH1RshlB", "my",    4, "Moira"),
    # EN-1: bad crop
    ("Overwatch_RsmH1RshlB", "enemy", 1, "Shion"),
    ("Overwatch_RsmH1RshlB", "enemy", 2, "Hanzo"),
    ("Overwatch_RsmH1RshlB", "enemy", 3, "Kiriko"),
    ("Overwatch_RsmH1RshlB", "enemy", 4, "Ana"),

    # --- Overwatch_SlCTA43i5k --- (sheet 11)
    ("Overwatch_SlCTA43i5k", "my",    0, "Zarya"),
    ("Overwatch_SlCTA43i5k", "my",    1, "Ashe"),
    ("Overwatch_SlCTA43i5k", "my",    2, "Mei"),
    ("Overwatch_SlCTA43i5k", "my",    3, "Wuyang"),
    ("Overwatch_SlCTA43i5k", "my",    4, "Kiriko"),
    # EN-1 through EN-5: all bad crops (rows misaligned in this screenshot)

    # --- Overwatch_sM0bnxZLVF --- (sheet 12)
    ("Overwatch_sM0bnxZLVF", "my",    0, "Zarya"),
    ("Overwatch_sM0bnxZLVF", "my",    1, "Sojourn"),
    ("Overwatch_sM0bnxZLVF", "my",    2, "Cassidy"),
    ("Overwatch_sM0bnxZLVF", "my",    3, "Mizuki"),
    ("Overwatch_sM0bnxZLVF", "my",    4, "Kiriko"),
    ("Overwatch_sM0bnxZLVF", "enemy", 0, "Zarya"),
    ("Overwatch_sM0bnxZLVF", "enemy", 1, "Sojourn"),
    ("Overwatch_sM0bnxZLVF", "enemy", 2, "Lucio"),
    ("Overwatch_sM0bnxZLVF", "enemy", 3, "Kiriko"),
    ("Overwatch_sM0bnxZLVF", "enemy", 4, "Wuyang"),

    # --- Overwatch_TUCPtQoIBG --- (sheet 13)
    ("Overwatch_TUCPtQoIBG", "my",    0, "Zarya"),
    ("Overwatch_TUCPtQoIBG", "my",    1, "Soldier 76"),
    ("Overwatch_TUCPtQoIBG", "my",    2, "Shion"),
    ("Overwatch_TUCPtQoIBG", "my",    3, "Baptiste"),
    ("Overwatch_TUCPtQoIBG", "my",    4, "Mizuki"),
    ("Overwatch_TUCPtQoIBG", "enemy", 0, "Wrecking Ball"),
    ("Overwatch_TUCPtQoIBG", "enemy", 1, "Shion"),
    ("Overwatch_TUCPtQoIBG", "enemy", 2, "Widowmaker"),
    ("Overwatch_TUCPtQoIBG", "enemy", 3, "Brigitte"),
    ("Overwatch_TUCPtQoIBG", "enemy", 4, "Kiriko"),

    # --- Overwatch_xXm7xbfyho --- (sheet 14)
    # MY-1: bad crop (tank portrait cut off at bottom) — skip
    ("Overwatch_xXm7xbfyho", "my",    1, "Shion"),
    ("Overwatch_xXm7xbfyho", "my",    2, "Mei"),
    ("Overwatch_xXm7xbfyho", "my",    3, "Mizuki"),
    ("Overwatch_xXm7xbfyho", "my",    4, "Moira"),
    ("Overwatch_xXm7xbfyho", "enemy", 0, "Roadhog"),
    ("Overwatch_xXm7xbfyho", "enemy", 1, "Shion"),
    ("Overwatch_xXm7xbfyho", "enemy", 2, "Cassidy"),
    ("Overwatch_xXm7xbfyho", "enemy", 3, "Mizuki"),
    ("Overwatch_xXm7xbfyho", "enemy", 4, "Kiriko"),

    # --- Overwatch_ZGLCFsiOih --- (sheet 15)
    ("Overwatch_ZGLCFsiOih", "my",    0, "Baptiste"),
    ("Overwatch_ZGLCFsiOih", "my",    1, "Shion"),
    ("Overwatch_ZGLCFsiOih", "my",    2, "Junkrat"),
    ("Overwatch_ZGLCFsiOih", "my",    3, "Wuyang"),
    ("Overwatch_ZGLCFsiOih", "my",    4, "Kiriko"),
    ("Overwatch_ZGLCFsiOih", "enemy", 0, "Sigma"),
    ("Overwatch_ZGLCFsiOih", "enemy", 1, "Shion"),
    ("Overwatch_ZGLCFsiOih", "enemy", 2, "Mei"),
    ("Overwatch_ZGLCFsiOih", "enemy", 3, "Kiriko"),
    ("Overwatch_ZGLCFsiOih", "enemy", 4, "Junker Queen"),

    # --- Overwatch_zRPTVNorq2 --- (sheet 16)
    ("Overwatch_zRPTVNorq2", "my",    0, "Zarya"),
    ("Overwatch_zRPTVNorq2", "my",    1, "Emre"),
    ("Overwatch_zRPTVNorq2", "my",    2, "Shion"),
    ("Overwatch_zRPTVNorq2", "my",    3, "Kiriko"),
    ("Overwatch_zRPTVNorq2", "my",    4, "Zenyatta"),
    # EN-1 through EN-5: bad crops (rows misaligned in this screenshot)
    ("Overwatch_zRPTVNorq2", "enemy", 3, "Kiriko"),
]


def main():
    saved, skipped, errors, missing_files = 0, 0, 0, 0

    for stem, team, row, hero in LABELS:
        img_path = INBOX / f"{stem}.png"
        if not img_path.exists():
            print(f"  NOT FOUND: {img_path.name}")
            missing_files += 1
            continue

        slug = _slug(hero)
        out_path = PORTRAITS_DIR / team / f"{slug}.png"

        if out_path.exists():
            skipped += 1
            continue

        crop = extract_portrait_crop(str(img_path), team, row)
        if crop is None:
            print(f"  CROP FAIL : {stem} {team.upper()}-{row+1} ({hero})")
            errors += 1
            continue

        cv2.imwrite(str(out_path), crop)
        print(f"  Saved: {team}/{slug}.png  <- {stem} row {row+1}")
        saved += 1

    print(f"\nDone: {saved} saved, {skipped} already existed, "
          f"{errors} crop errors, {missing_files} missing files")
    print()

    # Report which heroes still have no template
    from build_portraits import ALL_HEROES
    for team in ("my", "enemy"):
        have = {p.stem for p in (PORTRAITS_DIR / team).glob("*.png")}
        missing = [h for h in ALL_HEROES if _slug(h) not in have]
        print(f"{team.upper()} — missing ({len(missing)}/{len(ALL_HEROES)}): "
              + ", ".join(missing))


if __name__ == "__main__":
    main()
