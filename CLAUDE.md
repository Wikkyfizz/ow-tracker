# OW Tracker — Claude Context

Quick-reference for any new session. Read this before touching code.

---

## Stack

- **Backend:** Python 3.12, FastAPI, uvicorn, SQLite (`ow_tracker.db`)
- **Frontend:** Vanilla JS SPA (`static/index.html`, `static/app.js`, `static/style.css`). No build step.
- **Parser:** `parser/` — Python package. OCR via Tesseract + pytesseract. Template matching via OpenCV.
- **Python runtime:** Always use `venv/Scripts/python.exe`. System `py` is 3.8 where `parser` conflicts with a stdlib C module.

---

## Hero data — single source of truth

`data/heroes.csv` is the authoritative hero roster. The database (`ow_tracker.db`) is seeded from it via `db.py`.

**Name discrepancies between CSV and code:**

| CSV name | Code name (templates, HERO_ROLES) | Why |
|---|---|---|
| `Soldier: 76` | `Soldier 76` | Slug compatibility |
| `Torbjörn` | `Torbjorn` | ASCII-only slug |
| `D.Va` | `D Va` | Slug `d_va` matches either |

`parser/icons.py` loads `HERO_ROLES` dynamically from `heroes.csv` at import time (with `_CSV_NAME_ALIASES` for the three above). If CSV is unavailable, a hardcoded fallback is used. **Do not add heroes to the hardcoded fallback — add them to `heroes.csv` only.**

---

## Template matching pipeline

### How it works

1. Screenshot is loaded as BGR image via OpenCV
2. `parser/ocr.py:row_slots()` computes the 10 portrait slot bounding boxes (5 my-team, 5 enemy-team) using resolution-independent fractions, refined by `_refine_row_center()`
3. `parser/icons.py:_match_slot()` extracts each portrait crop (70×56 px canonical size), filtered to heroes with the correct role, then scores against saved templates using normalized cross-correlation
4. Best match above threshold is returned as the detected hero

### Slot order

Both teams follow: **slot 0 = tank, slots 1–2 = dps, slots 3–4 = support**

This is enforced by `SLOT_ROLES` in `icons.py`. Templates in `parser/portraits/my/` and `parser/portraits/enemy/` are filtered by this role before scoring.

### Template naming

Template files: `parser/portraits/{my|enemy}/{hero_slug}.png`

Slug function: `re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")`

Examples:
- `Zarya` → `zarya.png`
- `Junker Queen` → `junker_queen.png`
- `Soldier 76` → `soldier_76.png`
- `D Va` → `d_va.png`
- `Jetpack Cat` → `jetpack_cat.png`

### Known issues

**Tank slot crop quality (slot 0 on both teams):** When a player has a title badge displayed, the portrait thumbnail is pushed up, cutting off the bottom of the portrait. `_refine_row_center()` partially compensates but tank-slot crops remain lower quality than others. Avoid saving templates from tank-slot crops if the bottom is visibly cut off.

**enemy/lucio.png:** The saved template came from a DPS slot (wrong position for a support hero). Delete and re-save from a confirmed support slot.

**Template count (as of 2026-06-27):** 24 MY / 24 ENEMY templates saved. ~28 heroes per team still missing templates. These return low-confidence matches until templates are added.

### Template library tools

- `save_portrait_templates.py` — batch-saves templates from labeled screenshots using `LABELS` dict
- `build_portraits.py` — interactive tool: `--missing` lists heroes with no template, `--sheet` generates review sheets
- `gen_unknowns_grid.py` — generates a compact grid of unconfirmed portrait crops for identification

---

## Parser pipeline

`parser/pipeline.py:parse_screenshot(path, username="DROWZY")` is the main entry point.

- Calls `parser/ocr.py:detect_tab()` to identify which screenshot type was dropped
- Dispatches to `_parse_summary_tab()`, `_parse_team_tab()`, or `_parse_personal_tab()`
- **SUMMARY tab:** reads map name, outcome, date/time, game mode from fixed OCR regions
- **TEAM tab:** reads all 10 rows of stats (E/A/D/dmg/heal/mit) + calls `extract_heroes()` for portrait matching
- **PERSONAL tab:** stub only — not yet implemented

