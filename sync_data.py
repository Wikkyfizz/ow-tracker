"""Apply data/heroes.csv + data/maps.csv to the live DB, and rewrite the CSVs
in clean canonical form (casing/order normalized via db.py's loaders).

Run after editing the CSVs:  .\\venv\\Scripts\\python.exe sync_data.py

db.py loads + validates the CSVs on import, so an invalid value (unknown
archetype, bad role) raises here before anything is written.

Run after a game update:  .\\venv\\Scripts\\python.exe sync_data.py --fetch

Adds new heroes and ranked maps from OverFast and applies hero role changes.
Unlike the plain sync, it leaves existing archetypes and map affinities alone,
so edits made in Settings survive. New rows get "Flex"/"Neutral" until reviewed.
"""
import csv
import re
import sys
import unicodedata

import db

HERO_HEADER = ["name", "role", "sub_role", "primary_archetype"]
MAP_HEADER = ["name", "game_mode", "comp_affinity", "notes"]
OVERFAST = "https://overfast-api.tekrop.fr"


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def _sync_table(conn, table, cols, rows):
    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in cols[1:])
    conn.executemany(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT({cols[0]}) DO UPDATE SET {updates}",
        rows,
    )
    keep = {r[0] for r in rows}
    existing = {r[0] for r in conn.execute(f"SELECT {cols[0]} FROM {table}")}
    removed = existing - keep
    for name in removed:
        conn.execute(f"DELETE FROM {table} WHERE {cols[0]}=?", (name,))
    return len(rows), removed


def _name_key(name):
    # Accent- and punctuation-insensitive, so "Lúcio" = "Lucio", "King’s" = "King's".
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _get_json(path):
    import httpx

    r = httpx.get(OVERFAST + path, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_updates():
    hero_path, map_path = db.DATA_DIR / "heroes.csv", db.DATA_DIR / "maps.csv"
    heroes, maps = _read_csv(hero_path), _read_csv(map_path)
    by_key = {_name_key(h["name"]): h for h in heroes}
    map_keys = {_name_key(m["name"]) for m in maps}
    new_heroes, new_maps, role_changes = [], [], []

    for h in _get_json("/heroes"):
        role = h["role"].title()
        row = by_key.get(_name_key(h["name"]))
        if row is None:
            heroes.append({"name": h["name"], "role": role, "sub_role": "", "primary_archetype": "Flex"})
            new_heroes.append(h["name"])
        elif row["role"].strip().title() != role:
            role_changes.append((row["name"], role))
            row["role"] = role

    # "standard" = the maps in the regular QP/ranked pool (not arcade/stadium).
    for m in _get_json("/maps"):
        if "standard" in m["uses"] and _name_key(m["name"]) not in map_keys:
            maps.append({"name": m["name"], "game_mode": m["gamemodes"][0].title(),
                         "comp_affinity": "Neutral", "notes": ""})
            new_maps.append(m["name"])

    _write_csv(hero_path, HERO_HEADER, [[h[c] for c in HERO_HEADER] for h in heroes])
    _write_csv(map_path, MAP_HEADER, [[m[c] for c in MAP_HEADER] for m in maps])

    with db.get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO heroes (name, role, sub_role, primary_archetype) VALUES (?,?,?,?)",
            db._load_heroes_seed(),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO maps (name, game_mode, comp_affinity, notes) VALUES (?,?,?,?)",
            db._load_maps_seed(),
        )
        conn.executemany("UPDATE heroes SET role=? WHERE name=?", [(r, n) for n, r in role_changes])

    print(f"New heroes: {new_heroes or 'none'}")
    print(f"Role changes: {role_changes or 'none'}")
    print(f"New maps: {new_maps or 'none'}")
    if new_heroes or new_maps:
        print("Review the defaults in data/*.csv: new heroes are Flex with no sub-role, new maps are Neutral.")
    if new_heroes or role_changes:
        print("Check parser/icons.py aliases if a new name has punctuation (e.g. D.Mon).")


def main():
    if "--fetch" in sys.argv:
        fetch_updates()
        return
    # db.HEROES_SEED / MAPS_SEED are already validated + normalized on import.
    # Sync the DB first (the source the app reads); CSV cleanup is cosmetic.
    with db.get_conn() as conn:
        nh, rh = _sync_table(conn, "heroes", HERO_HEADER, db.HEROES_SEED)
        nm, rm = _sync_table(conn, "maps", MAP_HEADER, db.MAPS_SEED)
    print(f"Synced {nh} heroes (removed: {sorted(rh) or 'none'})")
    print(f"Synced {nm} maps (removed: {sorted(rm) or 'none'})")

    try:
        _write_csv(db.DATA_DIR / "heroes.csv", HERO_HEADER, db.HEROES_SEED)
        _write_csv(db.DATA_DIR / "maps.csv", MAP_HEADER, db.MAPS_SEED)
        print("Rewrote data/heroes.csv and data/maps.csv in canonical form.")
    except PermissionError as e:
        print(f"WARNING: DB synced, but couldn't rewrite a CSV (is it open?): {e}")


if __name__ == "__main__":
    main()
