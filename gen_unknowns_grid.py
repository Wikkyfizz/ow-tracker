"""
Generate a compact numbered grid of all unidentified portrait slots from sheets 9-16.
Run: venv/Scripts/python.exe gen_unknowns_grid.py
"""
import sys
from pathlib import Path
import cv2
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))

from parser.icons import extract_portrait_crop, CANONICAL_W, CANONICAL_H
from save_portrait_templates import LABELS

INBOX = Path(r"E:\Claude stuff\OW screenshots")
OUT   = Path(r"E:\Claude stuff\OW screenshots\portrait_library\unknowns_grid.png")
OUT.parent.mkdir(parents=True, exist_ok=True)

SHEETS = [
    ("Overwatch_Q6vAdOYyVP", 9),
    ("Overwatch_RsmH1RshlB", 10),
    ("Overwatch_SlCTA43i5k", 11),
    ("Overwatch_sM0bnxZLVF", 12),
    ("Overwatch_TUCPtQoIBG", 13),
    ("Overwatch_xXm7xbfyho", 14),
    ("Overwatch_ZGLCFsiOih", 15),
    ("Overwatch_zRPTVNorq2", 16),
]

confirmed = {(stem, team, row) for stem, team, row, _hero in LABELS}

ZOOM   = 4
CW, CH = CANONICAL_W * ZOOM, CANONICAL_H * ZOOM
PAD    = 6
COLS   = 6
LBL_H  = 16

unknowns = []
for stem, sheet_num in SHEETS:
    img_path = INBOX / f"{stem}.png"
    if not img_path.exists():
        print(f"MISSING: {img_path.name}")
        continue
    for team in ("my", "enemy"):
        for row in range(5):
            if (stem, team, row) not in confirmed:
                crop = extract_portrait_crop(str(img_path), team, row)
                if crop is not None:
                    unknowns.append((len(unknowns) + 1, sheet_num, team, row, crop))

print(f"{len(unknowns)} unknown slots across sheets 9-16")

rows_count = (len(unknowns) + COLS - 1) // COLS
sheet_w = COLS * (CW + PAD) + PAD
sheet_h = rows_count * (CH + LBL_H + PAD) + PAD
canvas = Image.new("RGB", (sheet_w, sheet_h), (20, 20, 20))
draw   = ImageDraw.Draw(canvas)

for i, (n, sheet_num, team, row, crop_bgr) in enumerate(unknowns):
    crop_rgb = cv2.cvtColor(
        cv2.resize(crop_bgr, (CW, CH), interpolation=cv2.INTER_LANCZOS4),
        cv2.COLOR_BGR2RGB,
    )
    col = i % COLS
    r   = i // COLS
    x = PAD + col * (CW + PAD)
    y = PAD + r  * (CH + LBL_H + PAD) + LBL_H
    canvas.paste(Image.fromarray(crop_rgb), (x, y))
    team_str = "MY" if team == "my" else "EN"
    color    = (100, 200, 255) if team == "my" else (255, 110, 110)
    draw.text((x + 2, y - LBL_H + 2), f"#{n} S{sheet_num} {team_str}-{row+1}", fill=color)

canvas.save(str(OUT))
print(f"Saved: {OUT}\n")
for n, sheet_num, team, row, _ in unknowns:
    print(f"  #{n:2d}  Sheet {sheet_num}  {'MY' if team=='my' else 'EN'}-{row+1}")
