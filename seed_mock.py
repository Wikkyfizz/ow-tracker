"""
Seed mock data for UI review.
Run from project root:  python seed_mock.py
Run with --clear flag:  python seed_mock.py --clear  (wipes existing data first)

Won't overwrite if sessions already exist (unless --clear is passed).
"""
import json
import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "ow_tracker.db"


def get_conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def rank_score(tier, div, pct):
    TIERS = ["Bronze", "Silver", "Gold", "Platinum", "Diamond",
             "Master", "Grandmaster", "Champion"]
    return float(TIERS.index(tier) * 500 + (5 - div) * 100 + pct)


def jheroes(pairs):
    return json.dumps([{"hero": h, "pct": p} for h, p in pairs])


def jenemies(heroes):
    return json.dumps([{"hero": h, "pct": 100} for h in heroes])


def jb(bans):
    return json.dumps(bans)


# ── Data ──────────────────────────────────────────────────────────────────────
# Each session: dict with metadata + list of match dicts.
# rank: (tier, division, pct)  — post-game rank
# heroes: [(hero, pct), ...]   — my heroes this game
# eheroes: [hero, ...]         — detected enemy heroes
# bans: [hero, ...]            — heroes banned this game

BASE = datetime(2026, 6, 6)


def dt(day, hour, minute=0):
    return (BASE + timedelta(days=day)).replace(hour=hour, minute=minute).isoformat()


