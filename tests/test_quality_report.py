from models.pitcher import GameContext, OpponentStats, PitcherInput, RecentStats, SeasonStats
from research.quality_report import build_quality_report, render_quality_report


def _full_pitcher(pid="1"):
    return PitcherInput(
        player_id=pid, name=f"Full {pid}", team="AAA", opponent="BBB", salary=8000,
        season=SeasonStats(k_percent=25.0, swinging_strike_percent=11.0, ground_ball_percent=45.0,
                            hard_hit_percent=35.0, barrel_percent=7.0, xera=3.80, xwoba_allowed=0.310),
        recent=RecentStats(k_percent=25.0, csw_percent=28.0, season_velocity=95.0),
        opponent_stats=OpponentStats(strikeout_percent_vs_hand=22.0),
        game=GameContext(weather_pitching_factor=100.0),
    )


def _sparse_pitcher(pid="2"):
    return PitcherInput(player_id=pid, name=f"Sparse {pid}", team="AAA", opponent="BBB")


def test_build_quality_report_counts_total_pitchers():
    report = build_quality_report([_full_pitcher("1"), _sparse_pitcher("2")])
    assert report.total_pitchers == 2


def test_build_quality_report_full_pitcher_populates_every_category():
    report = build_quality_report([_full_pitcher("1")])
    counts = dict(report.rows)
    assert counts["Season Stats"] == 1
    assert counts["Recent Stats"] == 1
    assert counts["Velocity"] == 1
    assert counts["CSW"] == 1
    assert counts["Swinging Strike %"] == 1
    assert counts["Ground Ball %"] == 1
    assert counts["Hard Hit %"] == 1
    assert counts["Barrel %"] == 1
    assert counts["xERA"] == 1
    assert counts["xwOBA"] == 1
    assert counts["Opponent K Rate"] == 1
    assert counts["Weather"] == 1
    assert counts["Salary"] == 1


def test_build_quality_report_sparse_pitcher_populates_nothing():
    report = build_quality_report([_sparse_pitcher("2")])
    counts = dict(report.rows)
    assert all(count == 0 for _, count in report.rows)
    assert counts["Vegas"] == 0


def test_build_quality_report_mixed_slate_makes_gaps_visible():
    report = build_quality_report([_full_pitcher("1"), _full_pitcher("2"), _sparse_pitcher("3")])
    counts = dict(report.rows)
    assert report.total_pitchers == 3
    assert counts["Season Stats"] == 2   # 2 of 3 populated
    assert counts["Weather"] == 2
    assert counts["Vegas"] == 0          # nobody has Vegas data


def test_build_quality_report_empty_slate_does_not_crash():
    report = build_quality_report([])
    assert report.total_pitchers == 0
    assert all(count == 0 for _, count in report.rows)


def test_render_quality_report_includes_every_row_and_denominator():
    report = build_quality_report([_full_pitcher("1"), _sparse_pitcher("2")])
    text = render_quality_report(report)
    assert "RESEARCH QUALITY REPORT" in text
    assert "Pitchers  2 / 2" in text
    for label, count in report.rows:
        assert f"{label}  {count} / 2" in text
