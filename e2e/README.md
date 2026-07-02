# e2e — browser tests

Playwright tests that drive the real UI against the real FastAPI backend, in an
isolated environment (throwaway DB / queue / settings — your `ow_tracker.db` is
never touched).

## Run

```
cd e2e
npm test            # headless
npm run test:headed # watch it in a real browser
```

`npm test` runs `seed.mjs` first (the `pretest` hook), which wipes `e2e/.tmp/`
and writes an isolated `settings.json` + `queue.json`. Playwright then boots the
app (`playwright.config.mjs` → `webServer`) with these env overrides:

- `OW_TRACKER_DB`, `OW_TRACKER_QUEUE`, `OW_TRACKER_SETTINGS` → point at `e2e/.tmp/`

The server's own `init_db()` creates + seeds a fresh DB at startup.

## One-time setup

```
cd e2e
npm install
npx playwright install chromium
```

Requires Node (installed system-wide) and the project `venv` (the config launches
`../venv/Scripts/python.exe -m uvicorn`).

## Layout

- `playwright.config.mjs` — run config + `webServer` (side-effect free on purpose).
- `seed.mjs` — pre-test state seeding. **Must** run before the server starts:
  deleting the throwaway DB while the server holds its WAL open silently drops the
  seeded tables, so seeding lives in the `pretest` hook, not `globalSetup`
  (globalSetup runs *after* the web server boots).
- `fixtures/team-parsed.json` — a representative parsed TEAM screenshot.
- `data-integrity.spec.mjs` — verifies the `my_heroes` / `my_team_heroes` split
  end-to-end (fix for teammates polluting the user's hero win-rates).

## Adding tests

Seed whatever queue/DB state you need in `seed.mjs` (or a dedicated fixture),
then assert against the UI + the JSON API. The `request` fixture shares the
server's `baseURL`, so you can cross-check persisted rows after a UI action.
