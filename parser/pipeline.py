"""
Orchestrates OCR + icon matching into a single parsed match dict.
Handles both OW2 screenshot tabs (1920×1080):
  - TEAM tab:    player stats, identifies your row by first-row fallback
  - SUMMARY tab: map, outcome, game length, date, game mode
"""
from PIL import Image
from db import get_conn


_KNOWN_MAPS = [
    "Antarctic Peninsula", "Busan", "Ilios", "Lijiang Tower", "Nepal", "Oasis", "Samoa",
    "Circuit Royal", "Dorado", "Havana", "Junkertown", "Rialto", "Route 66",
    "Shambali Monastery", "Watchpoint: Gibraltar",
    "Blizzard World", "Eichenwalde", "Hollywood", "King's Row", "Midtown", "Numbani", "Paraiso",
    "Colosseo", "Esperanca", "New Junk City", "Suravasa",
    "New Queen Street", "Runasapi", "Throne of Anubis",
    "Hanaoka", "Neon Junction", "Overwatch Headquarters",
    "Ramattra Null Sector", "Timelocked Sanctum",
    "Aatlis",
]


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
    data = extract_summary(img, _KNOWN_MAPS)
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
    from parser.icons import extract_heroes

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
    my_team_heroes = [
        {"hero": h["hero"], "confidence": h.get("confidence", 1.0), "role": h.get("role", ""), "row": i}
        for i, h in enumerate(raw_my)
    ]
    enemy_heroes = [
        {"hero": h["hero"], "confidence": h.get("confidence", 1.0), "role": h.get("role", ""), "row": i}
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
