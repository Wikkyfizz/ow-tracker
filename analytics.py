import json
from collections import defaultdict
from db import get_conn, rows_to_list

MIN_WEIGHTED_GAMES = 2.0


def _outcome_val(outcome: str) -> float:
    return {"Win": 1.0, "Loss": 0.0, "Draw": 0.5}.get(outcome, 0.0)


def _load_matches(conn, filters: dict = None) -> list:
    q = "SELECT * FROM matches"
    params = []
    if filters:
        clauses = []
        if filters.get("map"):
            clauses.append("map = ?"); params.append(filters["map"])
        if filters.get("outcome"):
            clauses.append("outcome = ?"); params.append(filters["outcome"])
        if filters.get("rank_tier"):
            clauses.append("rank_tier = ?"); params.append(filters["rank_tier"])
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
    return [dict(r) for r in conn.execute(q, params).fetchall()]


def hero_winrates(filters: dict = None) -> list:
    with get_conn() as conn:
        matches = _load_matches(conn, filters)
    stats = defaultdict(lambda: {"weighted_wins": 0.0, "weighted_games": 0.0})
    for m in matches:
        ov = _outcome_val(m["outcome"])
        for entry in json.loads(m["my_heroes"] or "[]"):
            w = entry["pct"] / 100.0
            stats[entry["hero"]]["weighted_wins"] += w * ov
            stats[entry["hero"]]["weighted_games"] += w
    result = []
    for hero, s in stats.items():
        if s["weighted_games"] < MIN_WEIGHTED_GAMES:
            continue
        result.append({
            "hero": hero,
            "win_rate": round(s["weighted_wins"] / s["weighted_games"], 3),
            "weighted_games": round(s["weighted_games"], 1),
        })
    return sorted(result, key=lambda x: -x["win_rate"])


def map_winrates(filters: dict = None) -> list:
    with get_conn() as conn:
        matches = _load_matches(conn, filters)
        map_info = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM maps").fetchall()}
    stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for m in matches:
        stats[m["map"]]["total"] += 1
        if m["outcome"] == "Win":
            stats[m["map"]]["wins"] += 1
    result = []
    for map_name, s in stats.items():
        if s["total"] < 3:
            continue
        info = map_info.get(map_name, {})
        result.append({
            "map": map_name,
            "win_rate": round(s["wins"] / s["total"], 3),
            "games": s["total"],
            "wins": s["wins"],
            "game_mode": info.get("game_mode", ""),
            "comp_affinity": info.get("comp_affinity", ""),
        })
    return sorted(result, key=lambda x: -x["win_rate"])


def comp_matchups() -> list:
    with get_conn() as conn:
        matches = _load_matches(conn)
    stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for m in matches:
        if not m["my_comp"] or not m["enemy_comp"]:
            continue
        key = (m["my_comp"], m["enemy_comp"])
        stats[key]["total"] += 1
        if m["outcome"] == "Win":
            stats[key]["wins"] += 1
    result = []
    for (my_comp, enemy_comp), s in stats.items():
        if s["total"] < 3:
            continue
        result.append({
            "my_comp": my_comp,
            "enemy_comp": enemy_comp,
            "win_rate": round(s["wins"] / s["total"], 3),
            "games": s["total"],
        })
    return sorted(result, key=lambda x: (-x["games"], -x["win_rate"]))


def teammate_winrates() -> list:
    with get_conn() as conn:
        matches = _load_matches(conn)
        players = {r["name"]: r["alias"] for r in conn.execute("SELECT name, alias FROM tracked_players").fetchall()}
    stats = defaultdict(lambda: {"wins": 0, "total": 0})
    solo = {"wins": 0, "total": 0}
    for m in matches:
        tm = json.loads(m["teammates"] or "[]")
        if not tm:
            solo["total"] += 1
            if m["outcome"] == "Win":
                solo["wins"] += 1
        else:
            for name in tm:
                stats[name]["total"] += 1
                if m["outcome"] == "Win":
                    stats[name]["wins"] += 1
    result = [{"player": "Solo", "alias": "", "win_rate": round(solo["wins"] / solo["total"], 3) if solo["total"] else 0, "games": solo["total"]}]
    for name, s in stats.items():
        result.append({
            "player": name,
            "alias": players.get(name, ""),
            "win_rate": round(s["wins"] / s["total"], 3) if s["total"] else 0,
            "games": s["total"],
        })
    return sorted(result, key=lambda x: -x["games"])


