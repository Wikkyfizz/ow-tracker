// Seeds isolated state into e2e/.tmp BEFORE Playwright launches the app.
// Run as the npm `pretest` hook, so it finishes before the web server starts —
// this is the only safe time to delete the throwaway DB (deleting it while the
// server holds the WAL open silently drops the seeded tables). The server's own
// init_db() then creates + seeds a fresh DB at startup.
import { fileURLToPath } from 'url';
import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tmp = path.join(__dirname, '.tmp');

const SCREENSHOT = 'E:\\Claude stuff\\OW screenshots\\Overwatch_06W2CnsgI0.png';

fs.rmSync(tmp, { recursive: true, force: true });
fs.mkdirSync(path.join(tmp, 'inbox'), { recursive: true });

fs.writeFileSync(
  path.join(tmp, 'settings.json'),
  JSON.stringify({ username: 'DROWZY', battletag: 'Drowzy-11334',
                   inbox_folder: path.join(tmp, 'inbox'), tracked_players: [] }, null, 2),
);

const parsed = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'team-parsed.json'), 'utf8'));
fs.writeFileSync(
  path.join(tmp, 'queue.json'),
  JSON.stringify([{
    filename: 'e2e-team.png',
    path: fs.existsSync(SCREENSHOT) ? SCREENSHOT : path.join(tmp, 'inbox', 'e2e-team.png'),
    parsed,
    added_at: new Date().toISOString(),
  }], null, 2),
);

console.log('[seed] wrote isolated settings + queue to', tmp);
