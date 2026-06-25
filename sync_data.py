"""Apply data/heroes.csv + data/maps.csv to the live DB, and rewrite the CSVs
in clean canonical form (casing/order normalized via db.py's loaders).

Run after editing the CSVs:  .\\venv\\Scripts\\python.exe sync_data.py

db.py loads + validates the CSVs on import, so an invalid value (unknown
archetype, bad role) raises here before anything is written.
"""
import csv

import db

HERO_HEADER = ["name", "role", "sub_role", "primary_archetype"]
MAP_HEADER = ["name", "game_mode", "comp_affinity", "notes"]


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


def main():
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
