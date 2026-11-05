"""Folders the developer scripts work on, read from settings.json so no one's own
paths end up in the code. The app itself reads settings through main.load_settings."""
import json
from pathlib import Path

_SETTINGS = Path(__file__).parent / "settings.json"


def inbox() -> Path:
    """The screenshot inbox set in Settings (falls back to the app's default)."""
    try:
        folder = json.loads(_SETTINGS.read_text(encoding="utf-8")).get("inbox_folder")
    except (OSError, ValueError):
        folder = None
    return Path(folder or r"C:\OW-Tracker\inbox")
