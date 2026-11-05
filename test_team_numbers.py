"""Checks how the TEAM-tab stat grid bins Tesseract's words into rows and columns.
Tesseract is faked with word boxes taken from real scoreboards, so no screenshot is needed.
Run: venv/Scripts/python.exe test_team_numbers.py"""
from PIL import Image

from parser import ocr
from parser.ocr import ENEMY_TEAM_ROW_Y, MY_TEAM_ROW_Y, ROW_HALF_H, STAT_COLS

X0 = STAT_COLS["elims"][0]
IMG = Image.new("RGB", (1920, 1080))


def words(*ws, rows=MY_TEAM_ROW_Y):
    """ws: (text, left_px, right_px, y_centre_px) in screen pixels, for the block read at rows."""
    y_top = min(rows) - ROW_HALF_H
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
    rows, *_ = read(words(("1308", 929, 1051, 341), ("9,131", 1100, 1150, 341)))
    assert rows[1]["assists"] is None, rows[1]
    assert rows[1]["elims"] is None and rows[1]["deaths"] is None
    assert rows[1]["damage"] == 9131


def test_a_merged_word_that_ends_inside_assists_is_skipped_too():
    # Match 36, "10 10": one word "10610" spanning E→A only (x 929–1002).
    rows, *_ = read(words(("10610", 929, 1002, 405)))
    assert rows[2]["assists"] is None and rows[2]["elims"] is None


def test_separate_words_still_bin_by_column():
    rows, *_ = read(words(("15", 929, 947, 341), ("5", 988, 996, 341), ("2", 1043, 1052, 341),
                         ("6,", 1110, 1125, 341), ("501", 1128, 1150, 341)))
    r = rows[1]
    assert (r["elims"], r["assists"], r["deaths"], r["damage"]) == (15, 5, 2, 6501), r


def test_a_word_reaching_a_few_px_past_its_column_still_counts():
    # Real words overhang their column a little, e.g. "1,240" in a gutter; that must not
    # count as spanning two columns.
    rows, *_ = read(words(("22", 923, 948, 341), ("11", 1039, 1057, 341),
                         ("1,240", 1200, 1240, 341)))
    assert rows[1]["healing"] == 1240, rows[1]
    assert rows[1]["elims"] == 22 and rows[1]["deaths"] == 11


def test_three_digit_e_a_d_is_treated_as_unread():
    rows, *_ = read(words(("104", 984, 1002, 341)))  # inside the A column, but impossible
    assert rows[1]["assists"] is None


def test_reports_where_each_row_was_found():
    # Match 37's enemy rows sit ~20px below the fixed estimate (rows with player titles).
    data = words(("3024", 933, 1052, 709), ("4,009", 1100, 1150, 709), rows=ENEMY_TEAM_ROW_Y)
    _, found, _ = read(data, ENEMY_TEAM_ROW_Y)
    assert found[0] == 709 and found[1:] == [None] * 4, found


def test_fallback_reads_the_row_where_it_was_found():
    calls = []
    real_fast, real_num = ocr._ocr_team_numbers_fast, ocr._ocr_number
    empty = [{s: None for s in STAT_COLS} for _ in range(5)]
    ocr._ocr_team_numbers_fast = lambda img, ys: (empty, [ys[0] + 20, None, None, None, None], 0)
    ocr._ocr_number = lambda img, region: calls.append(region) or 0
    try:
        ocr.extract_all_rows(IMG)
    finally:
        ocr._ocr_team_numbers_fast, ocr._ocr_number = real_fast, real_num
    row0 = (calls[0][1] + calls[0][3]) // 2
    row1 = (calls[6][1] + calls[6][3]) // 2
    assert row0 == MY_TEAM_ROW_Y[0] + 20, row0  # found 20px lower: crop there
    assert row1 == MY_TEAM_ROW_Y[1], row1       # nothing found: keep the estimate


