# OW-Tracker UI Overhaul — Implementation Brief

**Status:** DRAFT v1 (2026-06-26). Written for a future build session with cold context.
Several decisions are flagged `[ASSUMPTION]` / `[DECIDE]` — these were grilled with Brandon
after this draft; update this doc with his answers before building. Do not start the build
until the `[DECIDE]` block at the bottom is resolved.

---

## 0. The one thing that matters

The reference apps (Leetify, Parsertime, dpm.lol, tracker.gg) are built on **rich data**:
CS2 demo files, the LoL/Valorant APIs, OW scrim "custom code" logs. Our data is **OCR-scraped
from end-of-game screenshots** — sparse, per-game, and only as reliable as the parser.

**Design for the data that exists, not the data the references show.** Every Leetify panel
that depends on round-by-round telemetry (clutch breakdowns, opening duels, 2D replay, aim
heatmaps) is **off the table** because that data does not exist for us and never will from a
screenshot. Copying those panels = empty cards = the app feels broken. The discipline of this
overhaul is to hit Leetify/Parsertime *polish* on the subset of data we actually have.

**Why sessions are the primary unit (Brandon's thesis — not a data-sparsity workaround):**
per-game data is reasonably rich and we WANT it richer (weapon accuracy, deaths/10, enemy comp
archetype, tank matchup, etc. — include these, don't strip them). Sessions are primary for a
*positive analytical* reason: OW games are short and **serially correlated** — each game affects
the next (tilt, momentum, a bad-aim day). Aggregating a session surfaces trends that a single
match hides, and it **reframes ranked play as deliberate practice sessions** rather than
just-playing. The session is the lens that makes short-game noise legible. So: keep per-game
detail rich, AND make the session the organizing container that reveals cross-game trends.

The competitive wedge: **Parsertime's ranked tracker has no numerical/matchup/comp data at all**
(it's a scrim tool; ranked is secondary). We already compute hero win rates, comp matchups,
enemy-hero matchups, bans, teammate splits. So the target is: *Parsertime's clean professional
aesthetic + Leetify's session/dashboard structure + analytics Parsertime doesn't have.* That's a
real, defensible niche.

---

## 1. Current state (what you're modifying, not building)

- **Stack:** vanilla JS SPA. `static/index.html` (single file, all pages as `.page` divs),
  `static/app.js`, `static/style.css`. Python/FastAPI backend (`main.py`, `db.py`, `models.py`,
  `parser/`). Chart.js 4.4 via CDN. No build step, no framework.
- **Branch:** build on top of `feature/ocr-and-sessions` (the OCR + sessions work). That branch
  heavily rewrote `app.js`/`index.html`/`style.css` (+874/+293/+252). **Do NOT start from
  `master`** or you'll fight a massive merge. Ideally this branch merges to master first, then
  the overhaul branches off master. Confirm merge state before starting.
- **IA already exists:** nav = Dashboard · Session · Queue · History · Analytics · Settings.
  Keep this IA. The overhaul restyles and restructures *within* it; it does not invent new pages.
- **Token system already exists** (`style.css` `:root`): dark (`--bg #060a11`), role palette
  (`--tank #38b2f0`, `--dps #f97316`, `--support #4ade80`, `--open #a78bfa`), win/loss/draw,
  fonts Barlow Condensed (display) / Inter (body) / IBM Plex Mono (numbers). **Keep and extend
  these tokens** — the overhaul refines, it does not throw them out. `[ASSUMPTION]`

### What's actually weak (the real targets)
1. **History** (`#page-history`) is a single dense `<table>` — 12 columns, no expand. This is the
   biggest gap vs every reference. → Convert to **expandable match cards**.
2. **Analytics** (`#page-analytics`) is 7 raw `<table>` tabs. Functional, ugly, no framing. →
   Convert to **question-driven sections with visualization** (Parsertime model).
3. **Dashboard** (`#page-dashboard`) is 6 stat cards + 2 charts + 2 tables. Fine, but not
   session-forward. → Lead with **recent sessions + recent form**, demote lifetime tables.
4. **Session detail** is functional (stats bar, games list) but visually flat vs Leetify's
   session grouping + highlights reel.
5. **No expand-on-click anywhere** — the single interaction the references all share and the one
   Brandon explicitly called out.

---

## 2. What we're borrowing, attributed

| Source | What to take | What to ignore |
|---|---|---|
| **Leetify** | Session-as-container model; the "VICTORY 13:10" result-card header (colored outcome + score + map thumb + micro-stats); the **collapsed→expanded match** pattern; dashboard "Recent Matches / Focus Areas / Recent Form" three-band layout; the highlights row at the top of a session. | Per-round telemetry panels, 2D replay, aim/utility deep-dives, achievement "card packs," coaching-video embeds. No data for these. |
| **Parsertime** | The whole **clean professional aesthetic**; **question-driven section headers** ("Where do you win most?", "Are you improving?", "Are you a one-trick?"); the reused **recent-matches list component** across tabs; the top **stat strip** (Matches / Winrate / Best Map / Streak); sub-tab nav within a section. | Its data sparsity — we want to *out-data* it. Its scrim/team features. |
| **dpm.lol** | **Expandable match rows** with win/loss color tint; the **rank/SR line graph**; restrained dense-but-clean dark styling. | The radial "DPM Lens" comparison web (over-engineered for our data); premium-gated panels. |
| **tracker.gg** | Win/loss **row tinting** (green win / red loss); left-rail aggregate summaries (top maps / heroes / roles). | The density/ad-heaviness/busyness — it's the *negative* example for "too much at once." |

---

## 3. Visual system (refine existing tokens)

- **Theme:** DARK ONLY (decided). Keep and refine the existing dark token system; no light mode.
- **Typography:** NEUTRAL SINGLE SANS (decided). **Barlow Condensed retires** — it's condensed
  (space-efficient but tight/small), which fights the "bigger, airier, Parsertime-like" goal.
  Move to one clean neutral sans (Inter or similar) across the app, scaled UP from current sizes.
  Nav (`nav h1`, `.nav-btn`), card `h2`, stat-card labels/values all currently use `--font-d`
  (Barlow) — migrate all to the new sans. IBM Plex Mono MAY stay for tabular numerics (alignment)
  — optional, decide during build.
- **Accent:** `--accent` is currently orange (`#f97316`) — but that *collides* with `--dps`
  orange, which weakens the role-as-data-encoding. `[DECIDE]` — pick a brand accent that is NOT a
  role color (so role colors stay meaningful as data), e.g. a magenta (Leetify) or cyan.
- **Role colors stay as data encoding only** — tank/dps/support/open should appear on hero chips,
  comp bars, role splits, never as generic UI chrome.
- **Card system:** keep the left-border accent card. Add an **expanded state** (the new core
  interaction): card shows a summary row; click expands a detail panel inline (accordion), not a
  modal. Match Leetify/dpm where the row stays in place and grows.
- **Aesthetic direction (Brandon, confirmed):** **Parsertime's clean professional base** + the
  **tighter, panel-based UI and expandable menus of Leetify/dpm**. Specifically: he likes
  **panel-based layouts** (discrete bordered panels grouping related info, not loose floating
  elements) and **larger icons/text than the current build** — the current design reads cramped
  and small. So scale up hero icons, stat values, section headers; group into clear panels.
- **Spacing/density:** Parsertime's generous whitespace is the target over tracker.gg's density.
  Brandon wants Parsertime's cleanliness but "more tightly organized" — aim for *organized
  density*: grouped into panels, labeled, breathing, but information-rich. Bigger type/icons,
  clear panel boundaries, no cramped tables.

---

## 3.5 Design-discipline layer (from the taste + frontend-design skills)

**Scope caveat:** the `design-taste-frontend` skill is built for landing pages/portfolios and
explicitly lists "dashboards / dense product UI / data tables" as out of scope. OW-Tracker is a
dense data product, so we take that skill's *universal principles* (anti-default discipline, AI-
tell bans, color/type calibration, a11y) and ignore its page-patterns (heroes, bento, marquees,
logo walls, scroll-telling). The `frontend-design` skill (distinctive type, signature element,
restraint) applies more fully.

**Implementation reality:** vanilla CSS/JS, no framework, no build. Adopt the *principles*, not
the React/Tailwind/Motion stack the taste skill assumes.

### Dials for THIS app (a tool, not a marketing page)
Landing-page baseline is `8/6/4`; a data tool is different:
- **VISUAL_DENSITY ≈ 6** — "daily app," panel-based density. Higher than a landing page (you want
  data), lower than tracker.gg's cockpit. Standard app spacing, grouped into panels.
- **MOTION_INTENSITY ≈ 2–3** — functional only: expand/collapse transitions, hover states, maybe a
  light load-in stagger. **No** scroll-telling, parallax, marquees. Over-animating a stat tool is
  itself an AI tell. Honor `prefers-reduced-motion`.
- **DESIGN_VARIANCE ≈ 3–4** — data UI wants predictable, scannable structure, not asymmetric art-
  direction. Consistency > surprise here.

### Type (refines the "neutral single sans" decision)
- The taste skill flags **Inter as the over-used default** — "neutral" doesn't have to mean Inter.
  Recommend **Geist** (clean, neutral, slightly more characterful than Inter) as the single sans,
  paired with **IBM Plex Mono retained for tabular numerics**. Geist + Plex Mono is a quiet
  signature pairing vs Inter-everywhere slop. `[DECIDE-minor]` — Geist vs another neutral grotesk.
- Scale UP from current sizes (Brandon's "bigger type/icons"). Control hierarchy with weight +
  size, not neon or all-caps Barlow.

### Color (locks)
- **One brand accent, locked across the whole app**, and it must be **desaturated (<~80% sat)** and
  **NOT a role color** (current `--accent` orange collides with `--dps` — fix). Avoid the AI tells:
  no purple-glow, no neon outer-glows, no oversaturated accent.
- **Role colors stay the data-encoding system** (tank/dps/support/open), used only on data, never
  as UI chrome. This is genuinely the app's existing "color system" — preserve it; the taste skill
  would call it the one locked palette.
- `--bg #060a11` is already off-black (good — skill bans pure `#000`). Keep the dark token base.
- **Shape consistency lock:** pick one corner-radius scale and apply everywhere (current cards use
  8px — keep one scale).

### Signature element (frontend-design's core ask: one memorable thing)
A product still needs a signature, and ours should *be the thesis made visual*, not decoration:
**a session "momentum spine"** — a compact visual of the session's game sequence (W/L run, SR
delta, and a tilt/heat indicator) that makes serial correlation legible at a glance. It appears on
the session card (collapsed) and expands into the per-game breakdown. This is the one place to
"spend boldness"; everything else stays quiet and disciplined. It encodes something true (games
affect each other) rather than ornamenting. `[DECIDE]` — is the momentum spine the right signature,
or is there a better single memorable element?

### Copy discipline (frontend-design)
- Question-headers (§4) stay **functional, not cute** — "Which comps beat you?" yes; performative-
  craftsman labels ("Field notes," "On the bench") no.
- Empty states give **direction** ("No sessions yet — start one to track a play block"), not mood.
- Name things from the player's side. **No em-dashes** in any UI copy (use `-` or restructure).

## 4. Core interaction patterns (new)

### 4.1 Progressive disclosure — the spine of the whole UI (Brandon's model)
The organizing principle is **drill-down, not cramming**. Core info first; detail on expand;
full data on a second expand. This is how we resolve the density question: stay clean and
big-type at each level, and earn density through depth rather than packing one screen. Brandon:
willing to sacrifice "tight" before "clean" or "big."

**Sessions — three levels:**
- **L0 — Session card (collapsed):** overall record (W-L), most-played heroes, rank change,
  focus goal, length. Plus the **momentum spine** signature (§3.5).
- **L1 — Match list (expand session):** DPM/Leetify-style row per match — hero played, role
  matchup, W/L, KDA, per-match goal/practice rating.
- **L2 — Match detail (expand a match):** full 10-player team lists with scoreboard stats, game
  notes, other heroes played, enemy comp, bans — everything we have for that match.

**Dashboard panels mirror the same pattern** (e.g. Heroes):
- **L0:** overall W/L, avg KD, hours played per hero.
- **L1 (expand):** all hero-related analytics — best matchups, comp win rates with/against, hero×
  map, etc.

Same accordion mechanic everywhere; no modal for *viewing* (modal stays for *entry/edit* only).

### 4.2 Question-driven analytics sections
Each analytics block gets a plain-language question header + a one-line answer sentence + the viz.
("Which comps beat you? You lose to Dive 62% of the time, most on control maps.") Parsertime's
single best idea, and free. Keep functional, not cute (§3.5 copy discipline).

### 4.3 Confidence tagging for low-n
Per the existing Phase-2 design (`wiki/personal/ow-tracker.md`), every analytic with thin sample
shows an explicit "low confidence (n=…)" tag — shown, not hidden (single-user tool keeps what
little signal exists). Bake into the shared component, not per-table.

---

## 5. Page-by-page spec

### Dashboard (`#page-dashboard`) — make it session-forward
- **Top stat strip** (keep, restyle to Parsertime): Total Games · Win Rate · Last 20 · Streak ·
  Best Hero · Best Map.
- **Band 1 — Recent Sessions** (NEW lead element): horizontal row of 2–3 recent session cards
  (date, duration, W-L pips, WR, SR delta, goal). Click → Session detail. This is the
  Leetify-style lead.
- **Band 2 — Recent Form:** SR Timeline chart (keep, it's already there) + a small "last 10 vs
  all-time WR" gauge (Parsertime "Are you improving?").
- **Band 3 — Lifetime context (demoted):** WR-by-map chart + tracked hero WR + OverFast baseline.
  Keep but move below the fold.

### Sessions — first-class, OWN NAV ITEM (decided)
- Add a dedicated **Sessions** nav item = a Leetify-style list of past sessions. Each session =
  an expandable card with a summary header (W-L pips, WR, SR Δ, best game, goal) that expands to
  its match list. This is the primary review surface (per the session-as-lens thesis in §0).
- The existing **Session page** keeps the *active/live* session only (start → in-progress →
  end). "Play now" (Session) and "review past" (Sessions) are separate because they want
  different layouts. Nav becomes: Dashboard · Session · **Sessions** · Queue · History · Analytics
  · Settings. `[DECIDE-minor]` — naming to avoid Session/Sessions confusion (e.g. "Live Session"
  vs "Sessions", or "Play" vs "Sessions").

### Session detail — Leetify session container
- Keep the live stats bar (Games/Wins/Losses/WR/Rank Δ/Duration) — it's good.
- Add a **session header** with outcome summary + (optional) a "best game this session" highlight.
- Convert "Games This Session" list rows to the **expandable match card** component (shared with
  History).

### History (`#page-history`) — the flagship change
- Kill the 12-column table. Replace with a **vertical list of expandable match cards**:
  - **Collapsed:** outcome tint (left edge green/red/grey), map thumbnail, map name, mode,
    date, my hero icon(s), E/D (or KDA), SR delta chip.
  - **Expanded:** full 10-player scoreboard (we have this from TEAM-tab OCR), enemy comp +
    archetype, bans, my detailed stats (dmg/heal/mit), notes, practice rating if from a session.
- Keep the existing filters (Map / Outcome / Hero) as a Parsertime-style filter bar.

### Analytics (`#page-analytics`) — question-driven, keep the 7 data cuts
Keep all seven existing cuts (Heroes / Maps / Comp Matchups / vs Enemy / Teammates / Bans /
Stack) — that data is the wedge. Restructure each from raw table → question section:
- **Heroes:** "Are you a one-trick?" (hero-pool concentration bar) + "Who do you win with?" (WR by
  hero, sorted, with weighted-games + confidence tag). Parsertime literally does this; we have the
  WR data they lack.
- **Maps:** "Where do you win most?" (map WR bar chart, best/worst called out in the answer line).
- **Comp Matchups:** "Which comps beat you?" — my-comp × enemy-comp WR, shown as a small matrix or
  ranked list (per Phase-2 design, default to enemy-archetype grain, not the sparse full matrix).
- **vs Enemy / Teammates / Bans / Stack:** each = question header + answer sentence + ranked
  viz/table with confidence tags.
- Adopt Parsertime's **sub-tab bar** styling for these cuts (already have a `.tab-bar`).

### Match detail
- `[DECIDE]` — do we need a full dedicated match *page* (Leetify-style with sub-tabs), or is the
  **expanded card** in History/Session enough? Given our per-match data depth, the expanded card
  is likely sufficient and a full page would feel empty. Default assumption: **no separate match
  page**; the expanded card is the match detail.

### Queue / Settings
- Out of primary scope. Light restyle to match new card system for consistency; no structural
  change. Queue already got tab-type badges in the OCR branch.

---

## 6. Build sequence (phased, each independently shippable)

1. **Token + card refresh** — resolve accent/role collision, build the expandable-card component
   and the stat-strip + question-section components. Verify visually on one page.
2. **History → expandable cards.** Highest-impact single change. Ship.
3. **Analytics → question sections.** One cut at a time; Heroes + Maps first (richest data).
4. **Dashboard reorder** to session-forward.
5. **Session detail + Sessions list** polish.
6. **Queue/Settings** consistency pass.

Each phase: build → verify in Edge headless screenshot (existing project pattern) → commit. Don't
big-bang the whole frontend in one commit.

---

## 7. Out of scope (explicit)
- Per-round / telemetry visualizations (no data).
- Light mode `[DECIDE]` unless chosen in.
- Mobile layout (desktop-first personal tool; revisit if friend-distribution demands it).
- New analytics *features* — this is a presentation overhaul, not new metrics. Compute layer stays.

---

## 8. Decisions

### Resolved (2026-06-26)
- **Theme:** dark only. ✓
- **Typography:** neutral single sans; Barlow Condensed retires. Proposed **Geist + IBM Plex Mono**
  (numbers) — pending Brandon seeing it in a mock. ✓ (font family TBD on mock review)
- **Sessions IA:** own nav item (separate from the live Session page). ✓
- **Scope:** full overhaul of all pages, coordinated pass. ✓
- **Density → progressive disclosure (§4.1).** Resolved not as "cram more" but as drill-down:
  clean + big type at each level, density earned through depth. Sacrifice priority: tight first,
  then clean/big preserved. ✓
- **Signature element:** the **session momentum spine** (§3.5) — approved. ✓
- **Match detail:** expanded-card only (L2 of §4.1), no separate match page. ✓
- **Data plumbing — direction set (build target):** push to get nearly everything from **OCR**,
  expanding intake to **3 screenshots** (SUMMARY + scoreboard/TEAM + post-game **performance/
  accuracy page**). Source map:
  - scoreboard E/A/D/dmg/heal/mit (10 players) → OCR (TEAM tab, 60/60). ✓
  - enemy heroes / my heroes+% / teammate IDs → OCR (+ manual chip correction). ✓
  - comp archetype / tank matchup / deaths-per-10 → derived. ✓
  - weapon accuracy / per-hero perf → OCR from the NEW 3rd screenshot (self, per-match).
  - **bans → MANUAL multi-select** (not in any screenshot) — the one inherently-manual field;
    design degrades gracefully here (optional, never implies false completeness).
  - career baseline → OverFast 3rd-party if available, else OCR the reports page.
  **CAVEAT (gating, testable 2026-06-26 night):** the 3rd-screenshot weapon-accuracy OCR is
  unverified. If it proves unreliable, weapon-accuracy falls back to career-baseline only and the
  per-match accuracy panels are cut — design should not hard-depend on it. No manual *pasting* is
  acceptable; dropping a 3rd screenshot per game is (Brandon will do it consistently).
- **Session bracketing — model set (from Brandon; NOT auto-sessionization):** a session must be
  **started before any game is entered** — hitting Start is what enables game entry. If screenshots
  hit the inbox with no active session, the app **prompts to start a session and auto-enters the
  add-game flow** (but a session is still created first). Exception: **historical / past-games**
  entry (first-time setup, bulk backlog, or a fully-missed session) goes through a separate "Add
  Past Games" path — those games feed **general averages but NOT session analytics**. (Earlier
  auto-sessionization-by-time-gap idea = rejected.) **Undocumented elsewhere — backport this to
  `wiki/personal/ow-tracker.md`.**

### Still open
1. **Brand accent:** must NOT collide with role colors (blue/orange/green/purple already taken).
   Free hues = cyan/teal, rose/magenta, amber-gold. **Proposing desaturated rose/magenta**
   (Leetify-adjacent, distinct from open-purple) in the mock — veto on sight if wrong.
2. **Geist confirmation** — on mock review.
3. **Session/Sessions naming** to avoid confusion (minor; e.g. "Live" vs "Sessions").
