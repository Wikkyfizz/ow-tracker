"""Checks scoreboard row measuring on a synthetic screenshot.
Run: venv/Scripts/python.exe test_row_alignment.py"""
import numpy as np

from parser.ocr import STAT_COLS_FRAC, row_slots

W, H = 1920, 1080
CENTERS = [274, 344, 415, 486, 552, 708, 775, 846, 917, 988]  # uneven, as with player titles


def screenshot(centers=CENTERS):
    img = np.zeros((H, W, 3), np.uint8)
    img[205:238, 535:1385] = 230  # the white column-header bar
    x1 = int(STAT_COLS_FRAC["damage"][0] * W) + 5
    x2 = int(STAT_COLS_FRAC["mitigation"][1] * W) - 5
    img[610, x1:x2] = 230  # the thin "VS" divider line
    for cy in centers:
        img[cy - 8:cy + 8, x1:x2] = 230  # a row of digits
    return img


def test_rows_are_measured_not_assumed():
    my, enemy = row_slots(W, H, screenshot())
    measured = [(top + bot) // 2 for _, top, _, bot in my + enemy]
    assert all(abs(a - b) <= 1 for a, b in zip(measured, CENTERS)), measured


def test_the_player_row_ignores_the_header_bar():
    my, _ = row_slots(W, H, screenshot())
    assert abs((my[0][1] + my[0][3]) // 2 - 274) <= 1


def test_a_leaver_leaves_that_team_a_row_short():
    # A leaver's row is removed, not blanked, and the rows below it move up.
    short = CENTERS[:5] + [708, 775, 846, 917]
    my, enemy = row_slots(W, H, screenshot(short))
    assert len(my) == 5 and len(enemy) == 4
    measured = [(top + bot) // 2 for _, top, _, bot in my + enemy]
    assert all(abs(a - b) <= 1 for a, b in zip(measured, short)), measured


def test_falls_back_when_rows_cannot_be_found():
    my, enemy = row_slots(W, H, np.zeros((H, W, 3), np.uint8))
    assert (my[0][1] + my[0][3]) // 2 == 270 and (enemy[0][1] + enemy[0][3]) // 2 == 688


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
