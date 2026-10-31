// A merged SUMMARY + TEAM queue item, driven through the real UI. Runs after
// data-integrity.spec (alphabetical, 1 worker), whose save leaves the queue empty
// and archives e2e-team.png, which this spec reuses as its blank screenshot.
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tmp = path.join(__dirname, '.tmp');
const inbox = path.join(tmp, 'inbox');
const blankShot = path.join(inbox, 'processed', 'e2e-team.png');
const base = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'team-parsed.json'), 'utf8'));

function seedMergedItem(name, overrides = {}) {
  const teamFile = path.join(inbox, `${name}-team.png`);
  const summaryFile = path.join(inbox, `${name}-summary.png`);
  fs.copyFileSync(blankShot, teamFile);
  fs.copyFileSync(blankShot, summaryFile);
  fs.writeFileSync(path.join(tmp, 'queue.json'), JSON.stringify([{
    filename: path.basename(teamFile),
    path: teamFile,
    linked_filename: path.basename(summaryFile),
    linked_path: summaryFile,
    added_at: new Date().toISOString(),
    parsed: {
      ...base,
      merged: true,
      my_row: 0,
      played_pcts: [100],
      map: 'Colosseo',
      outcome: 'Win',
      played_at: '2026-10-31T13:53:00',
      game_length_s: 422,
      elims: 25,
      warnings: [],
      ...overrides,
    },
  }]));
  return { teamFile, summaryFile };
}

const archived = (sub, file) => fs.existsSync(path.join(inbox, sub, path.basename(file)));

test('merged game: confirm prefills everything and archives both screenshots', async ({ page, request }) => {
  const { teamFile, summaryFile } = seedMergedItem('m1');
  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');

  await expect(page.locator('.tab-badge')).toHaveText('SUMMARY + TEAM');
  await expect(page.locator('.queue-item-detail')).toContainText('Colosseo');

  await page.click('button:has-text("Confirm & Edit")');
  await expect(page.locator('#m-map')).toHaveValue('Colosseo');
  await expect(page.locator('#m-outcome')).toHaveValue('Win');
  await expect(page.locator('#m-played-at')).toHaveValue('2026-10-31T13:53');
  await expect(page.locator('#m-elims')).toHaveValue('25');

  // Row 0 of the fixture is Winston, and the Summary says one hero at 100%.
  const myHero = base.my_team_heroes[0].hero;
  await expect(page.locator('#m-my-heroes .hero-chip.selected')).toHaveCount(1);
  await expect(page.locator(`#m-my-heroes .hero-chip.selected[data-hero="${myHero}"]`)).toHaveCount(1);

  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');

  const match = (await (await request.get('/api/matches?map=Colosseo')).json()).matches[0];
  expect(match.played_at).toBe('2026-10-31T13:53:00');
  expect(match.game_length_s).toBe(422);
  expect(JSON.parse(match.my_heroes).map(h => h.hero)).toEqual([myHero]);

  expect((await (await request.get('/api/queue')).json()).queue).toEqual([]);
  expect(archived('processed', teamFile)).toBe(true);
  expect(archived('processed', summaryFile)).toBe(true);
});

test('merged game with a hero split: nothing is preselected', async ({ page }) => {
  seedMergedItem('m2', { played_pcts: [88, 12], warnings: ['Hero split on Summary: 88% + 12%'] });
  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');
  await page.click('button:has-text("Confirm & Edit")');
  await expect(page.locator('#m-my-heroes .hero-chip.selected')).toHaveCount(0);
  await expect(page.locator('#modal-ocr-banner')).toContainText('88% + 12%');
});

test('a map added while the tab is open appears in the form', async ({ page }) => {
  seedMergedItem('m4', { map: 'Brandnewmap' });
  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');
  // Simulate the server gaining a map after this page loaded its list.
  const current = await (await page.request.get('/api/maps')).json();
  await page.route('**/api/maps', route => route.fulfill({
    json: [...current, { name: 'Brandnewmap', game_mode: 'Escort', comp_affinity: 'Neutral', notes: '' }],
  }));
  await page.click('button:has-text("Confirm & Edit")');
  await expect(page.locator('#m-map')).toHaveValue('Brandnewmap');
  await expect(page.locator('#m-map optgroup[label="Escort"] option[value="Brandnewmap"]')).toHaveCount(1);
});

test('a parsed map missing from the list is kept, not blanked', async ({ page }) => {
  seedMergedItem('m5', { map: 'Unlistedmap' });
  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');
  await page.click('button:has-text("Confirm & Edit")');
  await expect(page.locator('#m-map')).toHaveValue('Unlistedmap');
});

test('discarding a merged game archives both screenshots', async ({ page, request }) => {
  const { teamFile, summaryFile } = seedMergedItem('m3');
  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');
  await page.click('button:has-text("Discard")');
  await expect.poll(async () => (await (await request.get('/api/queue')).json()).queue.length).toBe(0);
  expect(archived('discarded', teamFile)).toBe(true);
  expect(archived('discarded', summaryFile)).toBe(true);
});
