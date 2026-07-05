// Seeds isolated state into e2e/.tmp BEFORE Playwright launches the app.
// Run as the npm `pretest` hook, so it finishes before the web server starts —
// this is the only safe time to delete the throwaway DB (deleting it while the
// server holds the WAL open silently drops the seeded tables). The server's own
// init_db() then creates + seeds a fresh DB at startup.
import { fileURLToPath } from 'url';
import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const tmp = path.join(__dirname, '.tmp');

fs.rmSync(tmp, { recursive: true, force: true });
fs.mkdirSync(path.join(tmp, 'inbox'), { recursive: true });

fs.writeFileSync(
  path.join(tmp, 'settings.json'),
  JSON.stringify({ username: 'DROWZY', battletag: 'Drowzy-11334',
                   inbox_folder: path.join(tmp, 'inbox'), tracked_players: [] }, null, 2),
);

// Generate a deterministic 1920×1080 screenshot INSIDE the throwaway inbox.
// Never reference a real screenshot: the save/discard flows MOVE the queue
// item's file into archive subfolders (would relocate the user's actual file),
// and the live folder churns so a hardcoded path rots. Full-size matters —
// the portrait-crop and image endpoints must return 200, not 500.
const seededShot = path.join(tmp, 'inbox', 'e2e-team.png');
const python = path.join(__dirname, '..', 'venv', 'Scripts', 'python.exe');
execFileSync(python, ['-c',
  'import sys, cv2, numpy as np; cv2.imwrite(sys.argv[1], np.zeros((1080,1920,3), np.uint8))',
  seededShot,
]);

const parsed = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'team-parsed.json'), 'utf8'));
fs.writeFileSync(
  path.join(tmp, 'queue.json'),
  JSON.stringify([{
    filename: 'e2e-team.png',
    path: seededShot,
    parsed,
    added_at: new Date().toISOString(),
  }], null, 2),
);

console.log('[seed] wrote isolated settings + queue to', tmp);
