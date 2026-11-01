"""
Orchestrates OCR + icon matching into a single parsed match dict.
Handles both OW2 screenshot tabs (1920×1080):
  - TEAM tab:    player stats, identifies your row by first-row fallback
  - SUMMARY tab: map, outcome, game length, date, game mode
"""
from PIL import Image
from db import get_conn


def known_maps() -> list[str]:
    with get_conn() as conn:
        return [r["name"] for r in conn.execute("SELECT name FROM maps")]


def parse_screenshot(path: str, username: str = "DROWZY") -> dict:
    from parser.ocr import detect_tab, extract_all_rows, find_my_row, extract_tracked_players, extract_summary

    with get_conn() as conn:
        tracked_players = [r["name"] for r in conn.execute("SELECT name FROM tracked_players").fetchall()]

    warnings = []
    img = Image.open(path)

    tab = detect_tab(img)

    if tab == "SUMMARY":
        return _parse_summary_tab(img, warnings)
    if tab == "TEAM":
        return _parse_team_tab(path, img, username, tracked_players, warnings)
    if tab == "PERSONAL":
        return _parse_personal_tab(img, warnings)

    warnings.append("Could not auto-detect screenshot type; attempting TEAM tab parse")
    return _parse_team_tab(path, img, username, tracked_players, warnings)


def _parse_summary_tab(img: Image.Image, warnings: list) -> dict:
    from parser.ocr import extract_summary
    data = extract_summary(img, known_maps())
    warnings.extend(data.pop("warnings", []))
    return {
        "tab_type":      "SUMMARY",
        "map":           data.get("map", ""),
        "outcome":       data.get("outcome", ""),
        "game_length_s": data.get("game_length_s"),
        "played_at":     data.get("played_at"),
        "game_mode":     data.get("game_mode", ""),
        "my_heroes":     [],
        "my_team_heroes": [],
        "enemy_heroes":  [],
        "elims":         data.get("elims"),
        "deaths":        data.get("deaths"),
        "assists":       data.get("assists"),
        "damage":        None,
        "healing":       None,
        "mitigation":    None,
        "played_pcts":   data.get("played_pcts", []),
        "teammates":     [],
        "stack_size":    1,
        "confidence":    0.0,
        "warnings":      warnings,
    }


def _parse_personal_tab(img: Image.Image, warnings: list) -> dict:
    from parser.ocr import extract_personal
    data = extract_personal(img)
    warnings.extend(data.pop("warnings", []))
    return {
        "tab_type":      "PERSONAL",
        "map":           "",
        "outcome":       "",
        "game_length_s": None,
        "played_at":     None,
        "game_mode":     "",
        "my_heroes":     [{"hero": data.get("hero", ""), "pct": 100}] if data.get("hero") else [],
        "my_team_heroes": [],
        "enemy_heroes":  [],
        "elims":         None,
        "deaths":        None,
        "assists":       None,
        "damage":        None,
        "healing":       None,
        "mitigation":    None,
        "teammates":     [],
        "stack_size":    1,
        "confidence":    0.0,
        "warnings":      warnings,
    }


def _parse_team_tab(path: str, img: Image.Image, username: str, tracked_players: list, warnings: list) -> dict:
    from parser.ocr import extract_all_rows, find_my_row, extract_tracked_players
    from parser.icons import extract_heroes, _CSV_NAME_ALIASES

    # Name OCR is only useful for matching tracked players (own name + CJK names
    # otherwise read as ""). Skip it entirely when there's nobody to match.
    all_rows   = extract_all_rows(img, read_names=bool(tracked_players))
    my_rows    = all_rows["my_team"]
    enemy_rows = all_rows["enemy_team"]

    my_row = find_my_row(my_rows, username)
    if not my_row:
        warnings.append("Could not locate any rows — stats left blank")

    found_teammates = extract_tracked_players(my_rows, tracked_players)
    stack_size = 1 + len(found_teammates)

    icon_result  = extract_heroes(path)
    hero_warning = icon_result.get("warning", "")
    if hero_warning:
        warnings.append(hero_warning)

    raw_my    = icon_result.get("my_heroes",    [])
    raw_enemy = icon_result.get("enemy_heroes", [])
    # The scoreboard gives us the FULL team comp (all 5 slots), but it can't tell
    # which slot is the user: names OCR as blank (stylised nameplate + CJK names),
    # so we cannot attribute a specific slot to "me". The 5 my-team heroes are the
    # team comp (→ my_team_heroes, used only to derive my_comp); the hero(es) the
    # user actually played are picked explicitly in the review step. This avoids
    # crediting teammates' heroes to the user's own hero win-rates.
    # Templates use code names ("Soldier 76"); everything downstream uses CSV names.
    to_csv_name = {code: csv_name for csv_name, code in _CSV_NAME_ALIASES.items()}
    my_team_heroes = [
        {"hero": to_csv_name.get(h["hero"], h["hero"]), "confidence": h.get("confidence", 1.0),
         "role": h.get("role", ""), "row": i}
        for i, h in enumerate(raw_my)
    ]
    enemy_heroes = [
        {"hero": to_csv_name.get(h["hero"], h["hero"]), "confidence": h.get("confidence", 1.0),
         "role": h.get("role", ""), "row": i}
        for i, h in enumerate(raw_enemy)
    ]
    confidence   = icon_result.get("confidence", 0.0)

    warnings.append("Map and outcome not on TEAM tab — confirm after parsing SUMMARY tab screenshot")
    warnings.append("Select the hero(es) YOU played — the detected team comp is shown for reference only")

    return {
        "tab_type":      "TEAM",
        "map":           "",
        "outcome":       "",
        "game_length_s": None,
        "played_at":     None,
        "game_mode":     "",
        "my_heroes":     [],
        "my_team_heroes": my_team_heroes,
        "enemy_heroes":  enemy_heroes,
        "elims":         my_row.get("elims")      if my_row else None,
        "deaths":        my_row.get("deaths")     if my_row else None,
        "assists":       my_row.get("assists")     if my_row else None,
        "damage":        my_row.get("damage")     if my_row else None,
        "healing":       my_row.get("healing")    if my_row else None,
        "mitigation":    my_row.get("mitigation") if my_row else None,
        "team_rows":     {"my_team": my_rows, "enemy_team": enemy_rows},
        "teammates":     found_teammates,
        "stack_size":    stack_size,
        "confidence":    round(confidence, 2),
        "warnings":      warnings,
    }