SESSIONS = [
    # ── Session 1: 2026-06-06 ─────────────────────────────────────────────────
    {
        "date":       "2026-06-06",
        "started_at": dt(0, 19, 0),
        "ended_at":   dt(0, 22, 30),
        "goal":       "See where my rank is after the break",
        "matches": [
            dict(map="Eichenwalde",  outcome="Loss", heroes=[("Reinhardt", 100)],
                 eheroes=["D.Va", "Winston", "Tracer", "Genji", "Ana", "Kiriko"],
                 my_comp="Brawl", enemy_comp="Dive",
                 rank=("Gold", 4, 40), e=8,  d=5, a=3, dmg=4800, heal=0,   mit=2100,
                 secs=860,  bans=["Sombra", "Tracer"],  stack=1, prac="N",    pnotes=""),
            dict(map="King's Row",   outcome="Win",  heroes=[("Reinhardt", 100)],
                 eheroes=["Reinhardt", "Cassidy", "Sojourn", "Ana", "Lucio"],
                 my_comp="Brawl", enemy_comp="Brawl",
                 rank=("Gold", 4, 52), e=12, d=3, a=6, dmg=6200, heal=0,   mit=2900,
                 secs=705,  bans=["Ana", "Sombra"],     stack=1, prac="Y",    pnotes="Good shield timing on Point B"),
            dict(map="Dorado",       outcome="Loss", heroes=[("Reinhardt", 100)],
                 eheroes=["Sigma", "Ashe", "Widowmaker", "Zenyatta", "Mercy"],
                 my_comp="Brawl", enemy_comp="Poke",
                 rank=("Gold", 4, 40), e=9,  d=6, a=2, dmg=4400, heal=0,   mit=2200,
                 secs=750,  bans=["Widowmaker", "Tracer"], stack=1, prac="N", pnotes=""),
            dict(map="Nepal",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["Reinhardt", "Reaper", "Cassidy", "Lucio", "Moira"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 4, 55), e=18, d=3, a=5, dmg=7800, heal=0,   mit=5200,
                 secs=555,  bans=["Sombra"],             stack=1, prac="Y",    pnotes="Matrix eating every Ult"),
            dict(map="Oasis",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["Orisa", "Ashe", "Widowmaker", "Ana", "Baptiste"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Gold", 4, 67), e=20, d=2, a=8, dmg=8500, heal=0,   mit=5800,
                 secs=525,  bans=["Ana", "Tracer"],      stack=1, prac="Y",    pnotes=""),
            dict(map="Busan",        outcome="Loss", heroes=[("D.Va", 100)],
                 eheroes=["D.Va", "Tracer", "Sombra", "Kiriko", "Zenyatta"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Gold", 4, 55), e=14, d=5, a=4, dmg=6100, heal=0,   mit=4100,
                 secs=630,  bans=["Sombra", "Kiriko"],   stack=1, prac="Sort of", pnotes=""),
            dict(map="Hollywood",    outcome="Loss", heroes=[("Reinhardt", 100)],
                 eheroes=["Winston", "Tracer", "Genji", "Ana", "Lucio"],
                 my_comp="Brawl", enemy_comp="Dive",
                 rank=("Gold", 4, 43), e=7,  d=7, a=2, dmg=3900, heal=0,   mit=1800,
                 secs=910,  bans=["Tracer", "Sombra"],   stack=1, prac="N",    pnotes=""),
            dict(map="Route 66",     outcome="Win",  heroes=[("Reinhardt", 100)],
                 eheroes=["Ramattra", "Cassidy", "Sojourn", "Moira", "Lucio"],
                 my_comp="Brawl", enemy_comp="Brawl",
                 rank=("Gold", 4, 55), e=11, d=4, a=5, dmg=5600, heal=0,   mit=2600,
                 secs=780,  bans=["Ana"],                stack=2, prac="Y",    pnotes="Stack game, great coordination"),
            dict(map="Samoa",        outcome="Loss", heroes=[("D.Va", 100)],
                 eheroes=["Sigma", "Ashe", "Pharah", "Mercy", "Zenyatta"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Gold", 4, 43), e=13, d=6, a=3, dmg=5800, heal=0,   mit=3900,
                 secs=735,  bans=["Pharah", "Sombra"],   stack=1, prac="N",    pnotes=""),
        ],
    },

    # ── Session 2: 2026-06-10 ─────────────────────────────────────────────────
    {
        "date":       "2026-06-10",
        "started_at": dt(4, 20, 0),
        "ended_at":   dt(4, 23, 45),
        "goal":       "Work on Winston dive timing",
        "matches": [
            dict(map="Ilios",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Reinhardt", "Cassidy", "Reaper", "Ana", "Lucio"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 4, 55), e=15, d=3, a=7, dmg=6800, heal=500, mit=1200,
                 secs=540,  bans=["Tracer", "Ana"],     stack=1, prac="Y",    pnotes="Good bubble timing"),
            dict(map="Nepal",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Orisa", "Widowmaker", "Ashe", "Zenyatta", "Baptiste"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Gold", 4, 65), e=17, d=2, a=6, dmg=7400, heal=600, mit=1100,
                 secs=510,  bans=["Widowmaker"],        stack=1, prac="Y",    pnotes=""),
            dict(map="Busan",        outcome="Loss", heroes=[("Winston", 100)],
                 eheroes=["D.Va", "Tracer", "Sombra", "Kiriko", "Ana"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Gold", 4, 53), e=11, d=7, a=4, dmg=5100, heal=400, mit=900,
                 secs=705,  bans=["Sombra", "Tracer"],  stack=1, prac="Sort of", pnotes="Bubble on cooldown too often"),
            dict(map="Watchpoint: Gibraltar", outcome="Win",
                 heroes=[("Winston", 70), ("D.Va", 30)],
                 eheroes=["Junker Queen", "Reaper", "Cassidy", "Moira", "Lucio"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 4, 65), e=16, d=3, a=8, dmg=7200, heal=900, mit=2100,
                 secs=855,  bans=["Ana", "Sombra"],     stack=2, prac="Y",    pnotes="Stack duo, great synergy"),
            dict(map="Oasis",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["D.Va", "Tracer", "Genji", "Ana", "Kiriko"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Gold", 3, 10), e=22, d=2, a=9, dmg=9400, heal=0,   mit=6200,
                 secs=495,  bans=["Tracer", "Kiriko"],  stack=1, prac="Y",    pnotes=""),
            dict(map="Lijiang Tower",outcome="Loss", heroes=[("Winston", 100)],
                 eheroes=["Reinhardt", "Reaper", "Cassidy", "Lucio", "Brigitte"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 3, 0),  e=12, d=7, a=3, dmg=5500, heal=700, mit=1000,
                 secs=630,  bans=["Sombra"],            stack=1, prac="N",    pnotes=""),
            dict(map="Eichenwalde",  outcome="Win",  heroes=[("Reinhardt", 100)],
                 eheroes=["Reinhardt", "Soldier: 76", "Cassidy", "Ana", "Moira"],
                 my_comp="Brawl", enemy_comp="Brawl",
                 rank=("Gold", 3, 12), e=13, d=3, a=6, dmg=6300, heal=0,   mit=3000,
                 secs=765,  bans=["Ana", "Tracer"],     stack=1, prac="Y",    pnotes=""),
            dict(map="Dorado",       outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Sigma", "Sojourn", "Ashe", "Zenyatta", "Mercy"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Gold", 3, 25), e=18, d=3, a=7, dmg=7800, heal=500, mit=1300,
                 secs=795,  bans=["Widowmaker", "Sombra"], stack=1, prac="Y", pnotes=""),
            dict(map="King's Row",   outcome="Loss", heroes=[("Winston", 100)],
                 eheroes=["D.Va", "Tracer", "Genji", "Kiriko", "Lucio"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Gold", 3, 14), e=10, d=8, a=3, dmg=4800, heal=600, mit=900,
                 secs=840,  bans=["Tracer", "Sombra"],  stack=1, prac="Sort of", pnotes=""),
            dict(map="Hollywood",    outcome="Loss", heroes=[("D.Va", 100)],
                 eheroes=["Reinhardt", "Reaper", "Cassidy", "Ana", "Brigitte"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 3, 3),  e=16, d=5, a=4, dmg=6900, heal=0,   mit=4400,
                 secs=870,  bans=["Ana", "Tracer"],     stack=1, prac="N",    pnotes=""),
        ],
    },

    # ── Session 3: 2026-06-14 ─────────────────────────────────────────────────
    {
        "date":       "2026-06-14",
        "started_at": dt(8, 18, 30),
        "ended_at":   dt(8, 22, 15),
        "goal":       "Push to Platinum",
        "matches": [
            dict(map="Nepal",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["Orisa", "Ashe", "Widowmaker", "Ana", "Zenyatta"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Gold", 3, 15), e=19, d=2, a=8, dmg=8200, heal=0,   mit=5600,
                 secs=525,  bans=["Widowmaker", "Ana"], stack=1, prac="Y",    pnotes=""),
            dict(map="Busan",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Reinhardt", "Cassidy", "Reaper", "Lucio", "Moira"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 3, 28), e=16, d=3, a=6, dmg=7100, heal=800, mit=1200,
                 secs=555,  bans=["Tracer", "Sombra"],  stack=1, prac="Y",    pnotes="Great dive on supports"),
            dict(map="Oasis",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["D.Va", "Genji", "Tracer", "Kiriko", "Lucio"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Gold", 2, 10), e=21, d=2, a=9, dmg=9100, heal=0,   mit=6400,
                 secs=480,  bans=["Tracer", "Kiriko"],  stack=1, prac="Y",    pnotes=""),
            dict(map="Circuit Royal",outcome="Loss", heroes=[("Reinhardt", 100)],
                 eheroes=["Sigma", "Ashe", "Widowmaker", "Zenyatta", "Baptiste"],
                 my_comp="Brawl", enemy_comp="Poke",
                 rank=("Gold", 2, 1),  e=8,  d=7, a=2, dmg=4100, heal=0,   mit=1900,
                 secs=900,  bans=["Widowmaker", "Pharah"], stack=1, prac="N", pnotes=""),
            dict(map="Havana",       outcome="Loss", heroes=[("Sigma", 100)],
                 eheroes=["Orisa", "Ashe", "Soldier: 76", "Ana", "Mercy"],
                 my_comp="Poke", enemy_comp="Poke",
                 rank=("Gold", 2, 0),  e=10, d=6, a=3, dmg=5200, heal=0,   mit=2100,
                 secs=825,  bans=["Pharah", "Widowmaker"], stack=1, prac="N", pnotes=""),
            dict(map="Midtown",      outcome="Win",  heroes=[("Reinhardt", 100)],
                 eheroes=["Ramattra", "Reaper", "Cassidy", "Moira", "Brigitte"],
                 my_comp="Brawl", enemy_comp="Brawl",
                 rank=("Gold", 2, 13), e=14, d=3, a=6, dmg=6600, heal=0,   mit=3100,
                 secs=720,  bans=["Sombra", "Ana"],     stack=2, prac="Y",    pnotes=""),
            dict(map="Blizzard World",outcome="Win", heroes=[("D.Va", 100)],
                 eheroes=["D.Va", "Tracer", "Genji", "Ana", "Kiriko"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Gold", 1, 10), e=20, d=2, a=8, dmg=8700, heal=0,   mit=5900,
                 secs=660,  bans=["Tracer", "Sombra"],  stack=1, prac="Y",    pnotes=""),
            dict(map="Route 66",     outcome="Win",  heroes=[("D.Va", 70), ("Winston", 30)],
                 eheroes=["Reinhardt", "Soldier: 76", "Reaper", "Lucio", "Ana"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 1, 24), e=17, d=3, a=7, dmg=7400, heal=300, mit=4800,
                 secs=810,  bans=["Ana", "Tracer"],     stack=2, prac="Y",    pnotes="Stack helping a lot"),
            dict(map="Ilios",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Sigma", "Ashe", "Sojourn", "Zenyatta", "Baptiste"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Gold", 1, 38), e=18, d=2, a=7, dmg=7900, heal=700, mit=1400,
                 secs=495,  bans=["Widowmaker", "Sombra"], stack=1, prac="Y", pnotes=""),
            dict(map="Samoa",        outcome="Loss", heroes=[("Reinhardt", 100)],
                 eheroes=["D.Va", "Tracer", "Genji", "Kiriko", "Lucio"],
                 my_comp="Brawl", enemy_comp="Dive",
                 rank=("Gold", 1, 27), e=9,  d=6, a=3, dmg=4700, heal=0,   mit=2000,
                 secs=720,  bans=["Tracer", "Kiriko"],  stack=1, prac="Sort of", pnotes=""),
            dict(map="Lijiang Tower",outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["Reinhardt", "Reaper", "Moira", "Lucio", "Brigitte"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Platinum", 5, 12), e=21, d=2, a=9, dmg=9000, heal=0, mit=6100,
                 secs=480,  bans=["Sombra", "Ana"],     stack=1, prac="Y",    pnotes="PLAT!"),
        ],
    },

    # ── Session 4: 2026-06-18 ─────────────────────────────────────────────────
    {
        "date":       "2026-06-18",
        "started_at": dt(12, 19, 30),
        "ended_at":   dt(12, 22, 0),
        "goal":       "Study enemy dive — they're running it better than me",
        "matches": [
            dict(map="Nepal",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["D.Va", "Tracer", "Genji", "Kiriko", "Ana"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Platinum", 5, 22), e=14, d=4, a=6, dmg=6400, heal=800, mit=1200,
                 secs=570,  bans=["Tracer", "Sombra"],  stack=1, prac="Y",    pnotes=""),
            dict(map="Oasis",        outcome="Loss", heroes=[("D.Va", 100)],
                 eheroes=["Orisa", "Sojourn", "Ashe", "Baptiste", "Kiriko"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Platinum", 5, 10), e=15, d=5, a=4, dmg=6800, heal=0,  mit=4400,
                 secs=615,  bans=["Sombra", "Tracer"],  stack=1, prac="N",    pnotes=""),
            dict(map="Busan",        outcome="Loss", heroes=[("D.Va", 100)],
                 eheroes=["D.Va", "Tracer", "Sombra", "Ana", "Kiriko"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Platinum", 5, 0),  e=13, d=6, a=3, dmg=5900, heal=0,  mit=3800,
                 secs=660,  bans=["Sombra", "Kiriko"],  stack=1, prac="N",    pnotes=""),
            dict(map="Eichenwalde",  outcome="Loss", heroes=[("Reinhardt", 100)],
                 eheroes=["Winston", "Genji", "Tracer", "Lucio", "Kiriko"],
                 my_comp="Brawl", enemy_comp="Dive",
                 rank=("Gold", 1, 88), e=7,  d=8, a=2, dmg=3800, heal=0,   mit=1700,
                 secs=945,  bans=["Tracer", "Sombra"],  stack=1, prac="N",    pnotes=""),
            dict(map="Samoa",        outcome="Loss", heroes=[("Winston", 100)],
                 eheroes=["Ramattra", "Reaper", "Cassidy", "Moira", "Brigitte"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Gold", 1, 77), e=11, d=7, a=3, dmg=5100, heal=600, mit=900,
                 secs=720,  bans=["Ana", "Sombra"],     stack=1, prac="N",    pnotes=""),
            dict(map="King's Row",   outcome="Win",  heroes=[("Reinhardt", 100)],
                 eheroes=["Reinhardt", "Cassidy", "Sojourn", "Ana", "Lucio"],
                 my_comp="Brawl", enemy_comp="Brawl",
                 rank=("Gold", 1, 88), e=12, d=4, a=5, dmg=5900, heal=0,   mit=2700,
                 secs=750,  bans=["Sombra", "Tracer"],  stack=1, prac="Y",    pnotes="Earthshatter at last"),
            dict(map="Dorado",       outcome="Loss", heroes=[("Winston", 100)],
                 eheroes=["Orisa", "Cassidy", "Ashe", "Ana", "Zenyatta"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Gold", 1, 76), e=10, d=7, a=3, dmg=4900, heal=500, mit=900,
                 secs=825,  bans=["Ana", "Widowmaker"], stack=1, prac="N",    pnotes=""),
            dict(map="Circuit Royal",outcome="Win",  heroes=[("Sigma", 100)],
                 eheroes=["Sigma", "Ashe", "Widowmaker", "Zenyatta", "Baptiste"],
                 my_comp="Poke", enemy_comp="Poke",
                 rank=("Gold", 1, 88), e=13, d=3, a=6, dmg=6700, heal=0,   mit=3300,
                 secs=870,  bans=["Widowmaker", "Pharah"], stack=1, prac="Y", pnotes=""),
        ],
    },

    # ── Session 5: 2026-06-22 ─────────────────────────────────────────────────
    {
        "date":       "2026-06-22",
        "started_at": dt(16, 20, 0),
        "ended_at":   dt(16, 23, 30),
        "goal":       "Better positioning — less face-tanking, more angles",
        "matches": [
            dict(map="Ilios",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["D.Va", "Tracer", "Sombra", "Kiriko", "Lucio"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Gold", 1, 97), e=20, d=2, a=9, dmg=8900, heal=0,   mit=6000,
                 secs=510,  bans=["Sombra", "Tracer"],  stack=1, prac="Y",    pnotes=""),
            dict(map="Nepal",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Orisa", "Sojourn", "Ashe", "Ana", "Zenyatta"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Platinum", 5, 10), e=17, d=3, a=7, dmg=7600, heal=900, mit=1300,
                 secs=525,  bans=["Widowmaker", "Ana"], stack=1, prac="Y",    pnotes=""),
            dict(map="Busan",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["Reinhardt", "Cassidy", "Reaper", "Moira", "Lucio"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Platinum", 5, 22), e=19, d=2, a=8, dmg=8400, heal=0,   mit=5700,
                 secs=540,  bans=["Sombra", "Tracer"],  stack=1, prac="Y",    pnotes="Harass backline pattern working"),
            dict(map="Oasis",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["Sigma", "Ashe", "Widowmaker", "Baptiste", "Mercy"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Platinum", 5, 35), e=22, d=1, a=10,dmg=9600, heal=0,   mit=6500,
                 secs=480,  bans=["Widowmaker", "Sombra"], stack=1, prac="Y",  pnotes="Best game of the session"),
            dict(map="Samoa",        outcome="Loss", heroes=[("Winston", 100)],
                 eheroes=["D.Va", "Tracer", "Genji", "Ana", "Kiriko"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Platinum", 5, 23), e=13, d=6, a=4, dmg=6000, heal=700, mit=1100,
                 secs=675,  bans=["Tracer", "Kiriko"],  stack=1, prac="Sort of", pnotes=""),
            dict(map="Watchpoint: Gibraltar", outcome="Win",
                 heroes=[("D.Va", 100)],
                 eheroes=["Ramattra", "Reaper", "Soldier: 76", "Moira", "Brigitte"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Platinum", 5, 37), e=18, d=2, a=7, dmg=7900, heal=0,   mit=5400,
                 secs=855,  bans=["Sombra", "Ana"],     stack=2, prac="Y",    pnotes=""),
            dict(map="Havana",       outcome="Loss", heroes=[("D.Va", 100)],
                 eheroes=["Sigma", "Widowmaker", "Ashe", "Baptiste", "Zenyatta"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Platinum", 5, 26), e=14, d=5, a=4, dmg=6300, heal=0,   mit=4200,
                 secs=795,  bans=["Widowmaker", "Pharah"], stack=1, prac="N",  pnotes=""),
            dict(map="Hollywood",    outcome="Win",  heroes=[("Reinhardt", 100)],
                 eheroes=["Reinhardt", "Reaper", "Cassidy", "Ana", "Moira"],
                 my_comp="Brawl", enemy_comp="Brawl",
                 rank=("Platinum", 5, 38), e=13, d=3, a=6, dmg=6400, heal=0,   mit=3000,
                 secs=720,  bans=["Ana", "Sombra"],     stack=1, prac="Y",    pnotes=""),
            dict(map="Lijiang Tower",outcome="Win",  heroes=[("D.Va", 70), ("Lucio", 30)],
                 eheroes=["D.Va", "Tracer", "Genji", "Kiriko", "Ana"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Platinum", 5, 52), e=16, d=2, a=11,dmg=6900, heal=4200,mit=3800,
                 secs=495,  bans=["Tracer", "Sombra"],  stack=2, prac="Y",    pnotes=""),
            dict(map="Blizzard World",outcome="Win", heroes=[("D.Va", 100)],
                 eheroes=["Reinhardt", "Soldier: 76", "Reaper", "Lucio", "Brigitte"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Platinum", 4, 8),  e=20, d=2, a=8, dmg=8700, heal=0,   mit=5900,
                 secs=645,  bans=["Ana", "Tracer"],     stack=1, prac="Y",    pnotes=""),
        ],
    },

    # ── Session 6: 2026-06-26 ─────────────────────────────────────────────────
    {
        "date":       "2026-06-26",
        "started_at": dt(20, 19, 0),
        "ended_at":   dt(20, 21, 45),
        "goal":       "Dive practice on control maps only",
        "matches": [
            dict(map="Ilios",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Reinhardt", "Cassidy", "Reaper", "Ana", "Lucio"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Platinum", 4, 18), e=16, d=3, a=7, dmg=7200, heal=900, mit=1400,
                 secs=510,  bans=["Tracer", "Sombra"],  stack=1, prac="Y",    pnotes=""),
            dict(map="Nepal",        outcome="Win",  heroes=[("D.Va", 100)],
                 eheroes=["Sigma", "Ashe", "Sojourn", "Ana", "Baptiste"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Platinum", 4, 28), e=21, d=1, a=9, dmg=9100, heal=0,   mit=6200,
                 secs=480,  bans=["Widowmaker", "Ana"], stack=1, prac="Y",    pnotes=""),
            dict(map="Busan",        outcome="Loss", heroes=[("Winston", 100)],
                 eheroes=["D.Va", "Sombra", "Tracer", "Kiriko", "Lucio"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Platinum", 4, 16), e=12, d=6, a=4, dmg=5700, heal=700, mit=1100,
                 secs=660,  bans=["Sombra", "Kiriko"],  stack=1, prac="Sort of", pnotes=""),
            dict(map="Oasis",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Reinhardt", "Reaper", "Cassidy", "Moira", "Lucio"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Platinum", 4, 28), e=18, d=2, a=8, dmg=7800, heal=800, mit=1500,
                 secs=525,  bans=["Ana", "Sombra"],     stack=1, prac="Y",    pnotes=""),
            dict(map="Ilios",        outcome="Loss", heroes=[("D.Va", 100)],
                 eheroes=["D.Va", "Tracer", "Genji", "Ana", "Kiriko"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Platinum", 4, 17), e=15, d=5, a=5, dmg=6700, heal=0,   mit=4500,
                 secs=600,  bans=["Tracer", "Kiriko"],  stack=1, prac="N",    pnotes=""),
            dict(map="Nepal",        outcome="Win",  heroes=[("D.Va", 70), ("Winston", 30)],
                 eheroes=["Orisa", "Ashe", "Widowmaker", "Zenyatta", "Mercy"],
                 my_comp="Dive", enemy_comp="Poke",
                 rank=("Platinum", 4, 30), e=19, d=2, a=8, dmg=8300, heal=200, mit=5200,
                 secs=510,  bans=["Widowmaker", "Sombra"], stack=1, prac="Y", pnotes=""),
            dict(map="Busan",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["Ramattra", "Reaper", "Soldier: 76", "Moira", "Brigitte"],
                 my_comp="Dive", enemy_comp="Brawl",
                 rank=("Platinum", 4, 42), e=17, d=2, a=7, dmg=7500, heal=1000,mit=1300,
                 secs=540,  bans=["Sombra", "Ana"],     stack=1, prac="Y",    pnotes=""),
            dict(map="Oasis",        outcome="Win",  heroes=[("Winston", 100)],
                 eheroes=["D.Va", "Tracer", "Sombra", "Kiriko", "Ana"],
                 my_comp="Dive", enemy_comp="Dive",
                 rank=("Platinum", 4, 54), e=20, d=2, a=9, dmg=8600, heal=1100,mit=1600,
                 secs=480,  bans=["Tracer", "Sombra"],  stack=1, prac="Y",    pnotes="3W streak to close!"),
        ],
    },
]


# ── Insert ─────────────────────────────────────────────────────────────────────

def seed():
    if not DB_PATH.exists():
        print("ERROR: database not found. Run the app once first (python -m uvicorn main:app)")
        sys.exit(1)

    with get_conn() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        if existing > 0 and "--clear" not in sys.argv:
            print(f"Found {existing} existing session(s). Pass --clear to wipe and re-seed.")
            print("Aborting — no changes made.")
            sys.exit(0)

        if "--clear" in sys.argv:
            print("Clearing existing data...")
            conn.execute("DELETE FROM match_participants")
            conn.execute("DELETE FROM matches")
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM career_baseline")
            conn.execute("DELETE FROM player_rank")
            print("Done.")

        total_matches = 0
        for sess in SESSIONS:
            cur = conn.execute(
                "INSERT INTO sessions (date, started_at, ended_at, goal, focus_mode, name, notes) "
                "VALUES (?,?,?,?,0,'','')",
                (sess["date"], sess["started_at"], sess["ended_at"], sess["goal"])
            )
            session_id = cur.lastrowid

            for i, m in enumerate(sess["matches"]):
                # Stagger match timestamps through the session
                total_secs = (
                    datetime.fromisoformat(sess["ended_at"]) -
                    datetime.fromisoformat(sess["started_at"])
                ).total_seconds()
                interval = total_secs / (len(sess["matches"]) + 1)
                played_at = (
                    datetime.fromisoformat(sess["started_at"]) +
                    timedelta(seconds=interval * (i + 1))
                ).isoformat()

                tier, div, pct = m["rank"]
                rs = rank_score(tier, div, pct)

                conn.execute(
                    """INSERT INTO matches
                       (played_at, map, outcome, my_heroes, enemy_heroes,
                        my_comp, enemy_comp,
                        rank_tier, rank_division, rank_pct, rank_score,
                        elims, deaths, assists, damage, healing, mitigation,
                        game_length_s, session_id, notes, bans,
                        stack_size, practiced, practice_notes, data_source)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        played_at, m["map"], m["outcome"],
                        jheroes(m["heroes"]), jenemies(m["eheroes"]),
                        m["my_comp"], m["enemy_comp"],
                        tier, div, float(pct), rs,
                        m["e"], m["d"], m["a"],
                        m["dmg"], m["heal"], m["mit"],
                        m["secs"], session_id, "",
                        jb(m["bans"]),
                        m["stack"], m.get("prac"), m.get("pnotes", ""),
                        "mock",
                    )
                )
                total_matches += 1

        # Seed player_rank (current rank = last match rank)
        conn.execute("DELETE FROM player_rank")
        conn.execute(
            "INSERT INTO player_rank (role, rank_tier, rank_division) VALUES (?,?,?)",
            ("Tank", "Platinum", 4)
        )

        # Seed a couple baseline heroes for the dashboard
        conn.execute("DELETE FROM career_baseline")
        for hero, pct_play, wr, games in [
            ("D.Va",       32.0, 0.54, 210),
            ("Reinhardt",  28.0, 0.51, 180),
            ("Winston",    20.0, 0.49, 130),
            ("Sigma",       8.0, 0.48,  52),
            ("Roadhog",     5.0, 0.45,  32),
            ("Orisa",       7.0, 0.46,  44),
        ]:
            conn.execute(
                "INSERT INTO career_baseline (hero, playtime_pct, win_rate, games_played, fetched_at) "
                "VALUES (?,?,?,?,?)",
                (hero, pct_play, wr, games, datetime.utcnow().isoformat())
            )

    wins   = sum(1 for s in SESSIONS for m in s["matches"] if m["outcome"] == "Win")
    losses = sum(1 for s in SESSIONS for m in s["matches"] if m["outcome"] == "Loss")
    print(f"Seeded {len(SESSIONS)} sessions, {total_matches} matches ({wins}W {losses}L, {wins/total_matches*100:.1f}% WR)")
    print("Rank arc: Gold 4 -> Platinum 4 with a slump in session 4")
    print("Run the app and check all pages!")


if __name__ == "__main__":
    seed()
