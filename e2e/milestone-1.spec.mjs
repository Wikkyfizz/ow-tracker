// Party tracking, editing saved games, save warnings, session timing, safe archiving
// and backups, through the real UI and API. Runs after merged-game.spec, whose blank
// screenshot it reuses. All names here are made up.
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tmp = path.join(__dirname, '.tmp');
const inbox = path.join(tmp, 'inbox');
const blankShot = path.join(inbox, 'processed', 'e2e-team.png');
const base = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'team-parsed.json'), 'utf8'));

const statRow = (damage) => ({ elims: 1, assists: 2, deaths: 3, damage, healing: 0, mitigation: 0 });
const teamRows = {
  my_team: [statRow(100), statRow(200), statRow(300), statRow(400), statRow(500)],
  enemy_team: [statRow(600), statRow(700), statRow(800), statRow(900), statRow(1000)],
};

function seedItem(name, overrides = {}) {
  const file = path.join(inbox, `${name}-team.png`);
  fs.copyFileSync(blankShot, file);
  fs.writeFileSync(path.join(tmp, 'queue.json'), JSON.stringify([{
    filename: path.basename(file),
    path: file,
    added_at: new Date().toISOString(),
    parsed: {
      ...base, merged: true, my_row: 0, played_pcts: [100], map: 'Colosseo', outcome: 'Win',
      played_at: '2026-10-31T13:53:00', game_length_s: 422, team_rows: teamRows, warnings: [],
      ...overrides,
    },
  }]));
  return file;
}

async function openConfirm(page) {
  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');
  await page.click('button:has-text("Confirm & Edit")');
  await expect(page.locator('.party-row')).toHaveCount(4); // the 5 allies minus my own row
  await page.selectOption('#m-session', 'new');
}

const newestMatch = async (request) =>
  (await (await request.get('/api/matches?limit=500')).json()).matches.sort((a, b) => b.id - a.id)[0];

test('marking a party member saves them, sets the stack, and adds them to the list', async ({ page, request }) => {
  seedItem('p1');
  await openConfirm(page);
  await expect(page.locator('#m-stack-label')).toHaveText('(solo)');

  await page.locator('.party-row').nth(1).click();
  await expect(page.locator('#m-stack-label')).toHaveText('(stack of 2)');

  // A marked player with no name can't be saved.
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('Type a name');

  await page.locator('.party-name-input').fill('TestFriend');
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');

  const match = await newestMatch(request);
  expect(match.stack_size).toBe(2);
  expect(JSON.parse(match.teammates)).toEqual(['TestFriend']);

  const detail = await (await request.get(`/api/matches/${match.id}`)).json();
  const named = detail.participants.filter(p => p.player_name);
  expect(named.map(p => [p.team, p.slot, p.player_name])).toEqual([['ally', 2, 'TestFriend']]);

  const settings = await (await request.get('/api/settings')).json();
  expect(settings.tracked_players.map(p => p.name)).toContain('TestFriend');

  // Teammate analytics now see them instead of calling the game solo.
  const mates = await (await request.get('/api/analytics/teammate-winrates')).json();
  expect(mates.find(m => m.player === 'TestFriend').games).toBe(1);
});

test('marking several friends at once keeps every one of them and the settings file', async ({ page, request }) => {
  seedItem('p2', { map: 'Oasis' });
  await openConfirm(page);
  for (const i of [0, 2, 3]) await page.locator('.party-row').nth(i).click();
  const inputs = page.locator('.party-name-input');
  await inputs.nth(0).fill('FriendOne');
  await inputs.nth(1).fill('FriendTwo');
  await inputs.nth(2).fill('友達');
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');

  const match = await newestMatch(request);
  expect(match.stack_size).toBe(4);
  const res = await request.get('/api/settings'); // used to fail: the writes corrupted the file
  expect(res.ok()).toBeTruthy();
  const names = (await res.json()).tracked_players.map(p => p.name);
  for (const n of ['FriendOne', 'FriendTwo', '友達']) expect(names).toContain(n);
});

test('a game with no scoreboard chooses party members from the list', async ({ page, request }) => {
  await page.goto('/');
  await page.click('#add-historical-btn');
  await page.selectOption('#m-map', 'Ilios');
  await page.selectOption('#m-outcome', 'Loss');
  await page.click('#m-my-heroes .hero-chip[data-hero="Winston"]');
  await page.click('#m-party .hero-chip:has-text("TestFriend")');
  await expect(page.locator('#m-stack-label')).toHaveText('(stack of 2)');
  await page.selectOption('#m-session', 'new');
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');
  const match = await newestMatch(request);
  expect(JSON.parse(match.teammates)).toEqual(['TestFriend']);
  expect(match.stack_size).toBe(2);
});

