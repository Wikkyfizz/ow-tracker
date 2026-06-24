"""
Orchestrates OCR + icon matching into a single parsed match dict.
"""
from PIL import Image
from pathlib import Path
from db import get_conn, rows_to_list
import json


def parse_screenshot(path: str, username: str = "DROWZY") -> dict:
    from parser.ocr import (
        extract_map_name, extract_outcome,
        extract_player_rows, find_my_row, extract_tracked_players,
    )
    from parser.icons import extract_heroes

    with get_conn() as conn:
        known_maps = [r["name"] for r in conn.execute("SELECT name FROM maps").fetchall()]
        tracked_players = [r["name"] for r in conn.execute("SELECT name FROM tracked_players").fetchall()]

    warnings = []
    img = Image.open(path)

    # --- OCR ---
    map_name, map_conf = extract_map_name(img, known_maps)
    if map_conf < 0.5:
        warnings.append(f"Low map confidence ({map_conf:.0%}): '{map_name}'")

    outcome, outcome_conf = extract_outcome(img)
    if outcome_conf < 0.7:
        warnings.append(f"Low outcome confidence ({outcome_conf:.0%})")

    my_rows = extract_player_rows(img, team="my")
    my_row = find_my_row(my_rows, username)
    if not my_row:
        warnings.append(f"Could not locate '{username}' in your team's rows")

    # --- Template matching ---
    icon_result = extract_heroes(path)
    if icon_result.get("warning"):
        warnings.append(icon_result["warning"])

    # --- Teammates ---
    all_rows = extract_player_rows(img, team="my")
    found_teammates = extract_tracked_players(all_rows, tracked_players)
    stack_size = 1 + len(found_teammates)

    # --- Build hero entries ---
    my_hero_names = icon_result.get("my_heroes", [])
    enemy_hero_names = icon_result.get("enemy_heroes", [])

    # If all detected, assign 100% to first hero (user can adjust in UI)
    my_heroes = [{"hero": h, "pct": 100} for h in my_hero_names[:1]] if my_hero_names else []
    enemy_heroes = [{"hero": h, "pct": 100} for h in enemy_hero_names] if enemy_hero_names else []

    return {
        "map": map_name,
        "outcome": outcome,
        "my_heroes": my_heroes,
        "enemy_heroes": enemy_heroes,
        "elims":      my_row.get("elims") if my_row else None,
        "deaths":     my_row.get("deaths") if my_row else None,
        "assists":    my_row.get("assists") if my_row else None,
        "damage":     my_row.get("damage") if my_row else None,
        "healing":    my_row.get("healing") if my_row else None,
        "mitigation": my_row.get("mitigation") if my_row else None,
        "teammates":  found_teammates,
        "stack_size": stack_size,
        "confidence": icon_result.get("confidence", 0.0),
        "warnings":   warnings,
    }
