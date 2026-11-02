// Every game belongs to a session, even when nobody pressed Start Session first.
// Runs last: it reuses the blank screenshot from merged-game.spec.
import { test, expect } from '@playwright/test';
import { fileURLToPath } from 'url';
import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tmp = path.join(__dirname, '.tmp');
const inbox = path.join(tmp, 'inbox');
const blankShot = path.join(inbox, 'processed', 'e2e-team.png');
const base = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'team-parsed.json'), 'utf8'));

const localMinutesAgo = (m) =>
  new Date(Date.now() - new Date().getTimezoneOffset() * 60000 - m * 60000).toISOString().slice(0, 19);

function seedItem(name, played_at, map = 'Colosseo') {
  const file = path.join(inbox, `${name}-team.png`);
  fs.copyFileSync(blankShot, file);
  fs.writeFileSync(path.join(tmp, 'queue.json'), JSON.stringify([{
    filename: path.basename(file),
    path: file,
    added_at: new Date().toISOString(),
    parsed: { ...base, merged: true, my_row: 0, played_pcts: [100], map, outcome: 'Win', played_at, warnings: [] },
  }]));
}

async function openConfirm(page) {
  await page.goto('/');
  await page.click('.nav-btn[data-page="queue"]');
  await page.click('button:has-text("Confirm & Edit")');
  await expect(page.locator('#game-modal')).toBeVisible();
}

const saved = async (page) => {
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('saved');
  await page.waitForTimeout(700);
};
const sessionOfNewest = async (request) => {
  const { matches } = await (await request.get('/api/matches?limit=500')).json();
  return matches.sort((a, b) => b.id - a.id)[0].session_id;
};
const sessionRow = async (request, id) => (await (await request.get(`/api/sessions/${id}`)).json());
const endRunning = async (request) => {
  const { session } = await (await request.get('/api/sessions/active')).json();
  if (session) await request.post(`/api/sessions/${session.id}/end`);
};

test.beforeEach(async ({ request }) => { await endRunning(request); });

test('with no session to join, saving is blocked until one is chosen', async ({ page, request }) => {
  seedItem('s1', '2026-09-01T20:00:00');
  await openConfirm(page);
  await expect(page.locator('#m-session')).toHaveValue('');

  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('Choose a session');
  expect((await (await request.get('/api/queue')).json()).queue).toHaveLength(1);

  await page.selectOption('#m-session', 'new');
  await saved(page);

  const id = await sessionOfNewest(request);
  const s = await sessionRow(request, id);
  expect(s.started_at).toBe('2026-09-01T20:00:00'); // the game's time, not when it was confirmed
  expect(s.date).toBe('2026-09-01');
  expect(s.ended_at).toBe('2026-09-01T20:00:00');   // a game this old isn't a running session
});

test('the next games of a sitting confirmed later join it without a prompt', async ({ page, request }) => {
  seedItem('s2', '2026-09-01T20:20:00', 'Oasis');
  await openConfirm(page);
  const first = await page.locator('#m-session').inputValue();
  expect(first).not.toBe('');
  await saved(page);
  const s = await sessionRow(request, Number(first));
  expect(s.matches).toHaveLength(2);
  expect(s.ended_at).toBe('2026-09-01T20:20:00');

  // A game from another day doesn't: it asks again, and the old session is on the list.
  seedItem('s3', '2026-09-03T20:00:00', 'Ilios');
  await openConfirm(page);
  await expect(page.locator('#m-session')).toHaveValue('');
  await expect(page.locator(`#m-session option[value="${first}"]`)).toContainText('2 games');
  await page.selectOption('#m-session', first);
  await saved(page);
  expect(await sessionOfNewest(request)).toBe(Number(first));
  expect((await sessionRow(request, Number(first))).ended_at).toBe('2026-09-03T20:00:00');
});

test('a recent game can start a session that keeps running', async ({ page, request }) => {
  seedItem('s4', localMinutesAgo(5));
  await openConfirm(page);
  await page.selectOption('#m-session', 'new');
  await saved(page);
  const id = await sessionOfNewest(request);
  const { session } = await (await request.get('/api/sessions/active')).json();
  expect(session.id).toBe(id);
  await expect(page.locator('#sess-nav-text')).not.toHaveText('Live Session'); // no reload needed

  // The next game goes to it, and starting another ends it.
  seedItem('s5', localMinutesAgo(1), 'Oasis');
  await openConfirm(page);
  await expect(page.locator('#m-session')).toHaveValue(String(id));
  await page.selectOption('#m-session', 'new');
  await saved(page);
  expect((await sessionRow(request, id)).ended_at).not.toBeNull();
  expect((await (await request.get('/api/sessions/active')).json()).session.id).not.toBe(id);
});

test('games are placed by when they were played, and End Session is final', async ({ request }) => {
  const save = (played_at) => request.post('/api/matches', { data: {
    map: 'Ilios', outcome: 'Win', my_heroes: [{ hero: 'Tracer', pct: 100 }], played_at,
  }});
  const placed = async (res) =>
    (await (await request.get(`/api/matches/${(await res.json()).id}`)).json()).session_id;

  const { id: sess } = await (await request.post('/api/sessions', { data: { goal: 'timing' } })).json();
  expect(await placed(await save(localMinutesAgo(0)))).toBe(sess);
  expect(await placed(await save(localMinutesAgo(30)))).toBe(sess);  // started the session late
  expect((await save(localMinutesAgo(6000))).status()).toBe(400);    // an old screenshot, no session of its own
  await request.post(`/api/sessions/${sess}/end`);
  expect((await save(localMinutesAgo(-90))).status()).toBe(400);     // ended by hand, so nothing later joins
  expect((await request.post('/api/matches', { data: {
    map: 'Ilios', outcome: 'Win', session_id: 999999,
  }})).status()).toBe(400);
});

test('Edit shows a game\'s session and can move it', async ({ page, request }) => {
  const { id: gameId } = await (await request.post('/api/matches', { data: {
    map: 'Rialto', outcome: 'Win', my_heroes: [{ hero: 'Winston', pct: 100 }],
    played_at: '2026-09-10T12:00:00', new_session: true,
  }})).json();
  const original = (await (await request.get(`/api/matches/${gameId}`)).json()).session_id;
  const openEdit = async () => {
    await page.goto('/');
    await page.click('.nav-btn[data-page="history"]');
    const card = page.locator(`#mc-${gameId}`);
    await card.locator('.match-card-header').click();
    await card.locator('button:has-text("Edit")').click();
    await expect(page.locator('#modal-title-text')).toHaveText('Edit Game');
  };
  await openEdit();
  await expect(page.locator('#m-session')).toHaveValue(String(original));
  await page.selectOption('#m-session', 'new');
  await page.click('#modal-save-btn');
  await expect(page.locator('#modal-msg')).toContainText('updated');

  const moved = (await (await request.get(`/api/matches/${gameId}`)).json()).session_id;
  expect(moved).not.toBe(original);
  // Its old session had only this game, so it's gone rather than an empty card.
  expect((await request.get(`/api/sessions/${original}`)).status()).toBe(404);
});
