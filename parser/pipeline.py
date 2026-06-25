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

    all_rows = extract_all_rows(img)
    my_rows    = all_rows["my_team"]

    my_row = find_my_row(my_rows, username)
    if not my_row:
        warnings.append("Could not locate any rows — stats left blank")

    found_teammates = extract_tracked_players(my_rows, tracked_players)
    stack_size = 1 + len(found_teammates)

    icon_result = extract_heroes(path)
    hero_warning = icon_result.get("warning", "")
    no_icons = not icon_result.get("my_heroes") and not icon_result.get("enemy_heroes")

    if no_icons or hero_warning:
        if hero_warning:
            warnings.append(hero_warning)
        my_heroes    = []
        enemy_heroes = []
        confidence   = 0.0
    else:
        my_heroes    = [{"hero": h, "pct": 100} for h in icon_result.get("my_heroes", [])[:1]]
        enemy_heroes = [{"hero": h, "pct": 100} for h in icon_result.get("enemy_heroes", [])]
        confidence   = icon_result.get("confidence", 0.0)

    warnings.append("Map and outcome not on TEAM tab — confirm after parsing SUMMARY tab screenshot")

    return {
        "tab_type":      "TEAM",
        "map":           "",
        "outcome":       "",
        "game_length_s": None,
        "played_at":     None,
        "game_mode":     "",
        "my_heroes":     my_heroes,
        "enemy_heroes":  enemy_heroes,
        "elims":         my_row.get("elims")      if my_row else None,
        "deaths":        my_row.get("deaths")     if my_row else None,
        "assists":       my_row.get("assists")     if my_row else None,
        "damage":        my_row.get("damage")     if my_row else None,
        "healing":       my_row.get("healing")    if my_row else None,
        "mitigation":    my_row.get("mitigation") if my_row else None,
        "teammates":     found_teammates,
        "stack_size":    stack_size,
        "confidence":    round(confidence, 2),
        "warnings":      warnings,
    }
