# Hero Detection Design — Three Approaches

**Status:** DECISION PENDING (do not implement until approved by Brandon)

**Problem:** The TEAM tab scoreboard shows hero portraits as icons only — no text names for teammates or enemies. Template matching (normalized cross-correlation on 70×56 portrait crops) handles this, but has two gaps:

1. **Missing templates** — ~28 of 52 heroes per team still have no saved template; detection falls back to the nearest wrong match
2. **Tank slot crop quality** — slot 0 (both teams) is frequently clipped when players have title banners, producing unreliable crops

The system currently returns the best-scoring template even at low confidence, which means wrong guesses propagate silently into the DB.

---

## Constraints

- **Time budget:** Hero input must add seconds to the Queue review step, not minutes
- **Queue step:** Already designed for ~15 seconds total per game. Hero correction fits here; a separate hero-entry flow does not
- **OCR is not viable for hero names** — names only appear as text for the user's own hero (SUMMARY tab), not for all 10 players
- **Template icons are skin-independent** — scoreboard portraits do not change with cosmetic skins; templates are reliable once saved

---

## Approach A — Confidence Thresholding + Gradual Library Growth

**What it is:** Improve template matching quality, add confidence thresholds, and let the library grow naturally as more games are played.

**Changes:**
- `_match_slot()`: if `best_score < CONFIDENCE_THRESHOLD` (e.g. 0.65), return `"Unknown [Tank]"` / `"Unknown [DPS]"` / `"Unknown [Support]"` rather than the wrong hero
- Queue UI shows "Unknown [Support]" as an explicit flag rather than a silently wrong hero name
- User manually corrects unknowns in the existing Queue text fields
- No automatic template saving

**Pros:**
- Minimal code change
- Stops wrong data from entering the DB silently
- Works today

**Cons:**
- Large fraction of games will have "Unknown" slots for the next few months until templates accumulate
- No mechanism to actually build the library except running `save_portrait_templates.py` manually
- User corrects unknowns via a text field with no visual aid — slower and more error-prone than necessary
- Tank slot quality issue is unaddressed

**Verdict:** Good as a **safety improvement** (add confidence thresholding regardless), but insufficient as the primary approach.

---

## Approach B — Queue Hero Correction Panel (Recommended)

**What it is:** Auto-detect heroes with template matching and show all 10 portrait crops in the Queue review step. Low-confidence slots are highlighted. User clicks to correct any wrong slot, and confirmed corrections automatically save new templates — making the library self-improving from regular play.

