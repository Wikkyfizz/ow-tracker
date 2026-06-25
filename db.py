import sqlite3
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "ow_tracker.db"

MAPS_SEED = [
    # Control
    ("Antarctic Peninsula", "Control", "Brawl", "Tight corridors, close range"),
    ("Busan", "Control", "Neutral", "Mixed geometry across three points"),
    ("Ilios", "Control", "Poke", "Open sightlines, elevated positions"),
    ("Lijiang Tower", "Control", "Dive", "Vertical flanks, multiple levels"),
    ("Nepal", "Control", "Brawl", "Narrow shrine/temple chokepoints"),
    ("Oasis", "Control", "Dive", "Open plazas, vertical movement"),
    ("Samoa", "Control", "Neutral", "Mixed beach/industrial geometry"),
    # Escort
    ("Circuit Royal", "Escort", "Poke", "Wide boulevards, long sightlines"),
    ("Dorado", "Escort", "Brawl", "Tight street corridors"),
    ("Havana", "Escort", "Poke", "Long canal sightlines, open docks"),
    ("Junkertown", "Escort", "Poke", "Long first-stretch favors spam"),
    ("Rialto", "Escort", "Poke", "Open canals, bridge sight-lines"),
    ("Route 66", "Escort", "Poke", "Gas station gauntlet, long stretches"),
    ("Shambali Monastery", "Escort", "Poke", "Long hallways, elevated sniper perches"),
    ("Watchpoint: Gibraltar", "Escort", "Poke", "Long corridors, open final"),
    # Hybrid
    ("Blizzard World", "Hybrid", "Brawl", "Tight theme-park corridors"),
    ("Eichenwalde", "Hybrid", "Brawl", "Castle gate chokepoints"),
    ("Hollywood", "Hybrid", "Neutral", "Mixed open + tight interior"),
    ("King's Row", "Hybrid", "Brawl", "Narrow streets, close engagements"),
    ("Midtown", "Hybrid", "Neutral", "Wide avenues but flanking alleys"),
    ("Numbani", "Hybrid", "Dive", "Open courtyard, vertical building access"),
    ("Paraíso", "Hybrid", "Dive", "Open carnival, vertical rooftops"),
    # Push
    ("Colosseo", "Push", "Dive", "Open arena, high ground accessible"),
    ("Esperança", "Push", "Poke", "Wide streets, long sightlines"),
    ("New Queen Street", "Push", "Brawl", "Narrow urban corridors"),
    ("Runasapi", "Push", "Neutral", "Balanced ruins geometry"),
    # Flashpoint
    ("New Junk City", "Flashpoint", "Poke", "Industrial open zones"),
    ("Suravasa", "Flashpoint", "Neutral", "Temple complex, mixed range"),
]

HEROES_SEED = [
    # Tanks
    ("D.Va",            "Tank", "Initiator", "Dive"),
    ("Doomfist",        "Tank", "Initiator", "Dive"),
    ("Domina",          "Tank", "Stalwart",  "Brawl"),
    ("Hazard",          "Tank", "Stalwart",  "Brawl"),
    ("Junker Queen",    "Tank", "Stalwart",  "Brawl"),
    ("Mauga",           "Tank", "Bruiser",   "Brawl"),
    ("Orisa",           "Tank", "Bruiser",   "Poke"),
    ("Ramattra",        "Tank", "Stalwart",  "Brawl"),
    ("Reinhardt",       "Tank", "Stalwart",  "Brawl"),
    ("Roadhog",         "Tank", "Bruiser",   "Brawl"),
    ("Sigma",           "Tank", "Stalwart",  "Poke"),
    ("Winston",         "Tank", "Initiator", "Dive"),
    ("Wrecking Ball",   "Tank", "Initiator", "Dive"),
    ("Zarya",           "Tank", "Bruiser",   "Brawl"),
    # Damage
    ("Ashe",            "Damage", "Hitscan",    "Poke"),
    ("Bastion",         "Damage", "Projectile", "Poke"),
    ("Cassidy",         "Damage", "Hitscan",    "Flex"),
    ("Echo",            "Damage", "Projectile", "Dive"),
    ("Anran",           "Damage", "Flanker",    "Dive"),
    ("Freja",           "Damage", "Hitscan",    "Dive"),
    ("Genji",           "Damage", "Projectile", "Dive"),
    ("Hanzo",           "Damage", "Projectile", "Poke"),
    ("Junkrat",         "Damage", "Projectile", "Brawl"),
    ("Mei",             "Damage", "Projectile", "Brawl"),
    ("Pharah",          "Damage", "Projectile", "Poke"),
    ("Reaper",          "Damage", "Flanker",    "Brawl"),
    ("Sierra",          "Damage", "Hitscan",    "Poke"),
    ("Sojourn",         "Damage", "Hitscan",    "Poke"),
    ("Soldier: 76",     "Damage", "Hitscan",    "Flex"),
    ("Sombra",          "Damage", "Flanker",    "Dive"),
    ("Symmetra",        "Damage", "Projectile", "Brawl"),
    ("Torbjörn",        "Damage", "Hitscan",    "Poke"),
    ("Tracer",          "Damage", "Flanker",    "Dive"),
    ("Venture",         "Damage", "Projectile", "Dive"),
    ("Widowmaker",      "Damage", "Sniper",     "Poke"),
    ("Emre",            "Damage", "Hitscan",    "Poke"),
    ("Shion",           "Damage", "Flex",       "Dive"),
    ("Vendetta",        "Damage", "Flex",       "Dive"),
    # Support
    ("Ana",             "Support", "Healer",    "Poke"),
    ("Baptiste",        "Support", "Healer",    "Flex"),
    ("Brigitte",        "Support", "Defensive", "Brawl"),
    ("Illari",          "Support", "Healer",    "Poke"),
    ("Juno",            "Support", "Utility",   "Flex"),
    ("Kiriko",          "Support", "Healer",    "Dive"),
    ("Lifeweaver",      "Support", "Utility",   "Flex"),
    ("Lucio",           "Support", "Utility",   "Brawl"),
    ("Mercy",           "Support", "Healer",    "Flex"),
    ("Moira",           "Support", "Defensive", "Brawl"),
    ("Zenyatta",        "Support", "Healer",    "Poke"),
    ("Mizuki",          "Support", "Flex Support", "Dive"),
    ("Jetpack Cat",     "Support", "Flex Support", "Flex"),
    ("Wuyang",          "Support", "Main Support", "Flex"),
]

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
COMP_ROLE_WEIGHTS = {"Tank": 0.40, "Damage": 0.15, "Support": 0.15}


def derive_comp(hero_names: list, archetypes: dict, roles: dict) -> str:
    from collections import defaultdict
    weights = defaultdict(float)
    for h in hero_names:
        arch = archetypes.get(h, "Flex")
        if arch == "Flex":
            continue  # flexible picks don't commit the team to a comp identity
        weights[arch] += COMP_ROLE_WEIGHTS.get(roles.get(h, "Damage"), 0.15)
    if not weights:
        return "Mixed"
    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "Mixed"  # no dominant archetype
    return ranked[0][0]


def rows_to_list(rows) -> list:
    return [dict(r) for r in rows]