# ── Merging a SUMMARY + TEAM screenshot of one game ───────────────────────────

_EAD = ("elims", "assists", "deaths")
_MIN_MATCHING_STATS = 2  # of E/A/D; the TEAM grid misreads some, so 3/3 is too strict


def match_summary_row(summary: dict, team: dict) -> tuple[int, int | None]:
    """Compare SUMMARY's own E/A/D with each my-team row of a TEAM parse.
    Returns (best score, row index). The row is None if two rows tie."""
    best, best_rows = 0, []
    rows = (team.get("team_rows") or {}).get("my_team", [])
    for i, row in enumerate(rows):
        score = sum(summary.get(k) is not None and summary.get(k) == row.get(k) for k in _EAD)
        if score > best:
            best, best_rows = score, [i]
        elif score == best:
            best_rows.append(i)
    return best, (best_rows[0] if len(best_rows) == 1 else None)


def is_same_game(summary: dict, team: dict) -> bool:
    return match_summary_row(summary, team)[0] >= _MIN_MATCHING_STATS


def merge_summary_team(summary: dict, team: dict) -> dict:
    """Combine both parses: SUMMARY supplies map/result/time/length and the player's
    E/A/D; TEAM supplies the comps and the player's DMG/H/MIT."""
    _, row_idx = match_summary_row(summary, team)
    merged = dict(team)
    for k in ("map", "outcome", "game_length_s", "played_at", "game_mode", "played_pcts"):
        merged[k] = summary.get(k)
    merged["merged"] = True
    merged["my_row"] = row_idx

    warnings = list(summary.get("warnings", []))
    warnings += [w for w in team.get("warnings", [])
                 if not w.startswith(("Map and outcome", "Select the hero"))]

    row = {}
    if row_idx is None:
        warnings.append("Couldn't tell which scoreboard row is yours — check DMG/H/MIT")
        for k in ("damage", "healing", "mitigation"):
            merged[k] = None
    else:
        row = team["team_rows"]["my_team"][row_idx]
        for k in ("damage", "healing", "mitigation"):
            merged[k] = row.get(k)
    for k in _EAD:
        merged[k] = summary[k] if summary.get(k) is not None else row.get(k)

    pcts = merged.get("played_pcts") or []
    if pcts != [100]:
        played = " + ".join(f"{p}%" for p in pcts) or "unknown split"
        warnings.append(f"Hero split on Summary: {played} — select the heroes you played")
    merged["warnings"] = warnings
    return merged


# ── One row per player, for match_participants ────────────────────────────────

_ROW_STATS = ("elims", "assists", "deaths", "damage", "healing", "mitigation")


def build_participants(parsed: dict, team_slots: dict = None, me_stats: dict = None) -> list[dict]:
    """The scoreboard as 10 rows. Slots keep their row number, so an unidentified hero
    leaves that row's hero list empty instead of shifting the rows below it.
    team_slots holds the heroes confirmed in the Queue; without it, the detected ones.
    me_stats are the confirmed values for the player's own row, which beat raw OCR."""
    rows = parsed.get("team_rows") or {}
    slots = team_slots or {}
    sides = (("ally", "my", rows.get("my_team") or [], parsed.get("my_team_heroes") or []),
             ("enemy", "enemy", rows.get("enemy_team") or [], parsed.get("enemy_heroes") or []))
    participants = []
    for team, slot_key, team_rows, detected in sides:
        names = slots.get(slot_key)
        if names is None:
            names = [h.get("hero") if isinstance(h, dict) else h for h in detected]
        for i in range(max(len(team_rows), len(names))):
            row = team_rows[i] if i < len(team_rows) else {}
            hero = names[i] if i < len(names) else None
            is_me = team == "ally" and parsed.get("my_row") == i
            stats = {k: row.get(k) for k in _ROW_STATS}
            if is_me and me_stats:
                stats.update({k: v for k, v in me_stats.items() if v is not None})
            participants.append({
                "player_name": row.get("name") or "",
                "team": team,
                "heroes": [{"hero": hero, "pct": 100}] if hero and not hero.startswith("Unknown") else [],
                "stats": stats,
                "slot": i,
                "is_me": is_me,
            })
    return participants
