"""Checks for the SUMMARY + TEAM merge logic. Run: venv/Scripts/python.exe test_merge.py"""
from parser.pipeline import build_participants, is_same_game, match_summary_row, merge_summary_team


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


def scoreboard(**extra):
    return {"team_rows": {"my_team": [row(1, 1, 1, dmg=100), row(2, 2, 2, dmg=200), row(3, 3, 3, dmg=300)],
                          "enemy_team": [row(4, 4, 4, dmg=400)]},
            "my_team_heroes": [{"hero": "Winston"}, {"hero": "Unknown DPS"}, {"hero": "Tracer"}],
            "enemy_heroes": [{"hero": "Reaper"}], **extra}


def test_participants_keep_every_row_in_order():
    rows = build_participants(scoreboard())
    assert [(p["team"], p["slot"]) for p in rows] == [("ally", 0), ("ally", 1), ("ally", 2), ("enemy", 0)]
    assert rows[2]["stats"]["damage"] == 300 and rows[3]["stats"]["elims"] == 4


def test_an_unknown_hero_does_not_shift_the_rows_below_it():
    rows = build_participants(scoreboard())
    assert rows[1]["heroes"] == [] and rows[2]["heroes"] == [{"hero": "Tracer", "pct": 100}]


def test_confirmed_heroes_replace_detected_ones():
    rows = build_participants(scoreboard(), {"my": ["Sigma", "Genji", None], "enemy": ["Ana"]})
    assert [p["heroes"][0]["hero"] if p["heroes"] else None for p in rows] == ["Sigma", "Genji", None, "Ana"]


def test_my_row_is_marked_and_uses_confirmed_stats():
    rows = build_participants(scoreboard(my_row=1), None, {"elims": 17, "damage": None})
    assert [p["is_me"] for p in rows] == [False, True, False, False]
    assert rows[1]["stats"]["elims"] == 17 and rows[1]["stats"]["damage"] == 200


def test_an_unmerged_team_screenshot_marks_no_row_as_me():
    assert not any(p["is_me"] for p in build_participants(scoreboard()))


def test_a_summary_only_parse_has_no_participants():
    assert build_participants({"tab_type": "SUMMARY", "my_team_heroes": [], "enemy_heroes": []}) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
