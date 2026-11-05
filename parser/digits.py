"""Reads scoreboard numbers by matching each digit against stored images of 0-9.

Scoreboard digits are about 12px tall at 1080p, small enough that Tesseract drops one
"1" of an "11" and misses a dim grey "0" entirely. The game draws them in one font,
so splitting a cell into its glyphs and matching each against templates is exact
where Tesseract guesses. Templates live in data/digits/ (built by
build_digit_templates.py from saved games); without them read_cell returns None and
the caller falls back to Tesseract.
"""
from pathlib import Path

import numpy as np
from PIL import Image

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "data" / "digits"
GLYPH_W, GLYPH_H = 12, 14  # every glyph is scaled to GLYPH_H tall and centred GLYPH_W wide
MIN_CONTRAST = 50  # brightest pixel this far above the background, or the cell is empty
MIN_SCORE = 0.75  # correlation below this is not a confident digit (touching pairs score ~0.8)
MIN_MARGIN = 0.04  # ...nor is one this close to the runner-up digit
MAX_TOUCHING = 3  # the most digits seen drawn touching; a wider blob is not a number

_templates: dict[int, np.ndarray] | None = None


def _load_templates() -> dict[int, np.ndarray]:
    global _templates
    if _templates is None:
        _templates = {}
        for d in range(10):
            path = TEMPLATE_DIR / f"{d}.png"
            if path.is_file():
                _templates[d] = _normalise(np.asarray(Image.open(path).convert("L"), dtype=np.float32))
    return _templates


def _normalise(a: np.ndarray) -> np.ndarray:
    a = a - a.mean()
    n = np.linalg.norm(a)
    return a / n if n else a


def _components(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Bounding boxes (x1, y1, x2, y2) of 8-connected ink blobs, left to right."""
    import cv2
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    boxes = [(x, y, x + w, y + h) for x, y, w, h, _ in stats[1:n]]
    return sorted(boxes)


def glyphs(cell: Image.Image) -> list[np.ndarray]:
    """Split a scoreboard cell into one grayscale array per digit, left to right.
    Commas (short blobs low in the cell) and specks are dropped; two digits drawn
    touching are split at the faintest column between them."""
    g = np.asarray(cell.convert("L"), dtype=np.float32)
    if g.size == 0:
        return []
    bg = float(np.median(g))
    top = float(g.max())
    if top - bg < MIN_CONTRAST:
        return []
    # Halfway between the background and the brightest ink: white digits and the dim grey
    # "0" both clear it, and the dark strip past the panel's edge never does.
    mask = g > (bg + top) / 2
    boxes = _components(mask)
    if not boxes:
        return []
    tall = max(y2 - y1 for _, y1, _, y2 in boxes)
    if tall < 0.15 * g.shape[0]:
        return []
    digits = [b for b in boxes if (b[3] - b[1]) >= 0.7 * tall]
    pitch = tall * 0.75  # a digit is about 3/4 as wide as tall; two touching ones twice that
    out = []
    for x1, y1, x2, y2 in digits:
        w = x2 - x1
        parts = max(1, round(w / pitch)) if w > 1.4 * pitch else 1
        if parts > MAX_TOUCHING:  # a bar or banner, not digits: the cell can't be read
            return []
        out.extend(_split(g[y1:y2, x1:x2], parts))
    return out


def _split(blob: np.ndarray, parts: int) -> list[np.ndarray]:
    """Cut a blob of `parts` touching digits where the pieces match the templates best
    (or, with no templates yet, at the faintest columns)."""
    if parts == 1:
        return [blob]
    w = blob.shape[1]
    templates = _load_templates()
    best = None
    first = blob[:, : w // parts]
    for cut in range(max(2, int(w / parts * 0.6)), min(w - 2, int(w / parts * 1.4)) + 1):
        left, rest = blob[:, :cut], blob[:, cut:]
        tail = _split(rest, parts - 1)
        if len(templates) == 10:
            score = classify(left, templates)[1] + sum(classify(t, templates)[1] for t in tail)
        else:
            score = -float(blob[:, cut].sum())
        if best is None or score > best[0]:
            best = (score, [left] + tail)
    return best[1] if best else [first]


def _resize(glyph: np.ndarray) -> np.ndarray:
    """Scale to GLYPH_H tall keeping the glyph's own width, centred on a GLYPH_W canvas,
    so a narrow "1" isn't stretched (a 1px wider box would change it by a quarter)."""
    h, w = glyph.shape
    new_w = max(1, min(GLYPH_W, round(w * GLYPH_H / h)))
    im = Image.fromarray(np.clip(glyph, 0, 255).astype(np.uint8)).resize((new_w, GLYPH_H), Image.BILINEAR)
    canvas = np.full((GLYPH_H, GLYPH_W), float(np.percentile(glyph, 10)), dtype=np.float32)
    x = (GLYPH_W - new_w) // 2
    canvas[:, x:x + new_w] = np.asarray(im, dtype=np.float32)
    return canvas


def classify(glyph: np.ndarray, templates: dict[int, np.ndarray]) -> tuple[int | None, float]:
    """Best-matching digit and its correlation, or (None, score) if not confident."""
    v = _normalise(_resize(glyph))
    scores = sorted(((float((v * t).sum()), d) for d, t in templates.items()), reverse=True)
    best, digit = scores[0]
    runner = scores[1][0] if len(scores) > 1 else -1.0
    if best < MIN_SCORE or best - runner < MIN_MARGIN:
        return None, best
    return digit, best


def read_cell(cell: Image.Image) -> int | None:
    """The number in one scoreboard cell, or None if it can't be read with confidence
    (no templates, an empty cell, or any glyph that doesn't clearly match a digit)."""
    templates = _load_templates()
    if len(templates) < 10:
        return None
    parts = glyphs(cell)
    if not parts:
        return None
    digits = []
    for glyph in parts:
        d, _ = classify(glyph, templates)
        if d is None:
            return None
        digits.append(str(d))
    return int("".join(digits))