def rows_read(centers, binned=lambda ys: 0):
    """For a synthetic scoreboard with these row centres: (my rows, enemy rows) that
    extract_all_rows read, and how many one-pass reads it made. binned(ys) fakes how many
    digit-words the one-pass read finds at rows ys."""
    from test_row_alignment import screenshot
    calls, crops = [], []
    real_fast, real_num = ocr._ocr_team_numbers_fast, ocr._ocr_number
    ocr._ocr_team_numbers_fast = lambda img, ys: (calls.append(list(ys)) or
                                                  ([{s: None for s in STAT_COLS} for _ in ys],
                                                   [None] * len(ys), binned(list(ys))))
    ocr._ocr_number = lambda img, region: crops.append((region[1] + region[3]) // 2) or 0
    try:
        ocr.extract_all_rows(Image.fromarray(screenshot(centers)[:, :, ::-1]))
    finally:
        ocr._ocr_team_numbers_fast, ocr._ocr_number = real_fast, real_num
    ys = crops[::len(STAT_COLS)]  # every cell fell back; one crop centre per row
    return ys[:-5], ys[-5:], len(calls)


# Overwatch_a3ozeQBJlu: the player's team sits on the fixed rows, the enemy ~30px below.
DRIFTED = [274, 343, 414, 485, 555, 717, 786, 857, 925, 993]


def near(ys, centers):
    """Rows measured from the synthetic screenshot land within 1px of its centres."""
    return len(ys) == len(centers) and all(abs(a - b) <= 1 for a, b in zip(ys, centers))


def is_enemy_measured(ys):
    return near(ys, DRIFTED[5:])


def test_full_teams_keep_the_fixed_rows():
    # Player titles push rows down by up to ~36px on real scoreboards (SlCTA43i5k).
    # With no sign that the fixed rows miss digits, they stay.
    my, enemy, _ = rows_read([274, 344, 415, 486, 552, 708, 775, 846, 917, 996])
    assert my == MY_TEAM_ROW_Y and enemy == ENEMY_TEAM_ROW_Y, (my, enemy)


def test_a_full_enemy_team_below_a_short_one_is_measured():
    # Match 36: a leaver on the player's team pulls all 5 enemy rows ~56px up. Fixed rows
    # dropped the enemy tank's row and shifted every enemy stat row up one slot.
    centers = [274, 341, 405, 471, 632, 697, 764, 831, 894]
    my, enemy, _ = rows_read(centers)
    assert len(my) == 4 and all(abs(a - b) <= 1 for a, b in zip(enemy, centers[4:])), enemy


def test_digits_outside_every_row_band_are_not_binned():
    # Overwatch_a3ozeQBJlu, enemy rows 1-2 as Tesseract boxed them. At the fixed rows
    # (688, 756) they fall outside the +-28px bands, so nothing was read; the per-cell
    # fallback then cropped the fixed rows and cut the digits in half.
    ws = [("255", 928, 1052, 716.5), ("16,012", 1109, 1149, 718), ("21", 1224, 1240, 716.5),
          ("18,044", 1308, 1348, 717), ("617", 929, 1052, 787.5), ("12,549", 1109, 1149, 788)]
    measured = [717, 786, 857, 925, 993]
    rows, found, binned = read(words(*ws, rows=ENEMY_TEAM_ROW_Y), ENEMY_TEAM_ROW_Y)
    assert binned == 0 and found == [None] * 5 and rows[0]["damage"] is None, (binned, found)
    rows, found, binned = read(words(*ws, rows=measured), measured)
    assert binned == 6 and rows[0]["damage"] == 16012 and rows[1]["damage"] == 12549, rows
    assert rows[0]["mitigation"] == 18044 and found[:2] == [717, 788], found


def test_a_drifted_team_is_read_at_measured_rows_when_they_bin_clearly_more():
    _, enemy, _ = rows_read(DRIFTED, binned=lambda ys: 19 if is_enemy_measured(ys) else 0)
    assert near(enemy, DRIFTED[5:]), enemy


def test_a_drifted_team_keeps_the_fixed_rows_for_a_one_word_gain():
    # Two crops of one block often differ by a word; that alone is no reason to move rows.
    _, enemy, _ = rows_read(DRIFTED, binned=lambda ys: 30 if is_enemy_measured(ys) else 29)
    assert enemy == ENEMY_TEAM_ROW_Y, enemy


def test_the_bottom_row_cut_off_by_the_block_counts_as_drift():
    # Overwatch_Q6vAdOYyVP: enemy rows 21-28px low. The fixed block ends at 988, mid-way
    # through the last row, which came back empty; measured rows bin 29 words to 23.
    centers = DRIFTED[:5] + [709, 776, 845, 919, 988]
    _, enemy, _ = rows_read(centers, binned=lambda ys: 29 if near(ys, centers[5:]) else 23)
    assert near(enemy, centers[5:]), enemy


def test_a_small_drift_is_read_once():
    # Within 14px the digits stay inside the fixed rows' bands: no second read.
    my, enemy, calls = rows_read([274, 340, 404, 469, 532, 688, 751, 815, 880, 950],
                                 binned=lambda ys: 99 if ys[0] != 688 and ys[0] != 270 else 0)
    assert calls == 2 and my == MY_TEAM_ROW_Y and enemy == ENEMY_TEAM_ROW_Y, (calls, my, enemy)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
