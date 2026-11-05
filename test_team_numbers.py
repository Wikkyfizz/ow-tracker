"""Checks how the TEAM-tab stat grid bins Tesseract's words into rows and columns.
Tesseract is faked with word boxes taken from real scoreboards, so no screenshot is needed.
Run: venv/Scripts/python.exe test_team_numbers.py"""
from PIL import Image

from parser import ocr
from parser.ocr import ENEMY_TEAM_ROW_Y, MY_TEAM_ROW_Y, ROW_HALF_H, STAT_COLS

X0 = STAT_COLS["elims"][0]
IMG = Image.new("RGB", (1920, 1080))


def words(*ws):
    """ws: (text, left_px, right_px, y_centre_px) in screen pixels, for MY_TEAM_ROW_Y's block."""
    y_top = min(MY_TEAM_ROW_Y) - ROW_HALF_H
    return {"text": [w[0] for w in ws],
            "left": [w[1] - X0 for w in ws],
            "width": [w[2] - w[1] for w in ws],
            "top": [w[3] - 8 - y_top for w in ws],
            "height": [16 for _ in ws],
            "conf": [0 for _ in ws]}


def read(data, row_ys=MY_TEAM_ROW_Y):
    real = ocr.pytesseract.image_to_data
    ocr.pytesseract.image_to_data = lambda *a, **k: data
    try:
        return ocr._ocr_team_numbers_fast(IMG, row_ys)
    finally:
        ocr.pytesseract.image_to_data = real


def test_e_a_d_merged_into_one_word_is_not_read_as_assists():
    # Match 24, row "13 0 8": Tesseract returned one word "1308" spanning E→D (x 929–1051).
    rows, _ = read(words(("1308", 929, 1051, 341), ("9,131", 1100, 1150, 341)))
    assert rows[1]["assists"] is None, rows[1]
    assert rows[1]["elims"] is None and rows[1]["deaths"] is None
    assert rows[1]["damage"] == 9131


def test_a_merged_word_that_ends_inside_assists_is_skipped_too():
    # Match 36, "10 10": one word "10610" spanning E→A only (x 929–1002).
    rows, _ = read(words(("10610", 929, 1002, 405)))
    assert rows[2]["assists"] is None and rows[2]["elims"] is None


def test_separate_words_still_bin_by_column():
    rows, _ = read(words(("15", 929, 947, 341), ("5", 988, 996, 341), ("2", 1043, 1052, 341),
                         ("6,", 1110, 1125, 341), ("501", 1128, 1150, 341)))
    r = rows[1]
    assert (r["elims"], r["assists"], r["deaths"], r["damage"]) == (15, 5, 2, 6501), r


def test_a_word_reaching_a_few_px_past_its_column_still_counts():
    # Real words overhang their column a little, e.g. "1,240" in a gutter; that must not
    # count as spanning two columns.
    rows, _ = read(words(("22", 923, 948, 341), ("11", 1039, 1057, 341),
                         ("1,240", 1200, 1240, 341)))
    assert rows[1]["healing"] == 1240, rows[1]
    assert rows[1]["elims"] == 22 and rows[1]["deaths"] == 11


def test_three_digit_e_a_d_is_treated_as_unread():
    rows, _ = read(words(("104", 984, 1002, 341)))  # inside the A column, but impossible
    assert rows[1]["assists"] is None


def test_reports_where_each_row_was_found():
    # Match 37's enemy rows sit ~20px below the fixed estimate (rows with player titles).
    y_top = min(ENEMY_TEAM_ROW_Y) - ROW_HALF_H
    data = words(("3024", 933, 1052, 709), ("4,009", 1100, 1150, 709))
    data["top"] = [t + (min(MY_TEAM_ROW_Y) - ROW_HALF_H) - y_top for t in data["top"]]
    _, found = read(data, ENEMY_TEAM_ROW_Y)
    assert found[0] == 709 and found[1:] == [None] * 4, found


def test_fallback_reads_the_row_where_it_was_found():
    calls = []
    real_fast, real_num = ocr._ocr_team_numbers_fast, ocr._ocr_number
    empty = [{s: None for s in STAT_COLS} for _ in range(5)]
    ocr._ocr_team_numbers_fast = lambda img, ys: (empty, [ys[0] + 20, None, None, None, None])
    ocr._ocr_number = lambda img, region: calls.append(region) or 0
    try:
        ocr.extract_all_rows(IMG)
    finally:
        ocr._ocr_team_numbers_fast, ocr._ocr_number = real_fast, real_num
    row0 = (calls[0][1] + calls[0][3]) // 2
    row1 = (calls[6][1] + calls[6][3]) // 2
    assert row0 == MY_TEAM_ROW_Y[0] + 20, row0  # found 20px lower: crop there
    assert row1 == MY_TEAM_ROW_Y[1], row1       # nothing found: keep the estimate


def rows_read(centers):
    """The row y's extract_all_rows reads for a synthetic scoreboard with these row centres."""
    from test_row_alignment import screenshot
    seen = []
    real_fast, real_num = ocr._ocr_team_numbers_fast, ocr._ocr_number
    ocr._ocr_team_numbers_fast = lambda img, ys: (seen.append(list(ys)) or
                                                  ([{s: 0 for s in STAT_COLS} for _ in ys], [None] * len(ys)))
    ocr._ocr_number = lambda img, region: 0
    try:
        ocr.extract_all_rows(Image.fromarray(screenshot(centers)[:, :, ::-1]))
    finally:
        ocr._ocr_team_numbers_fast, ocr._ocr_number = real_fast, real_num
    return seen


def test_full_teams_keep_the_fixed_rows():
    # Player titles push rows down by up to ~36px on real scoreboards (SlCTA43i5k).
    my, enemy = rows_read([274, 344, 415, 486, 552, 708, 775, 846, 917, 996])
    assert my == MY_TEAM_ROW_Y and enemy == ENEMY_TEAM_ROW_Y, (my, enemy)


def test_a_full_enemy_team_below_a_short_one_is_measured():
    # Match 36: a leaver on the player's team pulls all 5 enemy rows ~56px up. Fixed rows
    # dropped the enemy tank's row and shifted every enemy stat row up one slot.
    centers = [274, 341, 405, 471, 632, 697, 764, 831, 894]
    my, enemy = rows_read(centers)
    assert len(my) == 4 and all(abs(a - b) <= 1 for a, b in zip(enemy, centers[4:])), enemy


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
