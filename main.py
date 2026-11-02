import json
import os
import threading
import time
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response

import db
import analytics
from models import (MatchCreate, MatchParticipant, MatchUpdate, MapUpdate, TrackedPlayer, Settings,
                    ParsedMatch, SessionCreate, SessionUpdate)
from parser.pipeline import build_participants

# OW_TRACKER_SETTINGS / OW_TRACKER_QUEUE let the e2e harness isolate state (see e2e/).
SETTINGS_PATH = Path(os.environ.get("OW_TRACKER_SETTINGS") or (Path(__file__).parent / "settings.json"))
QUEUE_PATH = Path(os.environ.get("OW_TRACKER_QUEUE") or (Path(__file__).parent / "inbox_queue.json"))
_queue_lock = threading.Lock()
_settings_lock = threading.Lock()
_watcher_thread = None
_observer = None
_last_backup = {}
BACKUP_INTERVAL_S = 24 * 3600


# ── Startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _start_watcher()
    threading.Thread(target=_backup_loop, daemon=True).start()
    yield


app = FastAPI(title="OW Tracker", lifespan=lifespan)


# ── Settings helpers ──────────────────────────────────────────────────────────

def _write_json(path: Path, data):
    """Replace the file in one step, so a reader or a crash never sees half of it.
    Windows refuses the swap while another thread has the file open for an instant."""
    tmp = path.with_name(f"{path.name}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.02)


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return {"username": "", "inbox_folder": "C:\\OW-Tracker\\inbox", "backup_folder": "", "tracked_players": []}


def save_settings(s: dict):
    _write_json(SETTINGS_PATH, s)


# ── Queue helpers ─────────────────────────────────────────────────────────────

def load_queue() -> list:
    if QUEUE_PATH.exists():
        return json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    return []


def save_queue(q: list):
    _write_json(QUEUE_PATH, q)


def queue_add(item: dict):
    with _queue_lock:
        q = load_queue()
        if not any(i["filename"] == item["filename"] for i in q):
            q.append(item)
            save_queue(q)


def queue_remove(filename: str):
    with _queue_lock:
        q = [i for i in load_queue() if i["filename"] != filename]
        save_queue(q)


def _archive_screenshot(path: str, subfolder: str = "processed"):
    """Move a screenshot to inbox/processed/ or inbox/discarded/ after handling."""
    try:
        src = Path(path)
        if not src.is_file():
            return
        dest_dir = src.parent / subfolder
        dest_dir.mkdir(exist_ok=True)
        shutil.move(str(src), dest_dir / src.name)
    except Exception as e:
        print(f"[archive] could not move {path}: {e}")


# ── Folder watcher ────────────────────────────────────────────────────────────

def _start_watcher():
    global _watcher_thread
    _watcher_thread = threading.Thread(target=_watch_loop, daemon=True)
    _watcher_thread.start()


def _watch_loop():
    global _observer
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory and event.src_path.lower().endswith((".png", ".jpg", ".jpeg")):
                    _handle_new_screenshot(event.src_path)

        if _observer is not None:
            try:
                _observer.stop()
                _observer.join(timeout=3)
            except Exception:
                pass

        settings = load_settings()
        inbox = Path(settings.get("inbox_folder", "C:\\OW-Tracker\\inbox"))
        inbox.mkdir(parents=True, exist_ok=True)
        _observer = Observer()
        _observer.schedule(Handler(), str(inbox), recursive=False)
        _observer.start()
        print(f"[watcher] watching {inbox}")
        _scan_inbox(inbox)
        while True:
            time.sleep(5)
    except Exception as e:
        print(f"[watcher] error: {e}")


MERGE_WINDOW_S = 15 * 60  # SUMMARY + TEAM of one game are captured close together
MISSED_SCREENSHOT_WINDOW_S = 24 * 3600


def _scan_inbox(inbox: Path):
    """Pick up screenshots saved while the app was off. Handled files leave the inbox
    root, so anything recent still there was missed; the age limit skips old leftovers."""
    cutoff = time.time() - MISSED_SCREENSHOT_WINDOW_S
    queued = set()
    for i in load_queue():
        queued.update({i["filename"], i.get("linked_filename")})
    missed = [p for p in inbox.iterdir()
              if p.suffix.lower() in (".png", ".jpg", ".jpeg") and p.is_file()
              and p.stat().st_mtime >= cutoff and p.name not in queued]
    for p in sorted(missed, key=lambda p: p.stat().st_mtime):
        _handle_new_screenshot(str(p))


def _damage_signature(parsed: dict):
    # DMG/MIT read reliably across screenshots, unlike E/A/D.
    rows = parsed.get("team_rows") or {}
    all_rows = rows.get("my_team", []) + rows.get("enemy_team", [])
    return tuple((r.get("damage"), r.get("mitigation")) for r in all_rows)


def _is_duplicate(parsed: dict, other: dict) -> bool:
    """True if `other`, a queued parse, already covers this screenshot's game."""
    if parsed.get("tab_type") == "SUMMARY":
        return bool(parsed.get("played_at")) and (parsed.get("played_at"), parsed.get("map")) == (
            other.get("played_at"), other.get("map"))
    if parsed.get("tab_type") == "TEAM":
        return bool(_damage_signature(parsed)) and _damage_signature(parsed) == _damage_signature(other)
    return False


def _find_merge_partner(queue: list, item: dict):
    """The queued screenshot most likely to be the other half of this game: the best
    stat match, then the closest in time. A coincidental 2 of 3 from a nearer screenshot
    must not beat a true 3 of 3."""
    from parser.pipeline import MIN_MATCHING_STATS, match_summary_row
    tab = item["parsed"].get("tab_type")
    wanted = {"SUMMARY": "TEAM", "TEAM": "SUMMARY"}.get(tab)
    if not wanted:
        return None
    candidates = [
        q for q in queue
        if q.get("parsed", {}).get("tab_type") == wanted and not q["parsed"].get("merged")
        and q.get("captured_at") and abs(q["captured_at"] - item["captured_at"]) <= MERGE_WINDOW_S
    ]
    def stat_score(q):
        summary, team = (item, q) if tab == "SUMMARY" else (q, item)
        return match_summary_row(summary["parsed"], team["parsed"])[0]
    scored = [(stat_score(q), q) for q in candidates]
    scored = [(s, q) for s, q in scored if s >= MIN_MATCHING_STATS]
    if not scored:
        return None
    return min(scored, key=lambda sq: (-sq[0], abs(sq[1]["captured_at"] - item["captured_at"])))[1]


def _warn_if_already_logged(parsed: dict):
    if not parsed.get("played_at"):
        return
    with db.get_conn() as conn:
        found = conn.execute(
            "SELECT id FROM matches WHERE played_at=? AND map=?", (parsed["played_at"], parsed.get("map"))
        ).fetchone()
    if found:
        parsed.setdefault("warnings", []).append(f"This game looks already logged (game #{found['id']})")


def _enqueue_screenshot(item: dict):
    """Add a parsed screenshot, dropping duplicates and merging it with its other half."""
    from parser.pipeline import merge_summary_team
    with _queue_lock:
        q = load_queue()
        if any(i["filename"] == item["filename"] for i in q):
            return
        parsed = item["parsed"]
        if any(_is_duplicate(parsed, i.get("parsed", {})) for i in q):
            print(f"[queue] duplicate of a queued game, discarding {item['filename']}")
            _archive_screenshot(item["path"], "discarded")
            return
        _warn_if_already_logged(parsed)
        partner = _find_merge_partner(q, item)
        if partner:
            summary, team = (item, partner) if parsed.get("tab_type") == "SUMMARY" else (partner, item)
            q[q.index(partner)] = {
                **team,
                "parsed": merge_summary_team(summary["parsed"], team["parsed"]),
                "linked_filename": summary["filename"],
                "linked_path": summary["path"],
            }
        else:
            q.append(item)
        save_queue(q)


def _archive_queue_item(item: dict, subfolder: str):
    for key in ("path", "linked_path"):
        if item.get(key):
            _archive_screenshot(item[key], subfolder)


def _learn_hero_names(item: dict, played_heroes: list, confirmed: list):
    """A hero the player had to pick by hand is read from its Summary card next time.
    The game is already saved, so a failure here must not fail the request."""
    from parser.hero_names import learn_cards
    try:
        learned = learn_cards(item.get("linked_path") or item["path"], played_heroes,
                              [(e.hero, e.pct) for e in confirmed])
        if learned:
            print(f"[hero names] learned {', '.join(learned)}")
    except Exception as e:
        print(f"[hero names] could not learn from {item.get('filename')}: {e}")


def _wait_until_readable(path: str, tries: int = 20, delay_s: float = 0.25):
    """The watcher fires as a file is created, while its writer may still hold it open.
    Reading then fails with a permission error or a truncated image."""
    from PIL import Image
    for _ in range(tries):
        try:
            with Image.open(path) as img:
                img.load()
            return
        except OSError:
            time.sleep(delay_s)


def _handle_new_screenshot(path: str):
    from parser.pipeline import parse_screenshot
    settings = load_settings()
    _wait_until_readable(path)
    try:
        result = parse_screenshot(path, username=settings.get("username", ""))
        _enqueue_screenshot({
            "filename": Path(path).name,
            "path": path,
            "parsed": result,
            "added_at": datetime.now().isoformat(),
            "captured_at": os.path.getmtime(path),
        })
    except Exception as e:
        print(f"[parser] error on {path}: {e}")
        queue_add({
            "filename": Path(path).name,
            "path": path,
            "parsed": {},
            "error": str(e),
            "added_at": datetime.now().isoformat(),
        })


# ── API: matches ──────────────────────────────────────────────────────────────

@app.get("/api/matches")
def list_matches(
    map: str = None,
    outcome: str = None,
    hero: str = None,
    limit: int = 200,
    offset: int = 0,
):
    with db.get_conn() as conn:
        q = "SELECT * FROM matches"
        params = []
        clauses = []
        if map:
            clauses.append("map = ?"); params.append(map)
        if outcome:
            clauses.append("outcome = ?"); params.append(outcome)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY played_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = db.rows_to_list(conn.execute(q, params).fetchall())

    if hero:
        rows = [r for r in rows if any(e["hero"] == hero for e in json.loads(r["my_heroes"] or "[]"))]

    return {"matches": rows, "total": len(rows)}


@app.post("/api/matches", status_code=201)
def create_match(body: MatchCreate):
    with db.get_conn() as conn:
        archetypes = db.hero_archetypes(conn)
        roles = db.hero_roles(conn)
        # Comp is a property of the *whole team*, so derive it from the full team
        # comp when we have it (TEAM-tab parse); fall back to my_heroes for manual
        # entry where only the played heroes are known.
        my_comp_names = [e.hero for e in (body.my_team_heroes or body.my_heroes)]
        enemy_hero_names = [e.hero for e in body.enemy_heroes]
        my_comp = body.my_comp or db.derive_comp(my_comp_names, archetypes, roles)
        enemy_comp = body.enemy_comp or db.derive_comp(enemy_hero_names, archetypes, roles)
        rank_score = None
        if body.rank_tier and body.rank_division is not None and body.rank_pct is not None:
            rank_score = db.rank_to_score(body.rank_tier, body.rank_division, body.rank_pct)

        session_id = _choose_session(conn, body)

        # Timestamps are naive LOCAL time throughout (OCR reads the game's local
        # clock; sessions stamp datetime.now()) so session idle math and ordering
        # stay in one frame. Do not mix in UTC here.
        played_at = body.played_at or datetime.now()

        # The queue item holds the parse as OCR read it. Keeping it is what lets OCR
        # accuracy be measured later against what was confirmed here.
        filename = Path(body.screenshot_path).name if body.screenshot_path else None
        item = next((i for i in load_queue() if i["filename"] == filename), None) if filename else None
        parsed = (item or {}).get("parsed") or None
        participants = body.participants
        if parsed and not participants:
            me_stats = {k: getattr(body, k)
                        for k in ("elims", "assists", "deaths", "damage", "healing", "mitigation")}
            participants = [MatchParticipant(**p)
                            for p in build_participants(parsed, body.team_slots, me_stats, body.team_names)]
        stack_size = 1 + len(body.teammates) if body.teammates else body.stack_size

        cur = conn.execute(
            """INSERT INTO matches
               (played_at, map, outcome, my_heroes, enemy_heroes, my_comp, enemy_comp,
                rank_tier, rank_division, rank_pct, rank_score,
                elims, deaths, assists, damage, healing, mitigation,
                game_length_s, session_id, notes, tags, bans, teammates,
                stack_size, screenshot_path, data_source,
                practiced, practice_notes, is_historical, raw_parse)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                played_at.isoformat(),
                body.map, body.outcome,
                json.dumps([e.dict() for e in body.my_heroes]),
                json.dumps([e.dict() for e in body.enemy_heroes]),
                my_comp, enemy_comp,
                body.rank_tier, body.rank_division, body.rank_pct, rank_score,
                body.elims, body.deaths, body.assists,
                body.damage, body.healing, body.mitigation,
                body.game_length_s, session_id,
                body.notes, body.tags,
                json.dumps(body.bans),
                json.dumps(body.teammates),
                stack_size,
                body.screenshot_path, "screenshot" if parsed else body.data_source,
                body.practiced, body.practice_notes, int(body.is_historical),
                json.dumps(parsed) if parsed else "",
            ),
        )
        match_id = cur.lastrowid
        if body.played_at:
            _fit_session_to_game(conn, session_id, body.played_at)
        if participants:
            conn.executemany(
                """INSERT INTO match_participants
                   (match_id, player_name, team, heroes, stats, name_confidence, slot, is_me)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [(match_id, p.player_name, p.team,
                  json.dumps([h.dict() for h in p.heroes]),
                  json.dumps(p.stats), p.name_confidence, p.slot, int(p.is_me))
                 for p in participants]
            )
    if parsed and parsed.get("played_heroes"):
        _learn_hero_names(item, parsed["played_heroes"], body.my_heroes)
    # Only once the game is committed: a failed save must leave its queue item and files.
    if body.screenshot_path:
        queue_remove(filename)
        _archive_screenshot(body.screenshot_path, "processed")
        if item and item.get("linked_path"):
            _archive_screenshot(item["linked_path"], "processed")
    return {"id": match_id}


@app.get("/api/matches/{match_id}")
def get_match(match_id: int):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        participants = db.rows_to_list(conn.execute(
            "SELECT * FROM match_participants WHERE match_id=? ORDER BY team, slot", (match_id,)
        ).fetchall())
    if not row:
        raise HTTPException(404, "Match not found")
    return {**dict(row), "participants": participants}


@app.put("/api/matches/{match_id}")
def update_match(match_id: int, body: MatchUpdate):
    with db.get_conn() as conn:
        existing = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Match not found")
        archetypes = db.hero_archetypes(conn)
        roles = db.hero_roles(conn)
        # Saved games don't keep the team's hero list on this row, so re-deriving from
        # my_heroes alone would turn a team comp into a comp of the player's picks.
        my_comp = body.my_comp or existing["my_comp"]
        if body.my_team_heroes:
            my_comp = db.derive_comp([e.hero for e in body.my_team_heroes], archetypes, roles)
        elif not my_comp:
            my_comp = db.derive_comp([e.hero for e in body.my_heroes], archetypes, roles)
        enemy_comp = body.enemy_comp or db.derive_comp([e.hero for e in body.enemy_heroes], archetypes, roles)
        stack_size = 1 + len(body.teammates) if body.teammates else 1
        played_at = body.played_at.isoformat() if body.played_at else existing["played_at"]
        session_id = _choose_session(conn, body, played_at=datetime.fromisoformat(played_at),
                                     keep=existing["session_id"])
        rank_score = None
        if body.rank_tier and body.rank_division is not None and body.rank_pct is not None:
            rank_score = db.rank_to_score(body.rank_tier, body.rank_division, body.rank_pct)
        conn.execute(
            """UPDATE matches SET
               played_at=?, map=?, outcome=?, my_heroes=?, enemy_heroes=?, my_comp=?, enemy_comp=?,
               rank_tier=?, rank_division=?, rank_pct=?, rank_score=?,
               elims=?, deaths=?, assists=?, damage=?, healing=?, mitigation=?,
               game_length_s=?, session_id=?, notes=?, tags=?, bans=?, teammates=?, stack_size=?,
               practiced=?, practice_notes=?
               WHERE id=?""",
            (
                played_at, body.map, body.outcome,
                json.dumps([e.dict() for e in body.my_heroes]),
                json.dumps([e.dict() for e in body.enemy_heroes]),
                my_comp, enemy_comp,
                body.rank_tier, body.rank_division, body.rank_pct, rank_score,
                body.elims, body.deaths, body.assists,
                body.damage, body.healing, body.mitigation,
                body.game_length_s, session_id, body.notes, body.tags,
                json.dumps(body.bans), json.dumps(body.teammates), stack_size,
                body.practiced, body.practice_notes, match_id,
            ),
        )
        _fit_session_to_game(conn, session_id, datetime.fromisoformat(played_at))
        # A session whose only game just moved out shouldn't linger as an empty card.
        old_session = existing["session_id"]
        if old_session and old_session != session_id and not conn.execute(
                "SELECT 1 FROM matches WHERE session_id=?", (old_session,)).fetchone():
            conn.execute("DELETE FROM sessions WHERE id=?", (old_session,))
        # Keep the player's scoreboard row in step with the corrected numbers.
        me = conn.execute("SELECT id, stats FROM match_participants WHERE match_id=? AND is_me=1",
                          (match_id,)).fetchone()
        if me:
            confirmed = {k: getattr(body, k) for k in ("elims", "assists", "deaths", "damage", "healing", "mitigation")}
            stats = {**json.loads(me["stats"]), **{k: v for k, v in confirmed.items() if v is not None}}
            conn.execute("UPDATE match_participants SET stats=? WHERE id=?", (json.dumps(stats), me["id"]))
        if body.team_names is not None:
            conn.execute("UPDATE match_participants SET player_name='' WHERE match_id=? AND team='ally'", (match_id,))
            for row, name in body.team_names.items():
                conn.execute("UPDATE match_participants SET player_name=? WHERE match_id=? AND team='ally' AND slot=?",
                             (name, match_id, int(row)))
    return {"ok": True}


@app.delete("/api/matches/{match_id}")
def delete_match(match_id: int):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM matches WHERE id=?", (match_id,))
    return {"ok": True}


# ── API: queue (pending screenshots) ─────────────────────────────────────────

@app.get("/api/queue")
def get_queue():
    return {"queue": load_queue()}


@app.delete("/api/queue/{filename}")
def discard_queue_item(filename: str):
    item = next((i for i in load_queue() if i["filename"] == filename), None)
    queue_remove(filename)
    if item:
        _archive_queue_item(item, "discarded")
    return {"ok": True}


@app.post("/api/queue/parse-file")
def parse_file_manual(body: dict):
    path = body.get("path", "").strip()
    if not path or not Path(path).is_file():
        raise HTTPException(400, f"File not found: {path}")
    queue_remove(Path(path).name)
    _handle_new_screenshot(path)
    return {"ok": True}


def _find_screenshot(filename: str):
    safe_name = Path(filename).name  # block path traversal
    candidates = []
    item = next((i for i in load_queue() if i["filename"] == safe_name), None)
    if item and item.get("path"):
        candidates.append(Path(item["path"]))
    inbox = Path(load_settings().get("inbox_folder", "C:\\OW-Tracker\\inbox"))
    candidates += [inbox / safe_name, inbox / "processed" / safe_name, inbox / "discarded" / safe_name]
    return next((p for p in candidates if p.is_file()), None)


@app.get("/api/screenshots/{filename}/allies")
def get_screenshot_allies(filename: str):
    """Each ally row of a scoreboard: the tracked player it matches, or a suggested name."""
    from parser.names import identify_allies
    path = _find_screenshot(filename)
    if path is None:
        return {"rows": [], "own_row": None}
    settings = load_settings()
    players = [p["name"] for p in settings.get("tracked_players", [])]
    return identify_allies(str(path), players, settings.get("username", ""))


@app.get("/api/screenshots/{filename}/name/{row}")
def get_name_image(filename: str, row: int):
    from parser.names import row_image_png
    path = _find_screenshot(filename)
    png = row_image_png(str(path), row) if path else None
    if png is None:
        raise HTTPException(404, "Name not found")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.post("/api/players/remember")
def remember_player(body: dict):
    """Record that a scoreboard row is this party member, adding them to the user's list."""
    from parser.names import remember_player as save_template
    filename, row, name = body.get("filename", ""), body.get("row"), (body.get("name") or "").strip()
    path = _find_screenshot(filename)
    if path is None or row is None or not name:
        raise HTTPException(400, "filename, row and name are all required")
    with _settings_lock:
        settings = load_settings()
        players = settings.setdefault("tracked_players", [])
        if not any(p["name"] == name for p in players):
            players.append({"name": name, "alias": ""})
            save_settings(settings)
            with db.get_conn() as conn:
                conn.execute("INSERT OR IGNORE INTO tracked_players (name, alias) VALUES (?, '')", (name,))
    return {"ok": True, "template_saved": save_template(str(path), int(row), name)}


@app.get("/api/queue/{filename}/image")
def get_queue_screenshot(filename: str):
    """Serve the full source screenshot for a queue item (spot-check OCR results).

    Falls back to the inbox and its processed/discarded archives so the image
    stays viewable right after the item is dequeued.
    """
    path = _find_screenshot(filename)
    if path is None:
        raise HTTPException(404, "Screenshot not found")
    media = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return Response(content=path.read_bytes(), media_type=media,
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/queue/{filename}/portrait/{team}/{row}")
def get_portrait_crop(filename: str, team: str, row: int):
    if team not in ("my", "enemy"):
        raise HTTPException(400, "team must be 'my' or 'enemy'")
    item = next((i for i in load_queue() if i["filename"] == filename), None)
    if not item:
        raise HTTPException(404, "Not in queue")
    path = item.get("path", "")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Screenshot not found")
    try:
        import cv2
        from parser.icons import extract_portrait_crop
        crop = extract_portrait_crop(path, team, row)
        if crop is None:
            raise HTTPException(500, "Could not extract portrait")
        scaled = cv2.resize(crop, (140, 112), interpolation=cv2.INTER_LANCZOS4)
        _, buf = cv2.imencode(".png", scaled)
        return Response(content=buf.tobytes(), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/heroes/template")
def save_hero_template(body: dict):
    import re as _re
    filename = body.get("filename", "")
    team = body.get("team", "")
    row = body.get("row")
    hero = body.get("hero", "")
    if not filename or team not in ("my", "enemy") or row is None or not hero:
        raise HTTPException(400, "filename, team (my/enemy), row, hero are all required")
    if hero.startswith("Unknown"):
        raise HTTPException(400, "Cannot save template for an unknown hero")
    item = next((i for i in load_queue() if i["filename"] == filename), None)
    if not item:
        raise HTTPException(404, "Not in queue")
    path = item.get("path", "")
    if not path or not Path(path).exists():
        raise HTTPException(404, "Screenshot not found")
    try:
        import cv2
        from parser.icons import extract_portrait_crop, _portrait_cache, PORTRAITS_DIR, _CSV_NAME_ALIASES
        crop = extract_portrait_crop(path, team, row)
        if crop is None:
            raise HTTPException(500, "Could not extract portrait crop")
        # The picker sends CSV names; templates use code names ("Soldier: 76" -> soldier_76).
        code_name = _CSV_NAME_ALIASES.get(hero, hero)
        slug = _re.sub(r"[^a-z0-9]", "_", code_name.lower()).strip("_")
        dest = PORTRAITS_DIR / team / f"{slug}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), crop)
        _portrait_cache["my"].clear()
        _portrait_cache["enemy"].clear()
        return {"saved": True, "path": str(dest), "hero": hero, "slug": slug}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/watcher/restart")
def restart_watcher():
    _start_watcher()
    return {"ok": True}


# ── API: analytics ────────────────────────────────────────────────────────────

@app.get("/api/analytics/dashboard")
def api_dashboard():
    return analytics.dashboard_summary()


@app.get("/api/analytics/hero-winrates")
def api_hero_winrates(map: str = None, outcome: str = None):
    f = {}
    if map: f["map"] = map
    return analytics.hero_winrates(f)


@app.get("/api/analytics/map-winrates")
def api_map_winrates():
    return analytics.map_winrates()


@app.get("/api/analytics/comp-matchups")
def api_comp_matchups():
    return analytics.comp_matchups()


@app.get("/api/analytics/teammate-winrates")
def api_teammate_winrates():
    return analytics.teammate_winrates()


@app.get("/api/analytics/stack-winrates")
def api_stack_winrates():
    return analytics.stack_winrates()


@app.get("/api/analytics/ban-stats")
def api_ban_stats():
    return analytics.ban_stats()


@app.get("/api/analytics/sr-timeline")
def api_sr_timeline():
    return analytics.sr_timeline()


@app.get("/api/analytics/hero-map")
def api_hero_map():
    return analytics.hero_map_winrates()


@app.get("/api/analytics/vs-enemy-hero")
def api_vs_enemy_hero():
    return analytics.vs_enemy_hero()


@app.get("/api/analytics/role-matchups")
def api_role_matchups(role: str = "Tank", grain: str = "hero"):
    return analytics.role_matchups(role, grain)


# ── API: maps ─────────────────────────────────────────────────────────────────

@app.get("/api/maps")
def list_maps():
    with db.get_conn() as conn:
        return db.rows_to_list(conn.execute("SELECT * FROM maps ORDER BY game_mode, name").fetchall())


@app.put("/api/maps/{name}")
def update_map(name: str, body: MapUpdate):
    affinity = db.normalize_affinity(body.comp_affinity)
    if affinity is None:
        raise HTTPException(400, f"Invalid comp_affinity: {body.comp_affinity!r}")
    with db.get_conn() as conn:
        if body.notes is None:
            conn.execute("UPDATE maps SET comp_affinity=? WHERE name=?", (affinity, name))
        else:
            conn.execute(
                "UPDATE maps SET comp_affinity=?, notes=? WHERE name=?",
                (affinity, body.notes, name),
            )
    return {"ok": True}


# ── API: heroes ───────────────────────────────────────────────────────────────

@app.get("/api/heroes")
def list_heroes():
    with db.get_conn() as conn:
        return db.rows_to_list(conn.execute("SELECT * FROM heroes ORDER BY role, name").fetchall())


# ── API: settings ─────────────────────────────────────────────────────────────

@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.put("/api/settings")
def update_settings(body: Settings):
    with _settings_lock:
        s = load_settings()
        s["username"] = body.username
        s["battletag"] = body.battletag
        s["inbox_folder"] = body.inbox_folder
        s["backup_folder"] = body.backup_folder
        s["tracked_players"] = [p.dict() for p in body.tracked_players]
        save_settings(s)
    # sync to DB
    with db.get_conn() as conn:
        conn.execute("DELETE FROM tracked_players")
        conn.executemany(
            "INSERT INTO tracked_players (name, alias) VALUES (?,?)",
            [(p.name, p.alias) for p in body.tracked_players],
        )
    return {"ok": True}


# ── Backup ────────────────────────────────────────────────────────────────────

def _run_backup() -> dict:
    from backup import run_backup
    from parser.names import NAMES_DIR
    settings = load_settings()
    folder = settings.get("backup_folder", "")
    if not folder:
        return {"error": "No backup folder set"}
    try:
        result = run_backup(folder, db.DB_PATH, Path(settings.get("inbox_folder", "")), SETTINGS_PATH, NAMES_DIR)
    except Exception as e:
        print(f"[backup] failed: {e}")
        result = {"error": str(e), "at": datetime.now().isoformat(timespec="seconds")}
    _last_backup.clear()
    _last_backup.update(result)
    return result


def _backup_loop():
    while True:
        _run_backup()
        time.sleep(BACKUP_INTERVAL_S)


@app.get("/api/backup")
def get_backup_status():
    return _last_backup or {"error": "No backup has run yet"}


@app.post("/api/backup")
def backup_now():
    return _run_backup()


# ── Session helpers ───────────────────────────────────────────────────────────

def _auto_close_sessions(conn):
    """Auto-close open sessions idle >1hr; scrap empty sessions idle >1hr."""
    now = datetime.now()
    open_sessions = conn.execute(
        "SELECT id, started_at FROM sessions WHERE ended_at IS NULL AND started_at IS NOT NULL"
    ).fetchall()
    for s in open_sessions:
        count = conn.execute("SELECT COUNT(*) FROM matches WHERE session_id=?", (s["id"],)).fetchone()[0]
        if count == 0:
            started = datetime.fromisoformat(s["started_at"])
            if (now - started).total_seconds() > 3600:
                conn.execute("DELETE FROM sessions WHERE id=?", (s["id"],))
        else:
            last = conn.execute(
                "SELECT MAX(played_at) as lp FROM matches WHERE session_id=?", (s["id"],)
            ).fetchone()
            if last and last["lp"]:
                last_played = datetime.fromisoformat(last["lp"])
                if (now - last_played).total_seconds() > 3600:
                    conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (last["lp"], s["id"]))


# ── API: sessions ─────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def list_sessions():
    with db.get_conn() as conn:
        _auto_close_sessions(conn)
        rows = db.rows_to_list(conn.execute(
            """SELECT s.*,
               COUNT(m.id) as match_count,
               SUM(CASE WHEN m.outcome='Win'  THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN m.outcome='Loss' THEN 1 ELSE 0 END) as losses
               FROM sessions s
               LEFT JOIN matches m ON m.session_id = s.id
               GROUP BY s.id
               ORDER BY COALESCE(s.started_at, s.date) DESC"""
        ).fetchall())
    return rows


@app.get("/api/sessions/active")
def get_active_session():
    with db.get_conn() as conn:
        _auto_close_sessions(conn)
        row = conn.execute(
            "SELECT * FROM sessions WHERE ended_at IS NULL AND started_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return {"session": dict(row) if row else None}


@app.get("/api/sessions/for-time")
def session_for_time(played_at: Optional[datetime] = None):
    """The session a game would join on its own, or null when the player has to choose."""
    with db.get_conn() as conn:
        _auto_close_sessions(conn)
        session_id = _session_for_time(conn, played_at) if played_at else _resolve_session(conn)
    return {"session_id": session_id}


@app.post("/api/sessions", status_code=201)
def create_session(body: SessionCreate):
    with db.get_conn() as conn:
        _auto_close_sessions(conn)
        existing = conn.execute(
            "SELECT id FROM sessions WHERE ended_at IS NULL AND started_at IS NOT NULL"
        ).fetchone()
        if existing:
            return {"id": existing["id"]}
        now = datetime.now().isoformat()
        today = datetime.now().date().isoformat()
        cur = conn.execute(
            "INSERT INTO sessions (date, started_at, goal, focus_mode) VALUES (?,?,?,?)",
            (today, now, body.goal, int(body.focus_mode))
        )
    return {"id": cur.lastrowid}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int):
    with db.get_conn() as conn:
        if not conn.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone():
            raise HTTPException(404, "Session not found")
        conn.execute("UPDATE sessions SET ended_at=? WHERE id=?",
                     (datetime.now().isoformat(), session_id))
    return {"ok": True}


@app.patch("/api/sessions/{session_id}")
def update_session(session_id: int, body: SessionUpdate):
    with db.get_conn() as conn:
        if not conn.execute("SELECT id FROM sessions WHERE id=?", (session_id,)).fetchone():
            raise HTTPException(404, "Session not found")
        updates = {}
        if body.goal        is not None: updates["goal"]       = body.goal
        if body.focus_mode  is not None: updates["focus_mode"] = int(body.focus_mode)
        if body.name        is not None: updates["name"]       = body.name
        if body.notes       is not None: updates["notes"]      = body.notes
        if updates:
            sets = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE sessions SET {sets} WHERE id=?", (*updates.values(), session_id))
    return {"ok": True}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: int):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        matches = db.rows_to_list(conn.execute(
            "SELECT * FROM matches WHERE session_id=? ORDER BY played_at ASC", (session_id,)
        ).fetchall())
    return {**dict(row), "matches": matches}


# ── API: baseline ─────────────────────────────────────────────────────────────

@app.post("/api/baseline/fetch")
async def fetch_baseline():
    import httpx
    settings = load_settings()
    battletag = settings.get("battletag") or settings.get("username", "")

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            stats_r = await client.get(f"https://overfast-api.tekrop.fr/players/{battletag}/stats/summary?gamemode=competitive")
            stats_r.raise_for_status()
            stats = stats_r.json()
        except Exception as e:
            raise HTTPException(502, f"OverFast stats error: {e}")

        try:
            profile_r = await client.get(f"https://overfast-api.tekrop.fr/players/{battletag}")
            profile_r.raise_for_status()
            profile = profile_r.json()
        except Exception:
            profile = {}

    # heroes is a dict: {"genji": {games_played, games_won, winrate, time_played, ...}, ...}
    heroes_dict = stats.get("heroes", {})
    total_time = sum(h.get("time_played", 0) for h in heroes_dict.values()) or 1
    now = datetime.now().isoformat()

    with db.get_conn() as conn:
        conn.execute("DELETE FROM career_baseline")
        conn.executemany(
            "INSERT INTO career_baseline (hero, playtime_pct, win_rate, games_played, fetched_at) VALUES (?,?,?,?,?)",
            [
                (
                    name.title().replace("_", " "),
                    round(data.get("time_played", 0) / total_time * 100, 2),
                    round(data.get("winrate", 0) / 100, 4) if data.get("winrate") is not None else None,
                    data.get("games_played"),
                    now,
                )
                for name, data in heroes_dict.items()
            ],
        )

        # Store per-role ranks from profile
        comp = profile.get("summary", {}).get("competitive", {}).get("pc", {})
        rank_rows = []
        role_map = {"tank": "Tank", "damage": "Damage", "support": "Support", "open": "Open Queue"}
        for api_key, label in role_map.items():
            role_data = comp.get(api_key)
            if role_data:
                rank_rows.append((
                    label,
                    role_data.get("division", "").title(),
                    role_data.get("tier"),
                    now,
                ))
        if rank_rows:
            conn.execute("DELETE FROM player_rank")
            conn.executemany(
                "INSERT INTO player_rank (role, rank_tier, rank_division, fetched_at) VALUES (?,?,?,?)",
                rank_rows,
            )

    return {"heroes_fetched": len(heroes_dict), "roles_fetched": len(rank_rows)}


@app.get("/api/baseline")
def get_baseline():
    with db.get_conn() as conn:
        rows = db.rows_to_list(conn.execute("SELECT * FROM career_baseline ORDER BY playtime_pct DESC").fetchall())
        ranks = db.rows_to_list(conn.execute("SELECT * FROM player_rank ORDER BY role").fetchall())
    return {"heroes": rows, "ranks": ranks}


# ── API: parse (manual trigger) ───────────────────────────────────────────────

@app.post("/api/parse")
async def parse_upload(file: UploadFile = File(...)):
    from parser.pipeline import parse_screenshot
    import tempfile, os
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        settings = load_settings()
        result = parse_screenshot(tmp_path, username=settings.get("username", ""))
    finally:
        os.unlink(tmp_path)
    return result


# ── Session resolution ────────────────────────────────────────────────────────

SESSION_START_GRACE_S = 3600  # people often hit Start a game or two into a sitting
SESSION_IDLE_S = 3600         # same limit as _auto_close_sessions


def _session_for_time(conn, played_at: datetime):
    """The session a game belongs to by when it was played, not when it was confirmed.
    Otherwise confirming yesterday's screenshot files it under today's session."""
    rows = conn.execute(
        """SELECT s.id, s.started_at, s.ended_at, MAX(m.played_at) AS last_game
           FROM sessions s LEFT JOIN matches m ON m.session_id = s.id
           WHERE s.started_at IS NOT NULL
           GROUP BY s.id ORDER BY s.ended_at IS NULL DESC, s.started_at DESC"""
    ).fetchall()
    for s in rows:
        started = datetime.fromisoformat(s["started_at"])
        if not s["ended_at"]:
            ended = datetime.now()
        else:
            ended = datetime.fromisoformat(s["ended_at"])
            # Auto-close stops the clock at the last game, so games confirmed in a batch
            # after the idle limit still join their sitting. End Session stamps a later
            # time and means it: nothing played after that joins.
            if s["last_game"] and ended <= datetime.fromisoformat(s["last_game"]):
                ended += timedelta(seconds=SESSION_IDLE_S)
        if (started - played_at).total_seconds() <= SESSION_START_GRACE_S and played_at <= ended:
            return s["id"]
    return None


def _choose_session(conn, body, played_at=None, keep=None):
    """Every game belongs to a session: a new one, one the player picked, or `keep`
    (the game's current session, on edit). Otherwise the one its time falls in."""
    played_at = played_at or body.played_at
    if body.new_session:
        return _new_session_for_game(conn, played_at or datetime.now())
    if body.session_id is not None:
        if not conn.execute("SELECT 1 FROM sessions WHERE id=?", (body.session_id,)).fetchone():
            raise HTTPException(400, "Session not found")
        return body.session_id
    session_id = keep or (_session_for_time(conn, played_at) if played_at else _resolve_session(conn))
    if session_id is None:
        raise HTTPException(400, "Choose a session: start a new one or pick an old one")
    return session_id


def _new_session_for_game(conn, played_at: datetime) -> int:
    """Start a session at the game's own time. It replaces a running session this game
    came after, and is already over if the game is older than the idle limit."""
    running = conn.execute(
        """SELECT s.id, s.started_at, MAX(m.played_at) AS last_game
           FROM sessions s LEFT JOIN matches m ON m.session_id = s.id
           WHERE s.ended_at IS NULL AND s.started_at IS NOT NULL GROUP BY s.id"""
    ).fetchall()
    for s in running:
        if played_at < datetime.fromisoformat(s["last_game"] or s["started_at"]):
            continue
        if s["last_game"]:
            conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (s["last_game"], s["id"]))
        else:
            conn.execute("DELETE FROM sessions WHERE id=?", (s["id"],))
    over = (datetime.now() - played_at).total_seconds() > SESSION_IDLE_S
    cur = conn.execute(
        "INSERT INTO sessions (date, started_at, ended_at) VALUES (?,?,?)",
        (played_at.date().isoformat(), played_at.isoformat(), played_at.isoformat() if over else None)
    )
    return cur.lastrowid


def _fit_session_to_game(conn, session_id: int, played_at: datetime):
    """Stretch a session's times to cover a game added earlier or later than them."""
    s = conn.execute("SELECT started_at, ended_at FROM sessions WHERE id=?", (session_id,)).fetchone()
    if s["started_at"] and played_at < datetime.fromisoformat(s["started_at"]):
        conn.execute("UPDATE sessions SET started_at=?, date=? WHERE id=?",
                     (played_at.isoformat(), played_at.date().isoformat(), session_id))
    if s["ended_at"] and played_at > datetime.fromisoformat(s["ended_at"]):
        conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (played_at.isoformat(), session_id))


def _resolve_session(conn):
    """Return the active session id, or None if no session is running."""
    row = conn.execute(
        "SELECT id FROM sessions WHERE ended_at IS NULL AND started_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


# ── Static files ──────────────────────────────────────────────────────────────

class RevalidatedStaticFiles(StaticFiles):
    """Make browsers check for a new app.js or style.css on every load. Without this
    they guess a cache lifetime and a plain reload can keep running old code."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", RevalidatedStaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
