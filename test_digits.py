"""Checks the template digit reader on real scoreboard cells Tesseract got wrong or missed.
The cells in test_data/digit_cells/ are named after what they show.
Run: venv/Scripts/python.exe test_digits.py"""
from pathlib import Path

from PIL import Image

from parser import digits

CELLS = Path(__file__).parent / "test_data" / "digit_cells"


def read(name):
    return digits.read_cell(Image.open(CELLS / f"{name}.png"))


def test_eleven_keeps_both_ones():
    # Tesseract read this "11" as "1", in the block pass and per cell.
    assert read("11") == 11


def test_seventeen_keeps_its_leading_one():
    assert read("17") == 17


def test_longer_numbers_with_ones():
    assert read("11115") == 11115
    assert read("1328") == 1328  # Tesseract had saved it as 1928


def test_dim_grey_zero_is_read():
    # A zero is drawn dim grey; Tesseract left these blank.
    assert read("0_dim") == 0


def test_zero_beside_the_dark_strip_past_the_panel_is_read():
    # The MIT column runs past the panel's edge into a dark strip.
    assert read("0_panel_edge") == 0


def test_touching_digits_are_split():
    assert read("440_touching") == 440
    assert read("2648_touching") == 2648


def test_the_brighter_own_player_row():
    assert read("14017_own_row") == 14017


def test_a_cell_it_cannot_read_is_blank_not_wrong():
    # A flaming name banner glows over this "3". Blank lets Tesseract try; a wrong number wouldn't.
    assert read("3_banner_glow") in (None, 3)


def test_an_empty_cell_is_blank():
    assert digits.read_cell(Image.new("RGB", (50, 56), (120, 20, 40))) is None


def test_without_templates_it_reads_nothing():
    saved_dir, saved = digits.TEMPLATE_DIR, digits._templates
    digits.TEMPLATE_DIR, digits._templates = CELLS / "missing", None
    try:
        assert read("11") is None
    finally:
        digits.TEMPLATE_DIR, digits._templates = saved_dir, saved


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"{len(tests)} passed")