test('Edit fixes a saved game without damaging what it can\'t see', async ({ page, request }) => {
  seedItem('e1', { map: 'Rialto' });
  await openConfirm(page);
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');
  await page.waitForTimeout(700);

  const before = await newestMatch(request);
  expect(before.data_source).toBe('screenshot');
  expect(before.my_comp).toBe('Dive'); // from the full team, not the one hero played

  await page.click('.nav-btn[data-page="history"]');
  const card = page.locator(`#mc-${before.id}`);
  await card.locator('.match-card-header').click();
  await card.locator('button:has-text("Edit")').click();
  await expect(page.locator('#modal-title-text')).toHaveText('Edit Game');
  await expect(page.locator('#m-map')).toHaveValue('Rialto');
  await expect(page.locator('#m-elims')).toHaveValue('25');

  // Exact percentages, which the old 25% steps couldn't express.
  await page.click('#m-my-heroes .hero-chip[data-hero="Reinhardt"]');
  await page.locator('#m-my-heroes .hero-chip[data-hero="Winston"] .pct-input').fill('63');
  await page.locator('#m-my-heroes .hero-chip[data-hero="Reinhardt"] .pct-input').fill('37');
  await page.fill('#m-elims', '30');
  // This game's Summary says 100%, so the split needs the deliberate second click.
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('Summary shows 100%');
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('updated');

  const after = await (await request.get(`/api/matches/${before.id}`)).json();
  expect(JSON.parse(after.my_heroes)).toEqual([{ hero: 'Winston', pct: 63 }, { hero: 'Reinhardt', pct: 37 }]);
  expect(after.elims).toBe(30);
  expect(after.my_comp).toBe('Dive');
  expect(after.data_source).toBe('screenshot');
  expect(after.raw_parse).toBe(before.raw_parse);
  expect(after.played_at).toBe(before.played_at);
  expect(JSON.parse(after.participants.find(p => p.is_me).stats).elims).toBe(30);
});

test('a game with no hero, or picks that contradict Summary, warns before saving', async ({ page, request }) => {
  seedItem('w1', { map: 'Oasis', played_pcts: [60, 40] });
  await openConfirm(page);
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('No hero picked');
  expect((await (await request.get('/api/queue')).json()).queue).toHaveLength(1);

  // Picks take Summary's numbers in order, so a correct game needs no typing.
  await page.click('#m-my-heroes .hero-chip[data-hero="Winston"]');
  await expect(page.locator('#m-my-heroes .hero-chip[data-hero="Winston"] .pct-input')).toHaveValue('60');
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('adds up to 60');
  expect((await (await request.get('/api/queue')).json()).queue).toHaveLength(1);

  await page.click('#m-my-heroes .hero-chip[data-hero="Reinhardt"]');
  await expect(page.locator('#m-my-heroes .hero-chip[data-hero="Reinhardt"] .pct-input')).toHaveValue('40');
  await page.locator('#m-my-heroes .hero-chip[data-hero="Reinhardt"] .pct-input').fill('30');
  await page.locator('#m-my-heroes .hero-chip[data-hero="Winston"] .pct-input').fill('70');
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('Summary shows 60 + 40%');

  // A second click is a deliberate choice.
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');
});

test('a failed save keeps the queue item and its screenshot', async ({ request }) => {
  const file = seedItem('f1');
  const sessionsBefore = (await (await request.get('/api/sessions')).json()).length;
  const res = await request.post('/api/matches', { data: {
    map: 'Ilios', outcome: 'Win', screenshot_path: file, new_session: true,
    participants: [{ team: 'not-a-team' }], // fails the table's CHECK after the game inserts
  }});
  expect(res.status()).toBe(500);
  expect((await (await request.get('/api/sessions')).json()).length).toBe(sessionsBefore); // no orphan session
  expect((await (await request.get('/api/queue')).json()).queue).toHaveLength(1);
  expect(fs.existsSync(file)).toBe(true);
  expect(fs.existsSync(path.join(inbox, 'processed', path.basename(file)))).toBe(false);
  await request.delete(`/api/queue/${path.basename(file)}`);
});

test('backup copies the database and screenshots to the chosen folder', async ({ request }) => {
  const dest = path.join(tmp, 'backup-target');
  const settings = await (await request.get('/api/settings')).json();
  await request.put('/api/settings', { data: { ...settings, backup_folder: dest } });

  const result = await (await request.post('/api/backup')).json();
  expect(result.error).toBeUndefined();
  expect(fs.existsSync(result.snapshot)).toBe(true);
  expect(fs.existsSync(path.join(dest, 'screenshots', 'processed', 'e2e-team.png'))).toBe(true);
  expect(fs.existsSync(path.join(dest, 'settings.json'))).toBe(true);

  // Saving settings keeps the fields the form doesn't own.
  const saved = await (await request.get('/api/settings')).json();
  expect(saved.battletag).toBe(settings.battletag);
  expect(saved.backup_folder).toBe(dest);
});
