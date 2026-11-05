"""Explore: ad-hoc questions over every player on the scoreboard (match_participants).

Each question takes the list from load_games(), so the logic can be tested without
a database. Only games with a saved scoreboard are included.
"""
import json
from collections import defaultdict

from db import get_conn

STATS = ("elims", "assists", "deaths", "damage", "healing", "mitigation")
ALL_STATS = STATS + ("kd",)
LOWER_IS_BETTER = {"deaths"}
# "Better on most stats" compares these. Assists is often unread and K/D repeats E and D.
OVERALL_STATS = ("elims", "deaths", "damage", "healing", "mitigation")
SLOT_ROLE = {0: "Tank", 1: "Damage", 2: "Damage", 3: "Support", 4: "Support"}
# The scoreboard OCR sometimes runs the assists digits into a neighbouring column
# (1308, 8136). No real game reaches these, so they count as unread.
PLAUSIBLE_MAX = {"assists": 99}


def _main_hero(heroes):
    return max(heroes, key=lambda h: h.get("pct") or 0)["hero"] if heroes else None


def load_games(hero=None, map_name=None):
    with get_conn() as conn:
        role_of = {r["name"]: r["role"] for r in conn.execute("SELECT name, role FROM heroes")}
        matches = conn.execute(
            "SELECT id, played_at, map, outcome, game_length_s FROM matches ORDER BY played_at, id"
        ).fetchall()
        parts = conn.execute(
            "SELECT match_id, team, slot, heroes, stats, is_me FROM match_participants"
        ).fetchall()

    players = defaultdict(list)
    for p in parts:
        main = _main_hero(json.loads(p["heroes"] or "[]"))
        players[p["match_id"]].append({
            "team": p["team"],
            "hero": main,
            # A leaver shifts the rows, so the hero's role beats the row position.
            "role": role_of.get(main) or SLOT_ROLE.get(p["slot"]),
            "is_me": bool(p["is_me"]),
            "stats": json.loads(p["stats"] or "{}"),
        })

    games = []
    for m in matches:
        ps = players.get(m["id"])
        if not ps:
            continue
        me = next((p for p in ps if p["is_me"]), None)
        if hero and (not me or me["hero"] != hero):
            continue
        if map_name and m["map"] != map_name:
            continue
        games.append({
            "id": m["id"], "played_at": m["played_at"], "map": m["map"], "outcome": m["outcome"],
            "minutes": (m["game_length_s"] or 0) / 60 or None,
            "me": me, "players": ps,
        })
    return games


def value(player, stat, minutes=None, per10=False):
    """A player's stat for one game; None if it wasn't read. K/D with 0 deaths is the elims."""
    s = player["stats"]
    if stat == "kd":
        e, d = s.get("elims"), s.get("deaths")
        if e is None or d is None:
            return None
        return e / d if d else float(e)
    v = s.get(stat)
    if v is not None and v > PLAUSIBLE_MAX.get(stat, float("inf")):
        return None
    if v is None or not per10:
        return v
    return v * 10 / minutes if minutes else None


def _wr(games):
    return round(sum(g["outcome"] == "Win" for g in games) / len(games), 3) if games else None


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _kd_total(players):
    """Total elims over total deaths, so one 0-death game doesn't swamp the average."""
    pairs = [(p["stats"].get("elims"), p["stats"].get("deaths")) for p in players]
    pairs = [(e, d) for e, d in pairs if e is not None and d is not None]
    deaths = sum(d for _, d in pairs)
    return round(sum(e for e, _ in pairs) / deaths, 2) if deaths else None


def _passes(v, op, threshold):
    return v is not None and (v < threshold if op == "lt" else v > threshold)


def condition(games, role, stat, op, threshold, per10=False):
    """How many games had a player of `role` (not you) on each team meeting the condition."""
    out = {}
    for team in ("ally", "enemy"):
        hits, misses, unknown = [], [], 0
        for g in games:
            cands = [p for p in g["players"]
                     if p["team"] == team and not p["is_me"] and (role == "any" or p["role"] == role)]
            vals = [value(p, stat, g["minutes"], per10) for p in cands]
            if any(_passes(v, op, threshold) for v in vals):
                hits.append(g)
            elif not cands or all(v is None for v in vals):
                unknown += 1
            else:
                misses.append(g)
        out[team] = {
            "hits": len(hits), "checked": len(hits) + len(misses), "unknown": unknown,
            "wr_when": _wr(hits), "wr_otherwise": _wr(misses),
        }
    return {"games": len(games), **out}


def versus(games, team, role, per10=False):
    """You against the other player(s) of `role` on `team`, stat by stat.
    With two players in the role, you're compared with their average."""
    rows = {s: {"better": [], "worse": [], "ties": 0, "mine": [], "theirs": []} for s in ALL_STATS}
    overall = {"better": [], "worse": [], "ties": 0}
    my_rows, their_rows = [], []
    compared = 0
    for g in games:
        me = g["me"]
        targets = [p for p in g["players"] if p["team"] == team and not p["is_me"] and p["role"] == role]
        if not me or not targets:
            continue
        compared += 1
        my_rows.append(me); their_rows.extend(targets)
        score = 0
        for s in ALL_STATS:
            mine = value(me, s, g["minutes"], per10)
            theirs = _avg([value(p, s, g["minutes"], per10) for p in targets])
            if mine is None or theirs is None:
                continue
            r = rows[s]
            r["mine"].append(mine); r["theirs"].append(theirs)
            if mine == theirs:
                r["ties"] += 1
                continue
            better = mine < theirs if s in LOWER_IS_BETTER else mine > theirs
            (r["better"] if better else r["worse"]).append(g)
            if s in OVERALL_STATS:
                score += 1 if better else -1
        if score > 0: overall["better"].append(g)
        elif score < 0: overall["worse"].append(g)
        else: overall["ties"] += 1

    def summarize(r):
        n = len(r["better"]) + len(r["worse"]) + r["ties"]
        return {"n": n, "better": len(r["better"]), "worse": len(r["worse"]), "ties": r["ties"],
                "wr_better": _wr(r["better"]), "wr_worse": _wr(r["worse"])}

    def averages(s):
        if s == "kd":
            return {"my_avg": _kd_total(my_rows), "their_avg": _kd_total(their_rows)}
        return {"my_avg": _avg(rows[s]["mine"]), "their_avg": _avg(rows[s]["theirs"])}

    return {
        "games": len(games), "compared": compared,
        "stats": [{"stat": s, **summarize(rows[s]), **averages(s)} for s in ALL_STATS],
        "overall": summarize(overall),
    }


def by_hero(games, per10=False):
    """Your average stats on each hero you played."""
    groups = defaultdict(list)
    for g in games:
        if g["me"] and g["me"]["hero"]:
            groups[g["me"]["hero"]].append(g)
    result = []
    for hero, gs in groups.items():
        row = {"hero": hero, "games": len(gs), "win_rate": _wr(gs)}
        for s in STATS:
            row[s] = _avg([value(g["me"], s, g["minutes"], per10) for g in gs])
        row["kd"] = _kd_total([g["me"] for g in gs])
        result.append(row)
    return {"games": len(games), "heroes": sorted(result, key=lambda r: (-r["games"], r["hero"]))}