**How the Queue hero panel works:**
1. When a TEAM tab screenshot is parsed, the parser extracts per-slot confidence alongside the hero name
2. The Queue item grows a "Team Comp" panel showing two rows of 5 portraits (my team / enemy team)
3. Each portrait thumbnail comes from the original screenshot (served by a new backend endpoint)
4. Low-confidence slots (< 0.75) are highlighted with an amber border + "?" badge
5. User clicks any portrait to open a role-filtered hero picker (only shows valid heroes for that slot's role)
6. On Queue submit, any correction where the original confidence was low triggers a `POST /api/heroes/template` call that saves the portrait crop as a new template

**Time cost:** 0–5 seconds per game. If auto-detection is correct (93%+ on known heroes), the user just glances at the panel and hits submit. Corrections are one click each.

**Self-improvement loop:**
- Game N: hero X has no template → shows "Unknown [DPS]" → user clicks → selects hero X → crop saved as template
- Game N+1 onward: hero X auto-detects correctly → no click needed
- After ~50 games across the full hero roster, template coverage approaches 100%

### Backend changes

**`parser/icons.py` — per-slot confidence return:**
```python
def extract_heroes(img_path: str) -> dict:
    # Change my_heroes return from ["Zarya", ...] to:
    # [{"hero": "Zarya", "confidence": 0.95, "role": "tank"}, ...]
    # Keep overall "confidence" as average. Add per-slot data.
    # If best_score < CONFIDENCE_THRESHOLD (0.65): hero = "Unknown [Tank/DPS/Support]"
```

**`parser/pipeline.py` — thread through per-slot confidence:**
- `_parse_team_tab()` currently unpacks `icon_result.get("my_heroes", [])` as a flat list
- Update to pass the full list-of-dicts through to the queue item

**New endpoint: `GET /api/queue/{filename}/portrait/{team}/{row}`**
- `team`: `"my"` or `"enemy"`, `row`: 0–4
- Extracts the portrait crop from the original screenshot (call `extract_portrait_crop()` from `parser/icons.py`)
- Returns PNG bytes, scaled to 140×112 for legible display
- Screenshot must still exist at its original path (stored in queue item)

**New endpoint: `POST /api/heroes/template`**
```json
{ "filename": "Overwatch_abc123.png", "team": "my", "row": 2, "hero": "Tracer" }
```
- Extracts portrait crop from screenshot, saves to `parser/portraits/{team}/{slug}.png`
- Calls `_portrait_cache.clear()` (or reload flag) so the cache picks up the new template
- Returns `{"saved": true, "path": "parser/portraits/my/tracer.png"}`

**Queue submit endpoint — accept hero overrides:**
Current submit body: `{map, outcome, rank_tier, rank_division, notes, bans, ...}`
New additions:
```json
{
  "my_heroes_confirmed": [{"hero": "Zarya", "confidence": 0.95, "corrected": false}, ...],
  "enemy_heroes_confirmed": [...]
}
```
When `corrected: true` AND original confidence < 0.75 → call template-save logic before committing the match.

### Frontend changes (`static/`)

**Queue item expansion — add Team Comp panel:**

```
[ MY TEAM ]
  [portrait] [portrait] [portrait] [portrait] [portrait]
   Zarya      Cassidy    Tracer     Kiriko    Mizuki
   tank 0.95  dps 0.91   dps 0.88   supp 0.82  supp 0.79

[ ENEMY TEAM ]
  [portrait] [portrait] [portrait] [portrait] [portrait]
   Sigma      ?          Cassidy    Mizuki     Kiriko
   tank 0.91  dps 0.43   dps 0.90   supp 0.88  supp 0.85
              (amber)
```

- Portrait images: `<img src="/api/queue/{filename}/portrait/{team}/{row}">` (lazy loaded)
- Slot with confidence < 0.75 gets `.hero-slot--uncertain` class (amber border + "?" badge)
- Click any slot → role-filtered hero picker overlay opens

**Hero picker component:**
- Filtered to the correct role (tank / dps / support) based on slot index
- Grid of hero name chips, grouped by role
- Heroes with templates show their portrait thumbnail (from `/api/queue/{filename}/portrait/...` OR static from `parser/portraits/`)
- Searchable by typing (simple substring filter on hero name)
- Click hero → slot updates, picker closes, slot marked as "corrected"

**Queue submit flow:**
- Collect `my_heroes_confirmed` / `enemy_heroes_confirmed` from the panel state
- Include in submit POST body
- On response success: any slots with `corrected: true` + low original confidence are saved as templates via `POST /api/heroes/template`

### Database changes

Add to matches table (via `_migrate_db`):
```sql
ALTER TABLE matches ADD COLUMN hero_confidence REAL DEFAULT NULL;
ALTER TABLE matches ADD COLUMN heroes_verified INTEGER DEFAULT 0;
```
- `hero_confidence`: average confidence score at save time (for future quality analysis)
- `heroes_verified`: 1 if user reviewed the hero panel in Queue, 0 if auto-accepted

### `_portrait_cache` invalidation

`parser/icons.py:_portrait_cache` is a module-level dict. After saving a new template, the running server needs to reload it. Options:
1. Simplest: clear `_portrait_cache["my"]` and `_portrait_cache["enemy"]` dicts in the template-save endpoint (force reload on next `extract_heroes` call)
2. Alternative: move to a function-level reload check (compare dir mtime)

Option 1 is fine. The cache is rebuilt on next parse (~50ms), which is acceptable.

---

## Approach C — Pre-game Hero Declaration

**What it is:** Before queuing for a game, user opens the app and clicks their hero in a hero-grid panel. At Queue time, only enemy slots need auto-detection. The user's own slot is always correct.

**How it works:**
- Session page gets a "Next game: pick your hero" button → opens hero grid
- Selected hero is held in local state (or server-side session)
- When screenshot is parsed, user's own slot is pre-filled from the declared hero
- Enemy slots go through template matching as normal

**Pros:**
- Own hero is always 100% accurate (critical for personal stats)
- No template needed for the user's own hero picks
- Simple to implement (hero grid already needed for Approach B's picker)

**Cons:**
- Requires a pre-game action that's easy to forget
- Does nothing for enemy comp (still needs template matching)
- Friction at game start (two steps: declare hero, then queue)
- If user switches hero mid-game, the declaration is wrong

**Verdict:** The pre-game action is forgettable and the benefit is narrow (own hero only). The SUMMARY tab already provides the user's hero from its "Heroes Played" section (it shows hero names as text for the user). Approach B covers the same accuracy improvement without the pre-game step.

---

## Recommendation: Approach B

The Queue Hero Correction Panel is the right system because:

1. **It's additive to existing workflow** — the Queue step is already the 15-second review touchpoint. Adding portrait display doesn't change the workflow structure.
2. **Self-improving** — every correction contributes a new template. By ~game 50, most heroes will have templates and corrections become rare.
3. **The visual aid matters** — showing the actual portrait crop makes hero identification fast even for unfamiliar heroes. A text dropdown without the image would be slower.
4. **Blocks wrong data** — confidence thresholding (part of B) replaces wrong guesses with explicit "Unknown [Role]" before user review, preventing silent garbage from entering the DB.
5. **Covers all 10 slots** — Approach C only helps with 1 slot (the user's own hero).

Approach A's confidence thresholding should be implemented as part of B (it's a 2-line change in `_match_slot`).

---

## Implementation sequence (for a future build session)

1. **`parser/icons.py`:** Add confidence thresholding (`CONFIDENCE_THRESHOLD = 0.65`). Update `extract_heroes()` to return list-of-dicts with per-slot confidence. Update `_match_slot()` to return "Unknown [Role]" below threshold.
2. **`parser/pipeline.py`:** Thread per-slot confidence data through `_parse_team_tab()`.
3. **`db.py`:** Add `hero_confidence` and `heroes_verified` columns in `_migrate_db`.
4. **`main.py`:** Add `GET /api/queue/{filename}/portrait/{team}/{row}` and `POST /api/heroes/template` endpoints. Update Queue submit endpoint to accept hero overrides and call template-save.
5. **`static/index.html` + `static/app.js`:** Add Team Comp panel to queue item. Build hero picker component. Wire portrait lazy-loading and submit flow.
6. **`static/style.css`:** `.hero-slot`, `.hero-slot--uncertain`, `.hero-picker` styles (consistent with existing dark token system).
7. Verify: parse a new screenshot → team comp panel shows in Queue → click an uncertain slot → pick hero → submit → verify template saved in `parser/portraits/`.

**Reference the `docs/ui-overhaul.md` token system** when building the styles. Role colors (`--tank`, `--dps`, `--support`) should be used for role indicators in the picker. Amber highlight for uncertain slots should NOT use a role color — it is a quality signal, not a data signal.
