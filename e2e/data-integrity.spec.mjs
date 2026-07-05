// End-to-end verification of the my_heroes / my_team_heroes decoupling (fix #1)
// driven through the real UI: Queue → Confirm & Edit → Log Game.
//
// Run:  cd e2e && npx playwright test
// The harness (playwright.config.mjs) boots the FastAPI app against a throwaway
// DB/queue/settings and seeds one TEAM queue item from fixtures/team-parsed.json.
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const parsed = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'team-parsed.json'), 'utf8'));

const TEAM = parsed.my_team_heroes.map(h => h.hero);       // Winston, Genji, Tracer, Lucio, Kiriko
const ENEMY = parsed.enemy_heroes.map(h => h.hero);        // Reinhardt, Reaper, Mei, Ana, Brigitte
const PLAYED = 'Lucio';                                    // the one hero we actually played
const TEAMMATES = TEAM.filter(h => h !== PLAYED);          // must NOT end up in my_heroes

// Fail the test on any uncaught JS exception; collect console errors for reporting.
function attachErrorGuards(page, sink) {
  page.on('pageerror', err => sink.push(`pageerror: ${err.message}`));
  page.on('console', msg => {
    if (msg.type() === 'error' && !/favicon|net::ERR|404/.test(msg.text())) {
      sink.push(`console.error: ${msg.text()}`);
    }
  });
}

test('TEAM parse: comp panel holds full team, my_heroes stays clean through save', async ({ page, request }) => {
  const jsErrors = [];
  attachErrorGuards(page, jsErrors);

  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');

  // Queue item detail relabelled "My team:" (was "My heroes:")
  await expect(page.locator('.queue-item-detail')).toContainText('My team');

  // Team-comp panel "My" row shows all 5 detected team heroes (from my_team_heroes)
  const myRowNames = page.locator('.team-comp-row').first().locator('.hero-slot-name');
  await expect(myRowNames).toHaveCount(5);
  const shown = (await myRowNames.allTextContents()).map(s => s.trim());
  for (const hero of TEAM) expect(shown).toContain(hero);

  // Open the log modal
  await page.click('button:has-text("Confirm & Edit")');
  await expect(page.locator('#game-modal')).toBeVisible();

  // Source-screenshot viewer: offered for queue items, collapsed by default,
  // image loads on expand (backlog item 3).
  const shotSection = page.locator('#modal-screenshot-section');
  await expect(shotSection).toBeVisible();
  await expect(page.locator('#modal-screenshot-body')).toBeHidden();
  const imgResponse = page.waitForResponse(r => r.url().includes('/image') && r.ok());
  await page.click('#modal-screenshot-toggle');
  await expect(page.locator('#modal-screenshot-img')).toBeVisible();
  await imgResponse;
  await page.click('#modal-screenshot-toggle'); // collapse again before filling the form
  await expect(page.locator('#modal-screenshot-body')).toBeHidden();

  // CORE ASSERTION 1: "My Heroes" starts EMPTY — no teammate is pre-selected.
  await expect(page.locator('#m-my-heroes .hero-chip.selected')).toHaveCount(0);

  // Enemy comp IS pre-selected (full 5-hero enemy team).
  await expect(page.locator('#m-enemy-heroes .hero-chip.selected')).toHaveCount(ENEMY.length);

  // Fill required fields, pick the single hero we played, save.
  await page.selectOption('#m-map', 'Ilios');
  await page.selectOption('#m-outcome', 'Win');
  await page.click(`#m-my-heroes .hero-chip[data-hero="${PLAYED}"]`);
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');

  // CORE ASSERTION 2: verify persisted record via the API.
  const res = await request.get('/api/matches?limit=1');
  expect(res.ok()).toBeTruthy();
  const match = (await res.json()).matches[0];
  const myHeroes = JSON.parse(match.my_heroes || '[]').map(h => h.hero);

  expect(myHeroes).toEqual([PLAYED]);                       // only what I played
  for (const mate of TEAMMATES) expect(myHeroes).not.toContain(mate);  // no teammate pollution
  expect(match.my_comp).toBe('Dive');                       // derived from the DIVE team, not Lucio(Brawl)

  // screenshot_path persisted on the match (was silently dropped before)
  expect(match.screenshot_path).toContain('e2e-team.png');

  // Queue item consumed by the save; screenshot archived to processed/ (NOT discarded/)
  const q = await (await request.get('/api/queue')).json();
  expect(q.queue).toEqual([]);
  expect(fs.existsSync(path.join(__dirname, '.tmp', 'inbox', 'processed', 'e2e-team.png'))).toBe(true);
  expect(fs.existsSync(path.join(__dirname, '.tmp', 'inbox', 'discarded', 'e2e-team.png'))).toBe(false);

  expect(jsErrors, `JS errors during flow:\n${jsErrors.join('\n')}`).toEqual([]);
});

test('Sessions page: history card renders labeled full-width stats', async ({ page, request }) => {
  const jsErrors = [];
  attachErrorGuards(page, jsErrors);

  // Create a completed session with one win via the API
  const sess = await (await request.post('/api/sessions', { data: { goal: 'e2e layout check' } })).json();
  await request.post('/api/matches', { data: {
    map: 'Ilios', outcome: 'Win', my_heroes: [{ hero: 'Tracer', pct: 100 }],
    my_team_heroes: [], enemy_heroes: [], bans: [], data_source: 'manual',
    session_id: sess.id,
  }});
  await request.post(`/api/sessions/${sess.id}/end`);

  await page.goto('/');
  await page.click('.nav-btn[data-page="sessions"]');

  const card = page.locator('.sess-hist-card').first();
  await expect(card).toBeVisible();

  // Four labeled stat cells spread across the header
  const labels = card.locator('.sess-hist-stat .l');
  await expect(labels).toHaveText(['Record', 'Win rate', 'Games', 'Duration']);
  await expect(card.locator('.sess-hist-stat .v').nth(0)).toContainText('1W');
  await expect(card.locator('.sess-hist-stat .v').nth(1)).toContainText('100');
  await expect(card.locator('.sess-hist-stat .v').nth(2)).toHaveText('1');

  // Expand/collapse still works after the layout rework
  await card.locator('.sess-hist-header').click();
  await expect(card).toHaveClass(/expanded/);
  await expect(card.locator('.sess-hist-body')).toBeVisible();

  expect(jsErrors, `JS errors during flow:\n${jsErrors.join('\n')}`).toEqual([]);
});
