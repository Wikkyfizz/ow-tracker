import csv
import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "ow_tracker.db"
DATA_DIR = Path(__file__).parent / "data"
ROLES = ("Tank", "Damage", "Support")

# Comp archetypes a hero or map can lean toward. The sentinel ("Flex" for heroes,
# "Neutral" for maps) means "no lean / fits anything". A value may list one or two
# archetypes pipe-separated (e.g. "Dive|Brawl").
COMP_ARCHETYPES = ("Dive", "Poke", "Brawl")


def normalize_archetypes(value: str, sentinel: str):
    """Canonicalize an archetype value to the sentinel or a |-joined subset of
    Dive/Poke/Brawl in fixed order. Returns None if invalid (unknown token, or
    the sentinel mixed with real archetypes)."""
    sentinel = sentinel.title()
    parts = [p.strip().title() for p in (value or "").split("|") if p.strip()]
    if not parts or parts == [sentinel]:
        return sentinel
    if sentinel in parts or any(p not in COMP_ARCHETYPES for p in parts):
        return None
    return "|".join(a for a in COMP_ARCHETYPES if a in parts)


def normalize_affinity(value: str):
    """Map comp_affinity normalizer (no-lean sentinel = 'Neutral')."""
    return normalize_archetypes(value, "Neutral")


# Hero roster and map list are sourced from data/*.csv so they can be edited
# without touching code (and ship with the repo for out-of-the-box use).
def _load_maps_seed():
    rows = []
    with open(DATA_DIR / "maps.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            affinity = normalize_affinity(r["comp_affinity"])
            if affinity is None:
                raise ValueError(f"maps.csv: invalid comp_affinity {r['comp_affinity']!r} for map {r['name']!r}")
            rows.append((r["name"].strip(), r["game_mode"].strip(), affinity, (r["notes"] or "").strip()))
    return rows


def _load_heroes_seed():
    rows = []
    with open(DATA_DIR / "heroes.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            role = r["role"].strip().title()
            if role not in ROLES:
                raise ValueError(f"heroes.csv: invalid role {r['role']!r} for hero {r['name']!r}")
            archetype = normalize_archetypes(r["primary_archetype"], "Flex")
            if archetype is None:
                raise ValueError(f"heroes.csv: invalid primary_archetype {r['primary_archetype']!r} for hero {r['name']!r}")
            rows.append((r["name"].strip(), role, r["sub_role"].strip(), archetype))
    return rows


MAPS_SEED = _load_maps_seed()

HEROES_SEED = _load_heroes_seed()

SCHEMA = """
CREATE TABLE IF NOT EXISTS maps (
    name            TEXT PRIMARY KEY,
    game_mode       TEXT NOT NULL,
    comp_affinity   TEXT NOT NULL,
    notes           TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS heroes (
    name            TEXT PRIMARY KEY,
    role            TEXT NOT NULL,
    sub_role        TEXT NOT NULL,
    primary_archetype TEXT NOT NULL,
    icon_file       TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sessions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    date    DATE NOT NULL,
    notes   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    played_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    map             TEXT NOT NULL,
    outcome         TEXT NOT NULL CHECK(outcome IN ('Win','Loss','Draw')),
    my_heroes       TEXT NOT NULL DEFAULT '[]',
    enemy_heroes    TEXT NOT NULL DEFAULT '[]',
    my_comp         TEXT DEFAULT '',
    enemy_comp      TEXT DEFAULT '',
    rank_tier       TEXT DEFAULT '',
    rank_division   INTEGER DEFAULT NULL,
    rank_pct        REAL DEFAULT NULL,
    rank_score      REAL DEFAULT NULL,
    elims           INTEGER DEFAULT NULL,
    deaths          INTEGER DEFAULT NULL,
    assists         INTEGER DEFAULT NULL,
    damage          INTEGER DEFAULT NULL,
    healing         INTEGER DEFAULT NULL,
    mitigation      INTEGER DEFAULT NULL,
    game_length_s   INTEGER DEFAULT NULL,
    session_id      INTEGER DEFAULT NULL,
    notes           TEXT DEFAULT '',
    tags            TEXT DEFAULT '',
    bans            TEXT NOT NULL DEFAULT '[]',
    teammates       TEXT NOT NULL DEFAULT '[]',
    stack_size      INTEGER DEFAULT 1,
    screenshot_path TEXT DEFAULT '',
    data_source     TEXT DEFAULT 'manual',
    FOREIGN KEY (map) REFERENCES maps(name),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS tracked_players (
    name    TEXT PRIMARY KEY,
    alias   TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS career_baseline (
    hero            TEXT PRIMARY KEY,
    playtime_pct    REAL DEFAULT 0,
    win_rate        REAL DEFAULT NULL,
    games_played    INTEGER DEFAULT NULL,
    fetched_at      DATETIME DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS player_rank (
    role            TEXT PRIMARY KEY,
    rank_tier       TEXT DEFAULT '',
    rank_division   INTEGER DEFAULT NULL,
    fetched_at      DATETIME DEFAULT NULL
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _seed_if_empty(conn)


def _seed_if_empty(conn):
    if conn.execute("SELECT COUNT(*) FROM maps").fetchone()[0] > 0:
        return
    conn.executemany(
        "INSERT OR IGNORE INTO maps (name, game_mode, comp_affinity, notes) VALUES (?,?,?,?)",
        MAPS_SEED,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO heroes (name, role, sub_role, primary_archetype) VALUES (?,?,?,?)",
        HEROES_SEED,
    )
    pass  # player_rank seeded on first baseline fetch


def rank_to_score(tier: str, division: int, pct: float) -> float:
    TIERS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Master", "Grandmaster", "Champion"]
    try:
        tier_idx = TIERS.index(tier)
    except ValueError:
        return 0.0
    division_offset = 5 - division  # div 5 = 0, div 1 = 4
    return float(tier_idx * 500 + division_offset * 100 + pct)


def hero_archetypes(conn) -> dict:
    rows = conn.execute("SELECT name, primary_archetype FROM heroes").fetchall()
    return {r["name"]: r["primary_archetype"] for r in rows}


def hero_roles(conn) -> dict:
    rows = conn.execute("SELECT name, role FROM heroes").fetchall()
    return {r["name"]: r["role"] for r in rows}


# Comp identity is weighted toward the tank pick, which most defines whether a
# team plays Dive / Brawl / Poke. Weights are per hero; a standard 1-2-2 comp
# sums to 1.0 (Tank 0.40 + 2x Damage 0.15 + 2x Support 0.15).
# A hero may list multiple archetypes pipe-separated (e.g. "Brawl|Dive"); its
# weight is split equally among them, so a two-style hero reinforces whichever
# direction the committed picks set without tipping the comp on its own.
# "Flex" means fits everything / abstains from voting.
COMP_ROLE_WEIGHTS = {"Tank": 0.40, "Damage": 0.15, "Support": 0.15}


def derive_comp(hero_names: list, archetypes: dict, roles: dict) -> str:
    from collections import defaultdict
    weights = defaultdict(float)
    for h in hero_names:
        labels = [a.strip() for a in archetypes.get(h, "Flex").split("|")
                  if a.strip() and a.strip() != "Flex"]
        if not labels:
            continue  # flexible picks don't commit the team to a comp identity
        share = COMP_ROLE_WEIGHTS.get(roles.get(h, "Damage"), 0.15) / len(labels)
        for label in labels:
            weights[label] += share
    if not weights:
        return "Mixed"
    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and abs(ranked[0][1] - ranked[1][1]) < 1e-9:
        return "Mixed"  # no dominant archetype
    return ranked[0][0]


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]
