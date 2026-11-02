"""Reading and learning heroes from Summary cards, on drawn cards in a temporary folder.
Run: venv/Scripts/python.exe test_hero_names.py"""
import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.TemporaryDirectory()
os.environ["OW_TRACKER_HERO_NAMES"] = str(Path(_tmp_dir.name) / "hero_names")

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from parser.hero_names import HERO_NAMES_DIR, learn_cards, read_cards  # noqa: E402


def summary(*names):
    """A blank 1920×1080 screen with a name drawn on each hero card."""
    canvas = np.zeros((1080, 1920), np.uint8)
    for card, name in enumerate(names):
        cv2.putText(canvas, name, (270, 312 + card * 240), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 255, 3)
    path = Path(_tmp_dir.name) / f"{'-'.join(names)}.png"
    Image.fromarray(canvas).save(path)
    return str(path)


def read(path, pcts):
    return read_cards(Image.open(path), list(range(len(pcts))), pcts)


def clear():
    for p in HERO_NAMES_DIR.glob("*.png"):
        p.unlink()


def test_an_unknown_hero_is_left_for_the_player():
    clear()
    assert read(summary("ZARYA"), [100]) == [{"card": 0, "pct": 100, "hero": None}]


def test_a_picked_hero_is_recognised_next_time():
    clear()
    first = summary("ZARYA", "ORISA")
    played = read(first, [94, 6])
    assert learn_cards(first, played, [("Zarya", 94), ("Orisa", 6)]) == ["Zarya", "Orisa"]
    # Same names in a different order, and a new one stays unread.
    again = read(summary("ORISA", "SIGMA", "ZARYA"), [60, 30, 10])
    assert [c["hero"] for c in again] == ["Orisa", None, "Zarya"]


def test_an_edited_percent_teaches_nothing():
    clear()
    first = summary("ZARYA")
    assert learn_cards(first, read(first, [100]), [("Zarya", 90), ("Orisa", 10)]) == []


def test_two_cards_on_the_same_percent_aren_t_guessed():
    clear()
    first = summary("ZARYA", "ORISA")
    assert learn_cards(first, read(first, [50, 50]), [("Zarya", 50), ("Orisa", 50)]) == []


def test_a_recognised_card_keeps_its_template():
    clear()
    first = summary("ZARYA")
    learn_cards(first, read(first, [100]), [("Zarya", 100)])
    before = (HERO_NAMES_DIR / "Zarya.png").read_bytes()
    second = summary("ZARYA", "SIGMA")
    assert learn_cards(second, read(second, [70, 30]), [("Orisa", 70), ("Sigma", 30)]) == ["Sigma"]
    assert (HERO_NAMES_DIR / "Zarya.png").read_bytes() == before


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
