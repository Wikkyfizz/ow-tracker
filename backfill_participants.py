"""Rebuild raw_parse and match_participants for games saved before they were stored.
Re-reads each game's TEAM screenshot, so the result is today's OCR and templates, not
what was read or corrected at the time; raw_parse is marked "backfilled" to say so.
Games that already have a raw_parse are skipped, so this is safe to re-run.
Run: venv/Scripts/python.exe backfill_participants.py
"""
import json
from datetime import date
from pathlib import Path

import db
from models import MatchParticipant  # noqa: F401  (validates the rows the same way a save does)
from parser.pipeline import build_participants, match_summary_row, parse_screenshot

SETTINGS = Path(__file__).parent / "settings.json"
STATS = ("elims", "deaths", "assists", "damage", "healing", "mitigation")


def find_screenshot(saved_path: str, inbox: Path):
    name = Path(saved_path).name
    for path in (Path(saved_path), inbox / "processed" / name, inbox / "discarded" / name):
        if path.is_file():
            return path
    return None


def backfill():
    inbox = Path(json.loads(SETTINGS.read_text())["inbox_folder"])
    db.init_db()
    with db.get_conn() as conn:
        games = db.rows_to_list(conn.execute(
            "SELECT * FROM matches WHERE COALESCE(raw_parse, '') = '' ORDER BY played_at"
        ).fetchall())
    for game in games:
        label = f"#{game['id']} {game['map']}"
        path = find_screenshot(game["screenshot_path"] or "", inbox) if game["screenshot_path"] else None
        if path is None:
            print(f"{label}: no screenshot found, skipped")
            continue
        parsed = parse_screenshot(str(path))
        if parsed.get("tab_type") != "TEAM":
            print(f"{label}: {path.name} is {parsed.get('tab_type')}, not a scoreboard, skipped")
            continue
        # The saved E/A/D came from SUMMARY or was confirmed by hand, so it finds his row.
        score, my_row = match_summary_row(game, parsed)
        parsed["my_row"] = my_row if score >= 2 else None
        parsed["backfilled"] = date.today().isoformat()
        me_stats = {k: game[k] for k in STATS}
        participants = [MatchParticipant(**p) for p in build_participants(parsed, None, me_stats)]
        with db.get_conn() as conn:
            conn.execute("UPDATE matches SET raw_parse=?, data_source='screenshot' WHERE id=?",
                         (json.dumps(parsed), game["id"]))
            conn.executemany(
                """INSERT INTO match_participants
                   (match_id, player_name, team, heroes, stats, name_confidence, slot, is_me)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(game["id"], p.player_name, p.team, json.dumps([h.dict() for h in p.heroes]),
                  json.dumps(p.stats), p.name_confidence, p.slot, int(p.is_me))
                 for p in participants],
            )
        print(f"{label}: {len(participants)} rows, my row {parsed['my_row']} (E/A/D matched {score}/3)")


if __name__ == "__main__":
    backfill()
