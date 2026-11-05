"""Builds data/digits/0.png ... 9.png, the digit images parser/digits.py matches against.

Every saved game's TEAM screenshot is cut into stat cells; a cell whose glyph count
equals the saved value's digit count labels each glyph with its digit. Each template is
the average of its glyphs. Afterwards every glyph is read back with the new templates,
and any that disagree with their label are listed: they are either a misread saved
value or a glyph the reader would get wrong.
Run: venv/Scripts/python.exe build_digit_templates.py
"""
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

import db
import local_paths
from parser import digits
from parser.ocr import ROW_HALF_H_FRAC, STAT_COLS_FRAC, _find_row_centers


def find_screenshot(saved: str) -> Path | None:
    inbox = local_paths.inbox()
    name = Path(saved).name
    for path in (Path(saved), inbox / "processed" / name, inbox / "discarded" / name):
        if saved and path.is_file():
            return path
    return None


def cells():
    """(label, glyph array, where) for every glyph of every saved cell that splits cleanly."""
    with db.get_conn() as conn:
        games = conn.execute("SELECT id, screenshot_path FROM matches ORDER BY id").fetchall()
        for game_id, shot in games:
            path = find_screenshot(shot or "")
            if path is None:
                continue
            img = Image.open(path).convert("RGB")
            w, h = img.size
            measured = _find_row_centers(np.asarray(img)[:, :, ::-1], w, h)
            if not measured:
                continue
            half = int(ROW_HALF_H_FRAC * h)
            rows = conn.execute("SELECT team, slot, stats FROM match_participants WHERE match_id=?",
                                (game_id,)).fetchall()
            for team, slot, stats in rows:
                ys = measured[0 if team == "ally" else 1]
                if slot >= len(ys):
                    continue
                cy = ys[slot]
                for stat, value in json.loads(stats).items():
                    if value is None or stat not in STAT_COLS_FRAC:
                        continue
                    xl, xr = STAT_COLS_FRAC[stat]
                    cell = img.crop((int(xl * w), cy - half, int(xr * w), cy + half))
                    parts = digits.glyphs(cell)
                    text = str(value)
                    if len(parts) != len(text):
                        continue
                    for ch, glyph in zip(text, parts):
                        yield int(ch), glyph, f"game {game_id} {team} row {slot + 1} {stat}={value} ({path.name})"


def build():
    samples = defaultdict(list)
    for label, glyph, where in cells():
        samples[label].append((digits._resize(glyph), glyph, where))
    missing = [d for d in range(10) if not samples[d]]
    if missing:
        raise SystemExit(f"No samples of digit(s) {missing}: log more games first.")
    digits.TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    for d in range(10):
        mean = np.mean([s[0] for s in samples[d]], axis=0)
        Image.fromarray(np.clip(mean, 0, 255).astype(np.uint8)).save(digits.TEMPLATE_DIR / f"{d}.png")
    digits._templates = None
    templates = digits._load_templates()
    disagree = []
    for d in range(10):
        ok = 0
        for _, glyph, where in samples[d]:
            got, score = digits.classify(glyph, templates)
            if got == d:
                ok += 1
            else:
                disagree.append((d, got, round(score, 3), where))
        print(f"{d}: {len(samples[d])} glyphs, {ok} read back as {d}")
    for d, got, score, where in disagree:
        print(f"  labelled {d}, read {got} (score {score}): {where}")


if __name__ == "__main__":
    build()
