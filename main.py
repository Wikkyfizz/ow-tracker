import json
import threading
import time
import shutil
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

import db
import analytics
from models import MatchCreate, MatchUpdate, MapUpdate, TrackedPlayer, Settings, ParsedMatch

SETTINGS_PATH = Path(__file__).parent / "settings.json"
QUEUE_PATH = Path(__file__).parent / "inbox_queue.json"
_queue_lock = threading.Lock()
_watcher_thread = None


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


# ── Folder watcher ────────────────────────────────────────────────────────────

def _start_watcher():
    global _watcher_thread
    _watcher_thread = threading.Thread(target=_watch_loop, daemon=True)
    _watcher_thread.start()


def _watch_loop():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory and event.src_path.lower().endswith(".png"):
                    _handle_new_screenshot(event.src_path)

        settings = load_settings()
        inbox = Path(settings.get("inbox_folder", "C:\\OW-Tracker\\inbox"))
        inbox.mkdir(parents=True, exist_ok=True)
        observer = Observer()
        observer.schedule(Handler(), str(inbox), recursive=False)
        observer.start()
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
            "added_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        print(f"[parser] error on {path}: {e}")
        queue_add({
            "filename": Path(path).name,
            "path": path,
            "parsed": {},
            "error": str(e),
            "added_at": datetime.utcnow().isoformat(),
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
        my_hero_names = [e.hero for e in body.my_heroes]
        enemy_hero_names = [e.hero for e in body.enemy_heroes]
        my_comp = body.my_comp or db.derive_comp(my_hero_names, archetypes)
        enemy_comp = body.enemy_comp or db.derive_comp(enemy_hero_names, archetypes)
        rank_score = None
        if body.rank_tier and body.rank_division is not None and body.rank_pct is not None:
            rank_score = db.rank_to_score(body.rank_tier, body.rank_division, body.rank_pct)

        # resolve session
        session_id = body.session_id
        if session_id is None:
            session_id = _resolve_session(conn)

        played_at = body.played_at or datetime.utcnow()

        cur = conn.execute(
            """INSERT INTO matches
               (played_at, map, outcome, my_heroes, enemy_heroes, my_comp, enemy_comp,
                rank_tier, rank_division, rank_pct, rank_score,
                elims, deaths, assists, damage, healing, mitigation,
                game_length_s, session_id, notes, tags, bans, teammates,
                stack_size, screenshot_path, data_source)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            ),
        )
        match_id = cur.lastrowid
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
        my_comp = body.my_comp or db.derive_comp([e.hero for e in body.my_heroes], archetypes)
        enemy_comp = body.enemy_comp or db.derive_comp([e.hero for e in body.enemy_heroes], archetypes)
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
    queue_remove(filename)
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


# ── API: maps ─────────────────────────────────────────────────────────────────

@app.get("/api/maps")
def list_maps():
    with db.get_conn() as conn:
        return db.rows_to_list(conn.execute("SELECT * FROM maps ORDER BY game_mode, name").fetchall())


@app.put("/api/maps/{name}")
def update_map(name: str, body: MapUpdate):
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE maps SET comp_affinity=?, notes=? WHERE name=?",
            (body.comp_affinity, body.notes, name),
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


# ── API: sessions ─────────────────────────────────────────────────────────────

@app.get("/api/sessions")
def list_sessions():
    with db.get_conn() as conn:
        rows = db.rows_to_list(
            conn.execute(
                """SELECT s.*, COUNT(m.id) as match_count
                   FROM sessions s
                   LEFT JOIN matches m ON m.session_id = s.id
                   GROUP BY s.id ORDER BY s.date DESC"""
            ).fetchall()
        )
    return rows


@app.post("/api/sessions", status_code=201)
def create_session(notes: str = ""):
    with db.get_conn() as conn:
        cur = conn.execute("INSERT INTO sessions (date, notes) VALUES (?,?)", (datetime.utcnow().date().isoformat(), notes))
    return {"id": cur.lastrowid}


# ── API: baseline ─────────────────────────────────────────────────────────────

@app.post("/api/baseline/fetch")
async def fetch_baseline():
    import httpx
    settings = load_settings()
    battletag = settings.get("battletag") or settings.get("username", "DROWZY")

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            stats_r = await client.get(f"https://overfast-api.tekrop.fr/players/{battletag}/stats/summary")
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
    now = datetime.utcnow().isoformat()

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

def _resolve_session(conn) -> int:
    today = datetime.utcnow().date().isoformat()
    row = conn.execute("SELECT id FROM sessions WHERE date=?", (today,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO sessions (date) VALUES (?)", (today,))
    return cur.lastrowid


# ── Static files ──────────────────────────────────────────────────────────────

app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
