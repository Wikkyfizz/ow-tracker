"""Guards the rule that data/maps.csv is the only list of maps.
Run: venv/Scripts/python.exe test_reference_data.py"""
import csv
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
_tmp_dir = tempfile.TemporaryDirectory()
os.environ["OW_TRACKER_DB"] = str(Path(_tmp_dir.name) / "t.db")

import db  # noqa: E402  (must follow the env override, so the real DB is never touched)
from parser.pipeline import known_maps  # noqa: E402

# Mock data and page mockups name maps as content, not as a list the app reads.
ALLOWED = {"seed_mock.py", "test_merge.py", "test_reference_data.py"}
SKIP_DIRS = {"venv", "node_modules", "docs", "__pycache__", ".git", "data", "e2e", "hero_icons", "portraits"}


def csv_map_names():
    with open(ROOT / "data" / "maps.csv", encoding="utf-8") as f:
        return [r["name"] for r in csv.DictReader(f)]


def source_files():
    for path in ROOT.rglob("*"):
        if path.suffix in {".py", ".js", ".html"} and not SKIP_DIRS & set(path.relative_to(ROOT).parts):
            yield path


def test_no_map_list_outside_the_csv():
    # Two or more map names in one file is a list; one could be an example in a comment.
    names = csv_map_names()
    offenders = {}
    for path in source_files():
        if path.name in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        found = [n for n in names if n in text]
        if len(found) >= 2:
            offenders[path.name] = found
    assert not offenders, f"Map names hardcoded outside data/maps.csv: {offenders}"


def test_startup_brings_a_stale_db_up_to_the_csv():
    db.init_db()
    with db.get_conn() as conn:
        conn.execute("DELETE FROM maps WHERE name=?", (csv_map_names()[-1],))
    db.init_db()
    assert sorted(known_maps()) == sorted(csv_map_names())


def test_startup_keeps_an_affinity_edited_in_settings():
    db.init_db()
    name = csv_map_names()[0]
    with db.get_conn() as conn:
        conn.execute("UPDATE maps SET comp_affinity='Poke' WHERE name=?", (name,))
    db.init_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT comp_affinity FROM maps WHERE name=?", (name,)).fetchone()
    assert row["comp_affinity"] == "Poke"


def test_startup_applies_a_hero_role_change():
    db.init_db()
    with db.get_conn() as conn:
        conn.execute("UPDATE heroes SET role='Damage' WHERE name='Sombra'")
    db.init_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT role FROM heroes WHERE name='Sombra'").fetchone()
    assert row["role"] == "Support"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
