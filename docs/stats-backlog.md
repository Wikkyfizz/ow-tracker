# Stats backlog

Questions to answer once there are enough games, what data each one needs, and whether that data is
saved today. Written 2026-11-05 with 43 games in 5 sessions: too few for any of the session
questions to mean anything yet. The point of this list is to make sure the data gets **saved now**,
because a game played without it can't be filled in later.

## What each game already saves

| Data | Where | Notes |
|---|---|---|
| Order and timing of games | `matches.played_at` (end of game, to the minute), `game_length_s` | The time between games (queue and breaks) can be worked out: usually about 3 minutes, sometimes a 20–30 minute break. |
| Which session | `matches.session_id`, `sessions.started_at / ended_at` | Every game has one. |
| Result | `matches.outcome` | |
| Your stats, and all 10 players' | `matches` (yours), `match_participants` (everyone: hero, role row, E/A/D/dmg/heal/mit) | Lets you compare against your team or the whole lobby. |
| Heroes you played, with % of the game | `matches.my_heroes` | Mid-game swaps are recorded (31 games have more than one hero). |
| Both comps | `my_team_heroes`, `enemy_heroes`, `my_comp`, `enemy_comp` | **Final heroes only**: the scoreboard doesn't show what the enemy swapped from. |
| Party | `stack_size`, `teammates` | |
| Leavers | a team with fewer than 5 rows in `match_participants` | |
| Rank | `rank_tier`, `rank_division`, `rank_pct` | Rank is deferred: only 4 games have it. |
| How you felt after it | `matches.tilt` (1 great game … 5 giga tilted) | From 2026-11-05 on; optional. |

## The questions

**Buildable** means everything it needs is already saved. **Needs capture** means something has to be
recorded from now on.

### When to stop, and how long to play

| Question | Status | How |
|---|---|---|
| Does win rate fall after N losses in a row? After N wins? | Buildable | For each game, the streak going into it within the session → win rate of the next game, against your overall win rate. |
| Does the previous game's result predict the next? | Buildable | P(win after a loss) vs P(win after a win). |
| How does win rate change with game number in the session, and with time played? | Buildable | Win rate by game 1, 2, 3…, and by hours since the session started. |
| Best session length? | Buildable, but needs many sessions | Compare sessions by length in games and in hours: their win rate and net wins. Needs ~30+ sessions before it says anything. |
| Do breaks help? | Buildable | The time between games is known. Win rate after a 10+ minute break vs straight back into the queue. |
| Do deaths predict the next game? | Buildable | Your deaths in a game, also compared with your team's average and the lobby's (`match_participants`) → the next game's result. The same for "worst on your team" or "out-damaged the enemy tank". |
| Signs of a good session, worth continuing? | Buildable | The same measures in reverse: what's true in the games before a win, or in sessions that ended up positive. |
| Does tilt predict the next game? | Capturing from 2026-11-05 | `matches.tilt`, picked on the game form: 1 great game … 5 giga tilted (blank if skipped). Win rate of the game after each tilt level; how many tilted games in a row come before a loss streak; whether tilt climbs through a session. |
| Do stats you can measure line up with tilt? | Capturing from 2026-11-05 | Tilt against deaths vs your team, outcome, and streak. If they line up, the app could warn you even on games you don't rate. |
| Why did you stop? | Not captured, on purpose | Most sessions end for reasons outside the game, mostly time, so tilt is tracked per game instead. |
| Time of day and day of week | Buildable | From `played_at`. |

### Heroes and matchups

| Question | Status | How |
|---|---|---|
| Your hero vs a specific enemy hero (e.g. your tank vs theirs) | Built | `analytics.role_matchups` (tank vs tank, by hero or archetype). |
| Win rate vs each enemy hero | Built | Analytics → vs Enemy. |
| Best heroes on each map | Built | Analytics → vs Enemy → heroes on maps. Map type (`maps.comp_affinity`) is also saved. |
| Your hero vs every enemy hero, not just same role | Buildable | `my_heroes` × `enemy_heroes`. |
| Did a swap work? | Partly buildable | Your swaps are saved, with %, but not when you swapped or in what order. Win rate when you swapped vs didn't is doable now. |
| Counter-picks: what the enemy swapped to against you | **Not capturable** | The post-game screens show only each enemy's final hero, so their swaps are never seen. Final comps are saved, so "your hero vs the enemy's final hero" is the closest available. |
| Your stats per hero, excluding swaps | Needs care | In a game with a swap, your stats cover every hero you played, and Explore credits them all to your most-played hero. 31 of 43 games had a swap. A cleaner version would weight by the hero's % or only use one-hero games. |

## Reading the results honestly

- **Your stopping habit skews this.** If you usually stop after a loss, the last game of most sessions
  is a loss, and that alone makes "win rate late in a session" look low. Compare like with like:
  the game after a loss streak against the game after a win streak, not against "games where you
  kept going".
- **Sample size.** A 50% coin flip over 40 games swings between about 35% and 65%. Telling a
  10-point drop after losses apart from luck takes a few hundred games. The Explore tab's "low n" tag
  is the model: every one of these stats should show its game count.

## Tilt capture (built 2026-11-05)

Each game has an optional five-face gauge on the game form (Queue confirm, Add Game, Edit), from a
green "great game" to a red "giga tilted". It's stored in `matches.tilt` (1–5, NULL if skipped) and
shown on History cards. It's a rating made just after the game, so it reads as "how I feel going into
the next one". That's what the streak questions need.

Games before 2026-11-05 have no rating. Leave them out of tilt analyses rather than guessing.
