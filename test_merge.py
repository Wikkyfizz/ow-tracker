"""Checks for the SUMMARY + TEAM merge logic. Run: venv/Scripts/python.exe test_merge.py"""
from parser.pipeline import is_same_game, match_summary_row, merge_summary_team


def row(e, a, d, dmg=1000, heal=0, mit=0):
    return {"elims": e, "assists": a, "deaths": d, "damage": dmg, "healing": heal, "mitigation": mit}


def team(*rows):
    return {"team_rows": {"my_team": list(rows), "enemy_team": []},
            "my_team_heroes": [], "enemy_heroes": [], "warnings": []}


def summary(e, a, d, pcts=(100,)):
    return {"elims": e, "assists": a, "deaths": d, "played_pcts": list(pcts), "map": "Colosseo",
            "outcome": "Win", "game_length_s": 422, "played_at": "2026-10-31T13:53:00",
            "game_mode": "Push", "warnings": []}


def test_finds_a_non_tank_row():
    t = team(row(16, 3, 3), row(16, 3, 5, dmg=9000))
    assert match_summary_row(summary(16, 3, 5), t) == (3, 1)


def test_tolerates_a_misread_leading_one():
    t = team(row(7, 3, 9, dmg=8569), row(22, 4, 10))
    assert is_same_game(summary(17, 3, 9), t)
    merged = merge_summary_team(summary(17, 3, 9), t)
    assert merged["elims"] == 17 and merged["damage"] == 8569 and merged["my_row"] == 0


def test_tolerates_a_blank_cell():
    assert is_same_game(summary(20, 0, 2), team(row(20, None, 2)))


def test_rejects_a_different_game():
    assert not is_same_game(summary(25, 4, 3), team(row(16, 7, 7), row(16, 0, 11)))


def test_tied_rows_leave_the_row_unknown():
    t = team(row(10, 2, 5, dmg=1), row(10, 2, 7, dmg=2), row(10, 2, 9, dmg=3))
    merged = merge_summary_team(summary(10, 2, 1), t)
    assert merged["my_row"] is None and merged["damage"] is None
    assert any("which scoreboard row" in w for w in merged["warnings"])


def test_summary_supplies_the_game_details():
    merged = merge_summary_team(summary(25, 4, 3), team(row(25, 4, 3, 6370, 1292, 9449)))
    assert merged["map"] == "Colosseo" and merged["played_at"] == "2026-10-31T13:53:00"
    assert merged["game_length_s"] == 422 and merged["mitigation"] == 9449
    assert merged["merged"] is True and merged["warnings"] == []


def test_a_hero_split_asks_for_a_pick():
    merged = merge_summary_team(summary(25, 4, 3, (88, 12)), team(row(25, 4, 3)))
    assert any("88% + 12%" in w for w in merged["warnings"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