Tab detection order: PERSONAL first (its region overlaps SUMMARY), then SUMMARY, then TEAM.

### `my_heroes` vs `my_team_heroes` (data model — important)

- **`my_heroes`** = the hero(es) *the user* played, playtime-weighted (`pct`). This is the ONLY field that drives hero win-rate analytics. Never put teammates here.
- **`my_team_heroes`** = the user's full 5-hero team comp. Used *only* to derive `my_comp`. Not counted toward the user's hero record.
- **`enemy_heroes`** = the enemy's full 5-hero comp (drives `enemy_comp` + vs-enemy analytics).

The TEAM scoreboard gives the full team comp but **cannot identify which slot is the user** — every name OCRs to `""` (stylised own-name banner + CJK teammate names). So `_parse_team_tab` puts the 5 detected my-team heroes in `my_team_heroes` and leaves `my_heroes` **empty**; the user picks their played hero explicitly in the Queue review. (Auto-filling `my_heroes` would require a **new SUMMARY-tab portrait template library** — the SUMMARY "HEROES PLAYED" panel shows the user's heroes + exact pcts, but its round thumbnails don't match the rectangular scoreboard templates, and its hero-name text is unreadable by Tesseract (styled font). This is the natural next feature.)

### OCR performance (TEAM stat grid)

`ocr._ocr_team_numbers_fast()` reads all 30 numbers of a 5-row team block in **one** Tesseract `image_to_data` pass, binning digit-words by row (y) and column (x). Only empty cells fall back to the slow multi-strategy `_ocr_number`. ~6× faster than the old per-cell approach *and* more accurate (reads dim "0"s and comma numbers the per-cell path missed). `extract_all_rows(img, read_names=False)` skips the ~2s of per-row name OCR — the pipeline passes `read_names=bool(tracked_players)` since names are only useful for tracked-player matching.

### Timestamps

All timestamps are **naive LOCAL time** (OCR reads the game's local clock; the server stamps `datetime.now()`; the frontend sends the `datetime-local` value as-is). Do not reintroduce `utcnow()` / `toISOString()` — mixing frames breaks session idle-close math and chronological ordering.

Result is written to `inbox_queue.json` for Queue UI review.

---

## Key coordinates (1920×1080 base, stored as fractions)

Portrait X span: `558/1920` to `628/1920`

My team portrait Y centers (approx): 270, 338, 406, 474, 542 px

Enemy team portrait Y centers (approx): 688, 756, 824, 892, 960 px

All coordinates in `parser/ocr.py` as `*_FRAC` constants.

---

## Database

Schema in `db.py`. Key tables:
- `matches` — one row per game
- `match_participants` — one row per player (10 per match; used for full team comp storage)
- `sessions` — play sessions
- `heroes` — seeded from `heroes.csv` (Damage/Support/Tank roles, CSV names)
- `maps` — seeded from `data/maps.csv`

Note: `heroes` table uses CSV names ("Soldier: 76", "Torbjörn", "D.Va"). Template slugs use code names. When looking up heroes across these two systems, use the `_CSV_NAME_ALIASES` from `icons.py` or query the DB by slug.

---

## Inbox and queue

- Inbox folder: `E:\Claude stuff\OW screenshots` (from `settings.json`)
- Queue state: `inbox_queue.json` in project root
- Watchdog watches inbox folder; new screenshots are auto-parsed into the queue
- Queue UI (`#page-queue`) shows parsed data for user review + submit

---

## Active work as of 2026-06-27

- Branch: `feature/ocr-calibration` (not yet committed — pending this session)
- Template matching 93% accuracy on confirmed screenshot set (28/30)
- Design doc for Queue hero correction panel: `docs/hero-detection-design.md`
- PERSONAL tab parsing: stub only — major future feature, do not implement yet
- UI overhaul design: `docs/ui-overhaul.md` — decisions pending, do not implement yet
