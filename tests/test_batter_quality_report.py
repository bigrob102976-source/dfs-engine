from models.batter import BatterInput, OpposingPitcherContext, PlatoonSplitStats, RecentBattingStats, SeasonBattingStats
from research.quality_report import batter_data_status, build_batter_quality_report, render_batter_quality_report


def _full_batter(pid="1"):
    return BatterInput(
        player_id=pid, name=f"Full {pid}", team="AAA", opponent="BBB", batting_order=3, salary=5000,
        season=SeasonBattingStats(k_percent=20.0, xwoba=0.340, xslg=0.460, hard_hit_percent=40.0, barrel_percent=8.0),
        recent=RecentBattingStats(plate_appearances=45),
        vs_rhp=PlatoonSplitStats(woba=0.340),
        opposing_pitcher=OpposingPitcherContext(player_id="999"),
    )


def _sparse_batter(pid="2"):
    return BatterInput(player_id=pid, name=f"Sparse {pid}", team="AAA", opponent="BBB")


def test_build_batter_quality_report_counts_total_hitters():
    report = build_batter_quality_report([_full_batter("1"), _sparse_batter("2")])
    assert report.total_hitters == 2


def test_full_batter_populates_every_category():
    report = build_batter_quality_report([_full_batter()])
    counts = dict(report.rows)
    assert counts["Season Batting Stats"] == 1
    assert counts["xwOBA"] == 1
    assert counts["xSLG"] == 1
    assert counts["Hard Hit"] == 1
    assert counts["Barrel"] == 1
    assert counts["Recent Data"] == 1
    assert counts["Platoon Splits"] == 1
    assert counts["Batting Order"] == 1
    assert counts["Opposing Pitcher Context"] == 1
    assert counts["Salary"] == 1


def test_sparse_batter_populates_nothing():
    report = build_batter_quality_report([_sparse_batter()])
    counts = dict(report.rows)
    assert all(count == 0 for _, count in report.rows)
    assert counts["Weather"] == 0
    assert counts["Vegas"] == 0


def test_weather_and_vegas_always_zero_by_design():
    report = build_batter_quality_report([_full_batter()])
    counts = dict(report.rows)
    assert counts["Weather"] == 0
    assert counts["Vegas"] == 0


def test_batter_data_status_matches_quality_report_predicates():
    b = _full_batter()
    status = batter_data_status(b)
    assert status["Season Batting Stats"] is True
    assert status["Weather"] is False


def test_render_batter_quality_report_includes_every_row():
    report = build_batter_quality_report([_full_batter(), _sparse_batter()])
    text = render_batter_quality_report(report)
    assert "RESEARCH QUALITY REPORT (Hitters)" in text
    assert "Starting Hitters  2 / 2" in text
    for label, count in report.rows:
        assert f"{label}  {count} / 2" in text


def test_empty_slate_does_not_crash():
    report = build_batter_quality_report([])
    assert report.total_hitters == 0
    assert all(count == 0 for _, count in report.rows)
