# UI Pass 2 — Session cards + screenshot viewer

**Status: DONE (2026-07-05), e2e green (2/2). Uncommitted — awaiting Brandon's go-ahead to commit.**
Branch: `fix/data-integrity-and-perf` (built on top of the e2e-harness commit `5106237`).
Source of scope: vault memory `Personal-Vault/wiki/meta/memory/project_ow-tracker-ui-backlog.md`
(items 2 and 3; item 1 — hero icons — deliberately out of scope, needs an asset pipeline).

If a session dies mid-work: everything below is the full design. Check the checklist,
`git status`, and pick up at the first unchecked item.

---

## A. Session-card layout rework (backlog item 2 — "most urgent")

**Problem:** On the Sessions page, `.sess-hist-header` is a single flex row —
`title (flex:1) | W–L | WR | meta | chevron`. All info is 11–14px, crammed to the
edges, dead zone in the middle. Info should be bigger and fill the card width.

**Design:** header becomes a CSS grid, full-width, with labeled stat cells:

```
| Title            | 7W – 3L | 70%      | 10    | 2h 14m   | ▼ |
| Jun 27           | RECORD  | WIN RATE | GAMES | DURATION |   |
```

- `.sess-hist-id` (col 1): title 16px/600 + date sub-line 11px dim.
- 4 × `.sess-hist-stat`: value 16px `var(--font-m)` over 9px uppercase label.
  Record keeps `wr-good`/`wr-bad` coloring; WR keeps `wrClass(wr)`.
- Grid: `minmax(0,1.4fr) repeat(4, minmax(0,1fr)) 18px`, stats left-aligned in
  their tracks so they spread across the card.
- ≤640px media query: id block full row, stats wrap in a second row.

**Files:** `static/app.js` → `renderSessionHistCard()` (~line 407);
`static/style.css` → `.sess-hist-*` block (~line 786). The click-to-expand handler
binds to `.sess-hist-header` and the chevron/expanded classes stay — don't rename
`sess-hist-header`, `sess-hist-card`, `sess-hist-body`, `shc-`/`shb-` ids.

## B. Screenshot viewer in the game modal (backlog item 3)

**Problem:** OCR digits can be wrong (zeros/misreads) and there's no in-app way to
spot-check against the source screenshot while reviewing a queue item.

**Design:**
1. **Backend** — `GET /api/queue/{filename}/image` in `main.py` (put it next to the
   portrait-crop endpoint ~line 330). Look up the queue item by filename and serve
   its `path` bytes (`image/png`/`image/jpeg` by suffix, `Cache-Control: max-age=3600`).
   Fallback when not in queue: search inbox, `inbox/processed/`, `inbox/discarded/`
   by basename (use `Path(filename).name` to block traversal). 404 otherwise.
2. **Modal UI** — collapsible section at the top of `.modal-body` in `index.html`:
   toggle button "📷 Source screenshot" + hidden `<div>` with an `<img>`. Hidden by
   default (OCR-first per backlog); only rendered at all when the modal was opened
   from a queue item. `img.src` is set lazily on first expand. Click image → open
   `/api/queue/{fn}/image` in a new tab for full-size.
3. **JS state** — `pendingScreenshotPath` module var alongside `pendingQueueFilename`;
   `confirmQueueItem()` passes `_screenshotPath: item.path` in the prefill.

## C. Bug fix: screenshot_path never persisted (prereq the backlog anticipated)

**Bug (current behavior):** `saveModalGame()` never sends `screenshot_path`, so
(1) the match row loses its screenshot link forever, and (2) after save the frontend
calls `DELETE /api/queue/{fn}` whose handler archives the file to **`discarded/`** —
processed games' screenshots end up in the discard pile.

**Fix (frontend only; `POST /api/matches` already handles it):**
- payload gains `screenshot_path: pendingScreenshotPath || ''`.
- When `screenshot_path` is sent, the server itself dequeues + archives to
  `processed/` (main.py ~line 234) — so *skip* the frontend `api.delete` in that case
  (keep it as fallback when there's no path).
- **Order matters:** `saveHeroTemplates(fn)` must run **before** the POST — the
  server's dequeue would otherwise 404 the template-save's queue lookup, and the
  archive move would invalidate the crop source path.

## D. e2e safety + coverage

- **seed.mjs hazard:** it points the queue item at a REAL screenshot in
  `E:\Claude stuff\OW screenshots`; the save/discard flows MOVE that file into
  archive subfolders of the real folder. Fix: copy it into `.tmp/inbox/e2e-team.png`
  and reference the copy.
- Extend `data-integrity.spec.mjs` (or new spec): viewer toggle visible when opened
  from queue, image endpoint returns 200, after save the queue is empty and the
  screenshot landed in `.tmp/inbox/processed/`, and `match.screenshot_path` is set.
- Run: `cd e2e && npm test` (needs venv + node; see e2e/README.md).

## Checklist (update as you go)

- [x] Plan doc written
- [x] C: screenshot_path wired through save flow (app.js)
- [x] B1: image endpoint in main.py
- [x] B2/B3: modal viewer UI (index.html, style.css, app.js)
- [x] A: session-card grid layout (app.js + style.css)
- [x] D: seed.mjs generates a deterministic 1920×1080 black PNG in `.tmp/inbox`
      (the old hardcoded real-screenshot path had rotted → placeholder caused
      10× portrait-crop 500s; full-size black image crops cleanly); spec extended
- [x] e2e suite green (2/2 passed, 2026-07-05; visual screenshot reviewed)
- [x] CLAUDE.md "Active work" + vault `project_ow-tracker-ui-backlog.md` updated
- [ ] Committed (awaiting Brandon's go-ahead)
