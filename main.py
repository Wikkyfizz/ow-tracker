import json
import os
import threading
import time
import shutil
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response

import db
import analytics
from models import (MatchCreate, MatchUpdate, MapUpdate, TrackedPlayer, Settings, ParsedMatch,
                    SessionCreate, SessionUpdate)

# OW_TRACKER_SETTINGS / OW_TRACKER_QUEUE let the e2e harness isolate state (see e2e/).
SETTINGS_PATH = Path(os.environ.get("OW_TRACKER_SETTINGS") or (Path(__file__).parent / "settings.json"))
QUEUE_PATH = Path(os.environ.get("OW_TRACKER_QUEUE") or (Path(__file__).parent / "inbox_queue.json"))
_queue_lock = threading.Lock()
_watcher_thread = None
_observer = None


# ── Startup / shutdown ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _start_watcher()
    yield


app = FastAPI(title="OW Tracker", lifespan=lifespan)


# ── Settings helpers ──────────────────────────────────────────────────────────

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text())
    return {"username": "DROWZY", "inbox_folder": "C:\\OW-Tracker\\inbox", "tracked_players": []}


def save_settings(s: dict):
    SETTINGS_PATH.write_text(json.dumps(s, indent=2))


# ── Queue helpers ─────────────────────────────────────────────────────────────

def load_queue() -> list:
    if QUEUE_PATH.exists():
        return json.loads(QUEUE_PATH.read_text())
    return []


def save_queue(q: list):
    QUEUE_PATH.write_text(json.dumps(q, indent=2))


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
        if not src.exists():
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
        while True:
            time.sleep(5)
    except Exception as e:
        print(f"[watcher] error: {e}")


def _handle_new_screenshot(path: str):
    from parser.pipeline import parse_screenshot
    settings = load_settings()
    try:
        result = parse_screenshot(path, username=settings.get("username", "DROWZY"))
        queue_add({
            "filename": Path(path).name,
            "path": path,
            "parsed": result,
            "added_at": datetime.now().isoformat(),
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

        session_id = body.session_id
        if session_id is None and not body.is_historical:
            session_id = _resolve_session(conn)

        # Timestamps are naive LOCAL time throughout (OCR reads the game's local
        # clock; sessions stamp datetime.now()) so session idle math and ordering
        # stay in one frame. Do not mix in UTC here.
        played_at = body.played_at or datetime.now()

        cur = conn.execute(
            """INSERT INTO matches
               (played_at, map, outcome, my_heroes, enemy_heroes, my_comp, enemy_comp,
                rank_tier, rank_division, rank_pct, rank_score,
                elims, deaths, assists, damage, healing, mitigation,
                game_length_s, session_id, notes, tags, bans, teammates,
                stack_size, screenshot_path, data_source,
                practiced, practice_notes, is_historical)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                body.stack_size,
                body.screenshot_path, body.data_source,
                body.practiced, body.practice_notes, int(body.is_historical),
            ),
        )
        match_id = cur.lastrowid
        if body.screenshot_path:
            queue_remove(Path(body.screenshot_path).name)
            _archive_screenshot(body.screenshot_path, "processed")
        if body.participants:
            conn.executemany(
                """INSERT INTO match_participants
                   (match_id, player_name, team, heroes, stats, name_confidence)
                   VALUES (?,?,?,?,?,?)""",
                [(match_id, p.player_name, p.team,
                  json.dumps([h.dict() for h in p.heroes]),
                  json.dumps(p.stats), p.name_confidence)
                 for p in body.participants]
            )
    return {"id": match_id}


@app.get("/api/matches/{match_id}")
def get_match(match_id: int):
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM matches WHERE id=?", (match_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Match not found")
    return dict(row)


@app.put("/api/matches/{match_id}")
def update_match(match_id: int, body: MatchUpdate):
    with db.get_conn() as conn:
        existing = conn.execute("SELECT id FROM matches WHERE id=?", (match_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Match not found")
        archetypes = db.hero_archetypes(conn)
        roles = db.hero_roles(conn)
        my_comp_names = [e.hero for e in (body.my_team_heroes or body.my_heroes)]
        my_comp = body.my_comp or db.derive_comp(my_comp_names, archetypes, roles)
        enemy_comp = body.enemy_comp or db.derive_comp([e.hero for e in body.enemy_heroes], archetypes, roles)
        rank_score = None
        if body.rank_tier and body.rank_division is not None and body.rank_pct is not None:
            rank_score = db.rank_to_score(body.rank_tier, body.rank_division, body.rank_pct)
        conn.execute(
            """UPDATE matches SET
               map=?, outcome=?, my_heroes=?, enemy_heroes=?, my_comp=?, enemy_comp=?,
               rank_tier=?, rank_division=?, rank_pct=?, rank_score=?,
               elims=?, deaths=?, assists=?, damage=?, healing=?, mitigation=?,
               game_length_s=?, notes=?, tags=?, bans=?, teammates=?, stack_size=?,
               data_source=?
               WHERE id=?""",
            (
                body.map, body.outcome,
                json.dumps([e.dict() for e in body.my_heroes]),
                json.dumps([e.dict() for e in body.enemy_heroes]),
                my_comp, enemy_comp,
                body.rank_tier, body.rank_division, body.rank_pct, rank_score,
                body.elims, body.deaths, body.assists,
                body.damage, body.healing, body.mitigation,
                body.game_length_s, body.notes, body.tags,
                json.dumps(body.bans), json.dumps(body.teammates), body.stack_size,
                body.data_source, match_id,
            ),
        )
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
    if item and item.get("path"):
        _archive_screenshot(item["path"], "discarded")
    return {"ok": True}


@app.post("/api/queue/parse-file")
def parse_file_manual(body: dict):
    path = body.get("path", "").strip()
    if not path or not Path(path).exists():
        raise HTTPException(400, f"File not found: {path}")
    queue_remove(Path(path).name)
    _handle_new_screenshot(path)
    return {"ok": True}


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
        from parser.icons import extract_portrait_crop, _portrait_cache, PORTRAITS_DIR
        crop = extract_portrait_crop(path, team, row)
        if crop is None:
            raise HTTPException(500, "Could not extract portrait crop")
        slug = _re.sub(r"[^a-z0-9]", "_", hero.lower()).strip("_")
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
    s = load_settings()
    s["username"] = body.username
    s["inbox_folder"] = body.inbox_folder
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
    battletag = settings.get("battletag") or settings.get("username", "DROWZY")

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
        result = parse_screenshot(tmp_path, username=settings.get("username", "DROWZY"))
    finally:
        os.unlink(tmp_path)
    return result


# ── Session resolution ────────────────────────────────────────────────────────

def _resolve_session(conn):
    """Return the active session id, or None if no session is running."""
    row = conn.execute(
        "SELECT id FROM sessions WHERE ended_at IS NULL AND started_at IS NOT NULL ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


# ── Static files ──────────────────────────────────────────────────────────────

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
