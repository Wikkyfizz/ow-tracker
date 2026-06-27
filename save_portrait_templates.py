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
# Uncertain identifications are commented out with a note.
LABELS = [
    # --- Overwatch_06W2CnsgI0 ---
    ("Overwatch_06W2CnsgI0", "my",    0, "Zarya"),
    ("Overwatch_06W2CnsgI0", "my",    1, "Cassidy"),
    ("Overwatch_06W2CnsgI0", "my",    2, "Tracer"),
    ("Overwatch_06W2CnsgI0", "my",    3, "Kiriko"),
    # MY-5: teal armored helmet — uncertain
    # EN-1: uncertain
    # EN-3: Cassidy (covered above)
    ("Overwatch_06W2CnsgI0", "enemy", 4, "Kiriko"),

    # --- Overwatch_1R56cHZndv ---
    ("Overwatch_1R56cHZndv", "my",    0, "Baptiste"),
    ("Overwatch_1R56cHZndv", "my",    1, "Mauga"),
    ("Overwatch_1R56cHZndv", "my",    2, "Ashe"),
    ("Overwatch_1R56cHZndv", "my",    3, "Lucio"),
    ("Overwatch_1R56cHZndv", "my",    4, "Soldier 76"),
    ("Overwatch_1R56cHZndv", "enemy", 0, "Baptiste"),
    ("Overwatch_1R56cHZndv", "enemy", 1, "Ramattra"),
    ("Overwatch_1R56cHZndv", "enemy", 2, "Genji"),
    ("Overwatch_1R56cHZndv", "enemy", 3, "Kiriko"),
    ("Overwatch_1R56cHZndv", "enemy", 4, "Soldier 76"),

    # --- Overwatch_1R6DGlPdQ2 ---
    ("Overwatch_1R6DGlPdQ2", "my",    0, "Zarya"),
    ("Overwatch_1R6DGlPdQ2", "my",    1, "Moira"),
    ("Overwatch_1R6DGlPdQ2", "my",    2, "Cassidy"),
    ("Overwatch_1R6DGlPdQ2", "my",    3, "Kiriko"),
    # MY-5: partially clipped — uncertain (Sojourn?)
    ("Overwatch_1R6DGlPdQ2", "enemy", 0, "Zarya"),
    ("Overwatch_1R6DGlPdQ2", "enemy", 1, "Cassidy"),
    ("Overwatch_1R6DGlPdQ2", "enemy", 2, "Moira"),
    # EN-4: purple-blue hair, crescent marking — uncertain (D.Va? Ana?)
    ("Overwatch_1R6DGlPdQ2", "enemy", 4, "Kiriko"),

    # --- Overwatch_4Zaakta4kE ---
    ("Overwatch_4Zaakta4kE", "my",    0, "Zarya"),
    ("Overwatch_4Zaakta4kE", "my",    1, "Mei"),
    ("Overwatch_4Zaakta4kE", "my",    2, "Genji"),
    ("Overwatch_4Zaakta4kE", "my",    3, "Junker Queen"),
    ("Overwatch_4Zaakta4kE", "my",    4, "Kiriko"),
    ("Overwatch_4Zaakta4kE", "enemy", 0, "Wrecking Ball"),
    ("Overwatch_4Zaakta4kE", "enemy", 1, "Tracer"),
    ("Overwatch_4Zaakta4kE", "enemy", 2, "Mauga"),
    ("Overwatch_4Zaakta4kE", "enemy", 3, "Kiriko"),
    # EN-5: young dark-haired man — uncertain

    # --- Overwatch_7www0b0WoJ ---
    ("Overwatch_7www0b0WoJ", "my",    0, "Venture"),
    ("Overwatch_7www0b0WoJ", "my",    1, "Torbjorn"),
    # MY-3: dark-skinned woman, gold accent — uncertain (Sojourn?)
    # MY-4: dark skin, wide toothy grin — uncertain
    ("Overwatch_7www0b0WoJ", "my",    4, "Kiriko"),
    # EN-1: yellow round mask, orange eye — uncertain
    ("Overwatch_7www0b0WoJ", "enemy", 1, "Moira"),
    ("Overwatch_7www0b0WoJ", "enemy", 2, "Reaper"),
    ("Overwatch_7www0b0WoJ", "enemy", 3, "Kiriko"),
    ("Overwatch_7www0b0WoJ", "enemy", 4, "Soldier 76"),

    # --- Overwatch_a3ozeQBJlu ---
    ("Overwatch_a3ozeQBJlu", "my",    0, "Zarya"),
    ("Overwatch_a3ozeQBJlu", "my",    1, "Cassidy"),
    ("Overwatch_a3ozeQBJlu", "my",    2, "Junkrat"),
    ("Overwatch_a3ozeQBJlu", "my",    3, "Kiriko"),
    ("Overwatch_a3ozeQBJlu", "my",    4, "Ana"),
    # EN-*: rows still split/misaligned in this screenshot — skip all enemy

    # --- Overwatch_bMzBrYEn8M ---
    ("Overwatch_bMzBrYEn8M", "my",    0, "Zarya"),
    ("Overwatch_bMzBrYEn8M", "my",    1, "Mauga"),
    ("Overwatch_bMzBrYEn8M", "my",    2, "Moira"),
    ("Overwatch_bMzBrYEn8M", "my",    3, "Kiriko"),
    ("Overwatch_bMzBrYEn8M", "my",    4, "Sojourn"),
    ("Overwatch_bMzBrYEn8M", "enemy", 0, "Zarya"),
    ("Overwatch_bMzBrYEn8M", "enemy", 1, "Tracer"),
    ("Overwatch_bMzBrYEn8M", "enemy", 2, "Cassidy"),
    # EN-4: dark skin, wide grin, short hair — uncertain
    ("Overwatch_bMzBrYEn8M", "enemy", 4, "Kiriko"),

    # --- Overwatch_glEGeuSkaU ---
    ("Overwatch_glEGeuSkaU", "my",    0, "Baptiste"),
    ("Overwatch_glEGeuSkaU", "my",    1, "Ashe"),
    ("Overwatch_glEGeuSkaU", "my",    2, "Widowmaker"),
    ("Overwatch_glEGeuSkaU", "my",    3, "Kiriko"),
    # MY-5: dark-skinned, white outfit — uncertain
    ("Overwatch_glEGeuSkaU", "enemy", 0, "Baptiste"),
    ("Overwatch_glEGeuSkaU", "enemy", 1, "Moira"),
    ("Overwatch_glEGeuSkaU", "enemy", 2, "Mei"),
    ("Overwatch_glEGeuSkaU", "enemy", 3, "Kiriko"),
    # EN-5: young dark-haired man — uncertain

    # --- Overwatch_Q6vAdOYyVP ---
    ("Overwatch_Q6vAdOYyVP", "my",    0, "Venture"),
    ("Overwatch_Q6vAdOYyVP", "my",    1, "Moira"),
    ("Overwatch_Q6vAdOYyVP", "my",    2, "Mei"),
    # MY-4: teal diagonal visor — uncertain (recurring unknown)
    ("Overwatch_Q6vAdOYyVP", "my",    4, "Junker Queen"),
    ("Overwatch_Q6vAdOYyVP", "enemy", 0, "Reaper"),   # skull/bone skin, dark cloak with skull motif
    ("Overwatch_Q6vAdOYyVP", "enemy", 1, "Cassidy"),
    # EN-3: Moira (already covered)
    # EN-4: uncertain
    ("Overwatch_Q6vAdOYyVP", "enemy", 4, "Kiriko"),

    # --- Overwatch_RsmH1RshlB ---
    ("Overwatch_RsmH1RshlB", "my",    0, "Zarya"),
    ("Overwatch_RsmH1RshlB", "my",    1, "Cassidy"),
    ("Overwatch_RsmH1RshlB", "my",    2, "Reaper"),
    ("Overwatch_RsmH1RshlB", "my",    3, "Kiriko"),
    ("Overwatch_RsmH1RshlB", "my",    4, "Junker Queen"),
    # EN-1: gray armored figure — uncertain (Bastion? Roadhog?)
    ("Overwatch_RsmH1RshlB", "enemy", 1, "Moira"),
    ("Overwatch_RsmH1RshlB", "enemy", 2, "Hanzo"),
    ("Overwatch_RsmH1RshlB", "enemy", 3, "Kiriko"),
    # EN-5: partially visible — uncertain

    # --- Overwatch_SlCTA43i5k ---
    ("Overwatch_SlCTA43i5k", "my",    0, "Zarya"),
    ("Overwatch_SlCTA43i5k", "my",    1, "Ashe"),
    ("Overwatch_SlCTA43i5k", "my",    2, "Mei"),
    # MY-4: uncertain
    ("Overwatch_SlCTA43i5k", "my",    4, "Kiriko"),
    # EN-*: mostly partially visible

    # --- Overwatch_sM0bnxZLVF ---
    ("Overwatch_sM0bnxZLVF", "my",    0, "Zarya"),
    ("Overwatch_sM0bnxZLVF", "my",    1, "Mauga"),
    ("Overwatch_sM0bnxZLVF", "my",    2, "Cassidy"),
    # MY-4: teal diagonal visor — uncertain
    ("Overwatch_sM0bnxZLVF", "my",    4, "Kiriko"),
    ("Overwatch_sM0bnxZLVF", "enemy", 0, "Zarya"),
    ("Overwatch_sM0bnxZLVF", "enemy", 1, "Mauga"),
    ("Overwatch_sM0bnxZLVF", "enemy", 2, "Lucio"),
    ("Overwatch_sM0bnxZLVF", "enemy", 3, "Kiriko"),
    # EN-5: uncertain

    # --- Overwatch_TUCPtQoIBG ---
    ("Overwatch_TUCPtQoIBG", "my",    0, "Zarya"),
    ("Overwatch_TUCPtQoIBG", "my",    1, "Soldier 76"),
    ("Overwatch_TUCPtQoIBG", "my",    2, "Moira"),
    ("Overwatch_TUCPtQoIBG", "my",    3, "Baptiste"),
    # MY-5: teal diagonal visor — uncertain
    ("Overwatch_TUCPtQoIBG", "enemy", 0, "Wrecking Ball"),
    ("Overwatch_TUCPtQoIBG", "enemy", 1, "Moira"),
    ("Overwatch_TUCPtQoIBG", "enemy", 2, "Widowmaker"),
    ("Overwatch_TUCPtQoIBG", "enemy", 3, "Brigitte"),
    ("Overwatch_TUCPtQoIBG", "enemy", 4, "Kiriko"),

    # --- Overwatch_xXm7xbfyho ---
    ("Overwatch_xXm7xbfyho", "my",    0, "Venture"),
    ("Overwatch_xXm7xbfyho", "my",    1, "Moira"),
    ("Overwatch_xXm7xbfyho", "my",    2, "Mei"),
    # MY-4: teal diagonal visor — uncertain
    ("Overwatch_xXm7xbfyho", "my",    4, "Junker Queen"),
    ("Overwatch_xXm7xbfyho", "enemy", 0, "Roadhog"),  # yellow/green round gas mask, orange lens
    ("Overwatch_xXm7xbfyho", "enemy", 1, "Moira"),
    ("Overwatch_xXm7xbfyho", "enemy", 2, "Cassidy"),
    # EN-4: teal visor — uncertain
    ("Overwatch_xXm7xbfyho", "enemy", 4, "Kiriko"),

    # --- Overwatch_ZGLCFsiOih ---
    ("Overwatch_ZGLCFsiOih", "my",    0, "Baptiste"),
    ("Overwatch_ZGLCFsiOih", "my",    1, "Moira"),
    ("Overwatch_ZGLCFsiOih", "my",    2, "Junkrat"),
    # MY-4: uncertain
    ("Overwatch_ZGLCFsiOih", "my",    4, "Kiriko"),
    # EN-1, EN-2: uncertain
    # EN-3: uncertain
    ("Overwatch_ZGLCFsiOih", "enemy", 3, "Kiriko"),
    ("Overwatch_ZGLCFsiOih", "enemy", 4, "Junker Queen"),

    # --- Overwatch_zRPTVNorq2 ---
    ("Overwatch_zRPTVNorq2", "my",    0, "Zarya"),
    # MY-2: dark red/maroon hair, yellow eyes — uncertain (Hazard? Moira skin?)
    ("Overwatch_zRPTVNorq2", "my",    2, "Moira"),
    ("Overwatch_zRPTVNorq2", "my",    3, "Kiriko"),
    ("Overwatch_zRPTVNorq2", "my",    4, "Soldier 76"),
    # EN-1, EN-2: uncertain
    # EN-3: Moira (already covered)
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