def stack_winrates() -> list:
    with get_conn() as conn:
        matches = _load_matches(conn)
    stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for m in matches:
        sz = m["stack_size"] or 1
        stats[sz]["total"] += 1
        if m["outcome"] == "Win":
            stats[sz]["wins"] += 1
    return [
        {
            "stack_size": sz,
            "label": {1: "Solo", 2: "Duo", 3: "Trio", 4: "4-Stack", 5: "5-Stack"}.get(sz, str(sz)),
            "win_rate": round(s["wins"] / s["total"], 3) if s["total"] else 0,
            "games": s["total"],
        }
        for sz, s in sorted(stats.items())
    ]


def ban_stats() -> list:
    with get_conn() as conn:
        matches = _load_matches(conn)
    ban_count = defaultdict(int)
    ban_wins = defaultdict(int)
    total = len(matches)
    for m in matches:
        bans = json.loads(m["bans"] or "[]")
        for hero in bans:
            ban_count[hero] += 1
            if m["outcome"] == "Win":
                ban_wins[hero] += 1
    return sorted(
        [
            {
                "hero": h,
                "ban_count": ban_count[h],
                "ban_rate": round(ban_count[h] / total, 3) if total else 0,
                "win_rate_when_banned": round(ban_wins[h] / ban_count[h], 3) if ban_count[h] else 0,
            }
            for h in ban_count
        ],
        key=lambda x: -x["ban_count"],
    )


def sr_timeline() -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, played_at, map, outcome, rank_tier, rank_division, rank_pct, rank_score "
            "FROM matches WHERE rank_score IS NOT NULL ORDER BY played_at ASC"
        ).fetchall()
    return rows_to_list(rows)


def hero_map_winrates() -> list:
    with get_conn() as conn:
        matches = _load_matches(conn)
        map_info = {r["name"]: r["comp_affinity"] for r in conn.execute("SELECT name, comp_affinity FROM maps").fetchall()}
    stats = defaultdict(lambda: {"weighted_wins": 0.0, "weighted_games": 0.0})
    for m in matches:
        ov = _outcome_val(m["outcome"])
        for entry in json.loads(m["my_heroes"] or "[]"):
            w = entry["pct"] / 100.0
            key = (entry["hero"], m["map"])
            stats[key]["weighted_wins"] += w * ov
            stats[key]["weighted_games"] += w
    result = []
    for (hero, map_name), s in stats.items():
        if s["weighted_games"] < MIN_WEIGHTED_GAMES:
            continue
        result.append({
            "hero": hero,
            "map": map_name,
            "comp_affinity": map_info.get(map_name, ""),
            "win_rate": round(s["weighted_wins"] / s["weighted_games"], 3),
            "weighted_games": round(s["weighted_games"], 1),
        })
    return sorted(result, key=lambda x: (-x["weighted_games"], -x["win_rate"]))


def vs_enemy_hero() -> list:
    with get_conn() as conn:
        matches = _load_matches(conn)
    stats = defaultdict(lambda: {"wins": 0, "total": 0})
    for m in matches:
        ov = m["outcome"]
        for entry in json.loads(m["enemy_heroes"] or "[]"):
            stats[entry["hero"]]["total"] += 1
            if ov == "Win":
                stats[entry["hero"]]["wins"] += 1
    return sorted(
        [
            {
                "enemy_hero": h,
                "win_rate": round(s["wins"] / s["total"], 3) if s["total"] else 0,
                "games": s["total"],
            }
            for h, s in stats.items()
            if s["total"] >= 3
        ],
        key=lambda x: -x["win_rate"],
    )


