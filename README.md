# OW Tracker

Personal Overwatch 2 stat tracker. Since Blizzard provides no match history or public API, this app reads your post-game scoreboard screenshots and builds a searchable record of every game you've played — with win-rate breakdowns by hero, map, team composition, and more.

---

## Starting the app

OW Tracker runs on Windows.

### One-time setup

1. **Download OW Tracker.** On GitHub, click **Code → Download ZIP**, then unzip it somewhere you'll keep it (or `git clone` it).
2. **Install Python** (3.10 or newer): https://www.python.org/downloads/
   The default install options are fine.
3. **Install Tesseract OCR.** It's the part that reads text from your screenshots:
   https://github.com/UB-Mannheim/tesseract/wiki
   The default install options are fine. OW Tracker finds it whether or not it's on your PATH.

### Every time you want to use it

Double-click **`start.bat`** in the OW Tracker folder. The first time, it sets itself up, which takes a few minutes. After that it starts in seconds and opens **http://localhost:8000** in your browser.

To stop it, close the black window that `start.bat` opened.

The app runs as a mini web server on your own machine. Your games stay on your computer and only you can see the app. The only things it fetches online are the charts library and, if you ask for it in Settings, your career stats from OverFast.

### First time in the app

Open **Settings** and fill in:
- **Username**: your in-game name exactly as it appears on the scoreboard, so the app can find your row.
- **Inbox Folder**: where you'll save screenshots. The default is `C:\OW-Tracker\inbox`, and it's created for you.

If the app shows a yellow banner saying Tesseract isn't installed, do step 3 above, then close and reopen OW Tracker.

<details>
<summary>Starting it from a terminal instead</summary>

```
py -3.12 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe main.py
```
Only the last line is needed after the first time. If Tesseract is somewhere unusual, set the `TESSERACT_CMD` environment variable to the full path of `tesseract.exe`.
</details>

---

## How the app works

### The core loop

```
Play a game  →  Take a screenshot  →  App reads it  →  You confirm in ~15s  →  Stats update
```

After each ranked game, screenshot the post-game **Game Reports** tab (the full 10-player scoreboard). Drop it into your inbox folder (configured in Settings). The app picks it up automatically, reads the map name, outcome, heroes, and your stats using OCR, then puts it in the **Queue** tab for a quick review. You check that everything looks right, add any extra info (rank, notes, bans), and hit submit. The game is saved to your personal database and immediately shows up in your stats.

---

### The inbox folder

The app watches a folder on your computer for new screenshots. The moment a new image appears there, it starts reading it.

You set this folder in **Settings → Inbox Folder**. Configure ShareX (or Windows' built-in snipping tool) to save screenshots to the same folder and the whole process becomes automatic — play a game, take a screenshot, flip to the browser, and the parsed data is already waiting.

---

### Sessions

A session is a block of ranked games played in one sitting — a practice unit, not just a list of games.

Before you queue up, go to the **Session** page and hit **Start Session**. You can optionally set a goal for the session ("push to Plat", "work on Winston dive timing", etc.). When you're done for the day, hit **End Session**.

Why sessions matter:
- Games are **serially correlated** — tilt, momentum, and a bad-aim-day affect the whole block. Sessions surface that pattern.
- The **momentum spine** on each session card (in the Sessions page) shows your W/L sequence game by game, making streaks and slumps visible at a glance.
- Session analytics (win rate trend, "are you improving?") compare your recent sessions against your all-time baseline.

**A session must be started before any game can be linked to it.** If you log games without an active session, they're saved as historical records — they count toward your all-time stats but don't appear in session analytics.

---

### The pages

#### Dashboard
Your headline numbers at a glance. Shows total games played, overall win rate, last-20-game win rate (your recent form), and an "improving?" indicator that compares recent form to your all-time average. Also includes a rank progression chart, recent sessions, and your best-performing hero and map.

#### Session (the live page)
The active session while you're playing. Shows a running W/L count, live win-rate bar, and the list of games so far. When a screenshot is parsed, the confirmed match appears here immediately.

#### Sessions
A history of all your past sessions. Each card shows the goal you set, W/L record, win rate, and how long the session ran. Click a card to expand it and see the individual games as a mini match-list with the session's momentum spine.

#### History
Every match you've ever logged, newest first. Each card shows the outcome, map, heroes you played, KDA (eliminations / deaths / assists), and your rank at the time. Click any card to expand it and see full stats, enemy heroes, bans, notes, and your practice rating for that game.

#### Analytics
Seven data views that answer specific questions about your play:

| Tab | The question it answers |
|---|---|
| **Heroes** | Which heroes am I actually winning on? |
| **Maps** | Which maps are hurting my rank? |
| **Comps** | How do I perform playing Dive vs. Poke vs. Brawl? What about against each? |
| **vs. Enemy Heroes** | Which specific heroes do I struggle against? |
| **Teammates** | Do I win more with certain friends? |
| **Stack Size** | Am I better solo, duo, or in a group? |
| **Bans** | Which heroes do I ban most — and does banning them actually help? |

Stats are **weighted by playtime per game**. If you played D.Va for 75% of a game and Winston for 25%, that game counts as 0.75 toward D.Va's record and 0.25 toward Winston's — not a full game for each. This keeps the numbers honest when you swap heroes mid-game.

Stats with fewer than 5 weighted games are shown with a **low confidence** tag, since the sample is too small to trust yet.

#### Queue
The review inbox. When a screenshot is parsed, it appears here with all extracted data pre-filled. Check that the map, outcome, heroes, and stats look right, fill in your rank and any bans, and submit. Takes about 15 seconds per game.

#### Settings
- **Username** — your in-game name (used to find your row on the scoreboard when parsing)
- **Battletag** — your full Battletag including the number (e.g. `Name-12345`), used to fetch your career stats from OverFast
- **Inbox Folder** — the folder the app watches for new screenshots
- **Tracked Players** — friends you play with; the app flags when they appear in your matches and tracks your win rate with them

---

### Where your data lives

All your data is stored in a single file called `ow_tracker.db` in this folder. It's a self-contained database — no server, no cloud. To back up your data, copy that file. To start fresh, delete it (the app will create a new empty one on next start).

---

### Known limitations

**OCR isn't perfect.** The app reads text from screenshots using optical character recognition, which occasionally misreads a number or name. The Queue review step exists specifically so you can catch and correct these before they're saved.

**Bans are entered manually.** The ban phase happens before the game and doesn't appear in any post-game screenshot, so there's no way to read it automatically. You can enter bans in the Queue review step if you want to track them.

**OverFast career stats are cached, not live.** The "Fetch Baseline" button in Settings pulls your all-time career stats from OverFast (a community-built Overwatch stats API). These stats don't update in real time — hit the button after a session to refresh them.
