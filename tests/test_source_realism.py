from dfs.models import DKSalaryRow
from dfs.providers.source_realism import (
    BLOCK,
    WARN,
    check_source_realism,
)


def _row(name, team, positions, game_info="AAA@BBB 7:05PM ET", dk_id=None, salary=5000):
    return DKSalaryRow(
        dk_player_id=dk_id or f"id-{name}-{team}", name=name, team_abbrev=team, dk_positions=list(positions),
        salary=salary, game_info=game_info,
    )


def _small_realistic_slate():
    rows = []
    for team, opp in (("AAA", "BBB"), ("BBB", "AAA")):
        rows.append(_row(f"{team} Ace", team, ["SP"]))
        rows.append(_row(f"{team} Setup", team, ["RP"]))
        rows.append(_row(f"{team} Closer", team, ["RP"]))
        for i in range(6):
            rows.append(_row(f"{team} Hitter {i}", team, ["OF"]))
    return rows


def test_realistic_small_slate_has_no_findings():
    report = check_source_realism(_small_realistic_slate(), game_count=1)
    assert report.blocked is False
    assert report.findings == []


def test_empty_rows_produce_no_findings():
    report = check_source_realism([], game_count=0)
    assert report.blocked is False
    assert report.findings == []


def test_suspicious_pitcher_count_per_team_blocks():
    # Modeled on the real 2026-08-18 LAD case: 30 pitcher-eligible rows
    # for one team in one game.
    rows = _small_realistic_slate()
    for i in range(20):
        rows.append(_row(f"AAA Extra Pitcher {i}", "AAA", ["RP"]))
    report = check_source_realism(rows, game_count=1)
    assert report.blocked is True
    assert any(f.level == BLOCK and "AAA" in f.message and "pitcher" in f.message.lower() for f in report.findings)


def test_moderately_high_pitcher_count_warns_without_blocking():
    rows = _small_realistic_slate()
    for i in range(9):
        rows.append(_row(f"AAA Extra Pitcher {i}", "AAA", ["RP"]))
    report = check_source_realism(rows, game_count=1)
    # 3 + 9 = 12 pitchers for AAA -- at the WARN threshold, below BLOCK.
    assert any(f.level == WARN and "AAA" in f.message for f in report.findings)
    assert not any(f.level == BLOCK and "AAA" in f.message for f in report.findings)


def test_extreme_row_count_relative_to_slate_size_blocks():
    rows = []
    for i in range(60):
        rows.append(_row(f"Hitter {i}", "AAA", ["OF"]))
        rows.append(_row(f"Hitter B {i}", "BBB", ["OF"]))
    report = check_source_realism(rows, game_count=1)
    assert report.blocked is True


def test_team_count_inconsistent_with_game_count_warns():
    rows = _small_realistic_slate()
    rows.append(_row("Third Team Guy", "CCC", ["OF"]))
    report = check_source_realism(rows, game_count=1)  # 1 game implies 2 teams, but 3 present
    assert any(f.level == WARN and "team" in f.message.lower() for f in report.findings)


def test_name_appearing_under_two_teams_is_flagged_as_a_warning():
    # Modeled on the real Max Muncy case: same name, two different teams.
    rows = _small_realistic_slate()
    rows.append(_row("AAA Ace", "BBB", ["SP"], dk_id="different-id"))  # same name as an AAA row, different team
    report = check_source_realism(rows, game_count=1)
    assert any(f.level == WARN and "AAA Ace" in f.message for f in report.findings)


def test_tarik_skubal_style_impossible_source_fixture_is_clearly_synthetic():
    # 30 pitcher-eligible rows salaried for one team in one game, headlined
    # by real-world star names spanning multiple actual organizations --
    # exactly the shape of the real 2026-08-18 LAD rows this milestone
    # investigated. Must be unambiguously blocked, not a borderline WARN.
    rows = []
    for i in range(30):
        rows.append(_row(f"Ace Pitcher {i}", "LAD", ["SP" if i < 15 else "RP"]))
    for i in range(22):
        rows.append(_row(f"Hitter {i}", "LAD", ["OF"]))
    for i in range(20):
        rows.append(_row(f"COL Player {i}", "COL", ["OF"] if i % 2 else ["RP"]))
    report = check_source_realism(rows, game_count=1)
    assert report.blocked is True
    assert any("LAD" in f.message and f.level == BLOCK for f in report.findings)