def _role_matchups(matches, role_of, archetype_of, role, grain="hero"):
    """Matchup win-rate for a single role: my hero of `role` vs the enemy's hero
    of the same role, weighted by both sides' playtime (pct). `grain` selects the
    enemy axis: "hero" (vs specific enemy hero) or "archetype" (vs enemy hero's
    archetype, multi-archetype heroes split equally — same logic as derive_comp).
    Tank players care most about this matchup; other roles can ignore it.
    """
    stats = defaultdict(lambda: {"weighted_wins": 0.0, "weighted_games": 0.0})
    for m in matches:
        ov = _outcome_val(m["outcome"])
        mine = [(e["hero"], e["pct"] / 100.0) for e in json.loads(m["my_heroes"] or "[]")
                if role_of.get(e["hero"]) == role]
        enemy = [(e["hero"], e["pct"] / 100.0) for e in json.loads(m["enemy_heroes"] or "[]")
                 if role_of.get(e["hero"]) == role]
        for my_hero, mw in mine:
            for enemy_hero, ew in enemy:
                if grain == "archetype":
                    labels = [a for a in archetype_of.get(enemy_hero, "Flex").split("|")]
                    buckets = [(lbl, ew / len(labels)) for lbl in labels]
                else:
                    buckets = [(enemy_hero, ew)]
                for key, kw in buckets:
                    w = mw * kw
                    stats[(my_hero, key)]["weighted_wins"] += w * ov
                    stats[(my_hero, key)]["weighted_games"] += w
    result = []
    for (my_hero, vs), s in stats.items():
        if s["weighted_games"] < MIN_WEIGHTED_GAMES:
            continue
        result.append({
            "my_hero": my_hero,
            "vs": vs,
            "win_rate": round(s["weighted_wins"] / s["weighted_games"], 3),
            "weighted_games": round(s["weighted_games"], 1),
        })
    return sorted(result, key=lambda x: (x["my_hero"], -x["weighted_games"]))


def role_matchups(role: str = "Tank", grain: str = "hero") -> list:
    with get_conn() as conn:
        matches = _load_matches(conn)
        role_of = {r["name"]: r["role"] for r in conn.execute("SELECT name, role FROM heroes")}
        archetype_of = {r["name"]: r["primary_archetype"]
                        for r in conn.execute("SELECT name, primary_archetype FROM heroes")}
    return _role_matchups(matches, role_of, archetype_of, role, grain)


def dashboard_summary() -> dict:
    with get_conn() as conn:
        all_matches = _load_matches(conn)
        latest_rank = conn.execute("SELECT role, rank_tier, rank_division FROM player_rank ORDER BY role").fetchall()

    total = len(all_matches)
    if total == 0:
        return {"total": 0, "win_rate": 0, "win_rate_last20": 0, "streak": 0, "streak_type": ""}

    wins = sum(1 for m in all_matches if m["outcome"] == "Win")
    last20 = all_matches[-20:]
    wins20 = sum(1 for m in last20 if m["outcome"] == "Win")

    streak = 0
    streak_type = ""
    for m in reversed(all_matches):
        if streak == 0:
            streak_type = m["outcome"]
        if m["outcome"] == streak_type:
            streak += 1
        else:
            break

    wr = hero_winrates()
    best_hero = wr[0]["hero"] if wr else ""
    mwr = map_winrates()
    best_map = mwr[0]["map"] if mwr else ""

    return {
        "total": total,
        "wins": wins,
        "win_rate": round(wins / total, 3),
        "win_rate_last20": round(wins20 / len(last20), 3) if last20 else 0,
        "streak": streak,
        "streak_type": streak_type,
        "best_hero": best_hero,
        "best_map": best_map,
        "ranks": [dict(r) for r in latest_rank] if latest_rank else [],
    }
