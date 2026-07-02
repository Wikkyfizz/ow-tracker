import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const tmp = path.join(__dirname, '.tmp');
const PORT = 8199;
const python = path.join(root, 'venv', 'Scripts', 'python.exe');

// NOTE: keep this file side-effect-free. State seeding lives in global-setup.mjs
// because Playwright evaluates the config more than once, and a re-run would
// clobber the live server's DB. Config only *describes* the run.

export default defineConfig({
  testDir: __dirname,
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    headless: true,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${python}" -m uvicorn main:app --host 127.0.0.1 --port ${PORT} --no-access-log`,
    cwd: root,
    url: `http://127.0.0.1:${PORT}/api/heroes`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: 'pipe',
    stderr: 'pipe',
    env: {
      OW_TRACKER_DB: path.join(tmp, 'test.db'),
      OW_TRACKER_QUEUE: path.join(tmp, 'queue.json'),
      OW_TRACKER_SETTINGS: path.join(tmp, 'settings.json'),
    },
  },
});
