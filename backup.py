"""Copies per-user data to the folder set in Settings (ideally on another disk).
Runs at startup and then daily. Dated database snapshots are pruned; screenshots and
name templates are copied once and never removed from the backup.
Run now: venv/Scripts/python.exe backup.py"""
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

KEEP_DB_SNAPSHOTS = 14


def _snapshot_db(db_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f"ow_tracker-{datetime.now():%Y-%m-%d}.db"
    # sqlite's backup API, not a file copy, so a write in progress can't corrupt it.
    source = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
    finally:
        copy.close()
        source.close()
    for old in sorted(dest.glob("ow_tracker-*.db"))[:-KEEP_DB_SNAPSHOTS]:
        old.unlink()
    return target


def _mirror_new_files(src: Path, dest: Path) -> int:
    if not src.is_dir():
        return 0
    copied = 0
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        target = dest / path.relative_to(src)
        if not target.exists() or target.stat().st_size != path.stat().st_size:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
    return copied


def run_backup(dest_folder: str, db_path: Path, inbox: Path, settings_path: Path, names_dir: Path) -> dict:
    dest = Path(dest_folder)
    snapshot = _snapshot_db(db_path, dest / "database")
    copied = _mirror_new_files(inbox, dest / "screenshots") + _mirror_new_files(names_dir, dest / "player_names")
    if settings_path.exists():
        shutil.copy2(settings_path, dest / "settings.json")
    return {"at": datetime.now().isoformat(timespec="seconds"), "snapshot": str(snapshot), "files_copied": copied}


if __name__ == "__main__":
    import db
    from parser.names import NAMES_DIR
    root = Path(__file__).parent
    settings = json.loads((root / "settings.json").read_text(encoding="utf-8"))
    print(run_backup(settings["backup_folder"], db.DB_PATH, Path(settings["inbox_folder"]),
                     root / "settings.json", NAMES_DIR))
