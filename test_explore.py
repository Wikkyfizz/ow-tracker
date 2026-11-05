"""Checks for the Explore questions. Run: venv/Scripts/python.exe test_explore.py"""
from explore import by_hero, condition, value, versus


def p(team, role, e, d, dmg=5000, a=5, heal=0, mit=0, hero="X", me=False):
    return {"team": team, "role": role, "hero": hero, "is_me": me,
            "stats": {"elims": e, "assists": a, "deaths": d, "damage": dmg, "healing": heal, "mitigation": mit}}


def game(outcome, players, minutes=10):
    return {"id": 0, "outcome": outcome, "minutes": minutes, "players": players,
            "me": next((x for x in players if x["is_me"]), None)}


ME = dict(team="ally", role="Tank", hero="Winston", me=True)


def test_condition_counts_each_team_and_skips_me():
    g1 = game("Loss", [p(**ME, e=2, d=9), p("ally", "Damage", 3, 8), p("enemy", "Damage", 20, 2)])
    g2 = game("Win", [p(**ME, e=20, d=2), p("ally", "Damage", 15, 4), p("enemy", "Damage", 2, 9)])
    r = condition([g1, g2], "Damage", "kd", "lt", 1)
    assert r["ally"]["hits"] == 1 and r["ally"]["wr_when"] == 0.0 and r["ally"]["wr_otherwise"] == 1.0
    assert r["enemy"]["hits"] == 1 and r["enemy"]["wr_when"] == 1.0
    # My own bad K/D is never what triggers a "tank on my team" hit.
    assert condition([g1], "Tank", "kd", "lt", 1)["ally"]["unknown"] == 1


def test_per10_scales_by_game_length():
    pl = p("ally", "Damage", 10, 5, dmg=20000)
    assert value(pl, "damage", 20, per10=True) == 10000
    assert value(pl, "damage", None, per10=True) is None
    assert value(pl, "kd", 20, per10=True) == 2


def test_zero_deaths_kd_and_implausible_assists():
    assert value(p("ally", "Damage", 7, 0), "kd") == 7.0
    assert value(p("ally", "Damage", 7, 1, a=1308), "assists") is None


def test_versus_enemy_tank():
    g1 = game("Win", [p(**ME, e=20, d=3, dmg=12000), p("enemy", "Tank", 10, 6, dmg=8000)])
    g2 = game("Loss", [p(**ME, e=5, d=8, dmg=6000), p("enemy", "Tank", 15, 2, dmg=11000)])
    r = versus([g1, g2], "enemy", "Tank")
    dmg = next(s for s in r["stats"] if s["stat"] == "damage")
    assert dmg["better"] == 1 and dmg["wr_better"] == 1.0 and dmg["wr_worse"] == 0.0
    assert dmg["my_avg"] == 9000
    deaths = next(s for s in r["stats"] if s["stat"] == "deaths")
    assert deaths["better"] == 1  # 3 < 6 in g1
    kd = next(s for s in r["stats"] if s["stat"] == "kd")
    assert kd["my_avg"] == round(25 / 11, 2)
    assert r["overall"]["better"] == 1 and r["overall"]["worse"] == 1


def test_versus_averages_a_two_player_role():
    g = game("Win", [p(**ME, e=10, d=5, dmg=9000),
                     p("enemy", "Damage", 5, 5, dmg=6000), p("enemy", "Damage", 5, 5, dmg=14000)])
    dmg = next(s for s in versus([g], "enemy", "Damage")["stats"] if s["stat"] == "damage")
    assert dmg["their_avg"] == 10000 and dmg["worse"] == 1


def test_by_hero():
    gs = [game("Win", [p(**ME, e=10, d=0, dmg=10000)]),
          game("Loss", [p(**ME, e=10, d=5, dmg=20000)], minutes=20),
          game("Win", [p(**{**ME, "hero": "D.Va"}, e=1, d=1)])]
    r = {h["hero"]: h for h in by_hero(gs)["heroes"]}
    assert r["Winston"]["games"] == 2 and r["Winston"]["win_rate"] == 0.5
    assert r["Winston"]["damage"] == 15000 and r["Winston"]["kd"] == 4.0
    assert {h["hero"]: h for h in by_hero(gs, per10=True)["heroes"]}["Winston"]["damage"] == 10000


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
