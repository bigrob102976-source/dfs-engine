import pytest

from agents.pitcher_agent import analyze_pitcher
from models.pitcher import PitcherInput
from research.collector import RawPitcherStats
from research.enrichment import (
    apply_stats_to_pitcher_inputs,
    compute_rate_percent,
    parse_recent_pitching_stats,
    parse_season_pitching_stats,
    parse_team_k_rate,
)

RETRIEVED_AT = "2026-08-11T12:00:00+00:00"


def _season_split(**overrides):
    stat = {
        "battersFaced": 100, "strikeOuts": 30, "baseOnBalls": 10, "earnedRuns": 12,
        "hits": 20, "homeRuns": 3, "hitBatsmen": 2, "era": "3.60", "outs": 75,
        "inningsPitched": "25.0", "numberOfPitches": 400, "gamesStarted": 5,
    }
    stat.update(overrides)
    return {"stats": [{"splits": [{"stat": stat}]}]}


# ----------------------------------------------------------------------------
# compute_rate_percent
# ----------------------------------------------------------------------------


def test_compute_rate_percent_basic():
    assert compute_rate_percent(30, 100) == 30.0


def test_compute_rate_percent_zero_denominator_is_safe():
    assert compute_rate_percent(0, 0) is None
    assert compute_rate_percent(5, 0) is None


# ----------------------------------------------------------------------------
# Season stat parsing
# ----------------------------------------------------------------------------


def test_parse_season_pitching_stats_basic_fields():
    line = parse_season_pitching_stats(_season_split(), "9001", "2026", RETRIEVED_AT)
    assert line is not None
    assert line.player_id == "9001"
    assert line.season == "2026"
    assert line.outs == 75
    assert line.innings_pitched == 25.0  # 75 outs / 3, a whole number here
    assert line.batters_faced == 100
    assert line.strikeouts == 30
    assert line.walks == 10
    assert line.earned_runs == 12
    assert line.era == 3.60
    assert line.retrieved_at == RETRIEVED_AT
    assert line.source == "mlb_stats_api"
    assert line.stat_scope == "season"


def test_parse_season_pitching_stats_k_percent_calculation():
    line = parse_season_pitching_stats(_season_split(strikeOuts=30, battersFaced=100), "9001", "2026", RETRIEVED_AT)
    assert line.k_percent == 30.0  # 30/100, NOT strikeouts/innings


def test_parse_season_pitching_stats_bb_percent_calculation():
    line = parse_season_pitching_stats(_season_split(baseOnBalls=10, battersFaced=100), "9001", "2026", RETRIEVED_AT)
    assert line.bb_percent == 10.0  # 10/100, NOT walks/innings


def test_parse_season_pitching_stats_k_minus_bb_calculation():
    line = parse_season_pitching_stats(
        _season_split(strikeOuts=30, baseOnBalls=10, battersFaced=100), "9001", "2026", RETRIEVED_AT
    )
    assert line.k_percent == 30.0
    assert line.bb_percent == 10.0
    assert line.k_minus_bb_percent == pytest.approx(20.0)


def test_innings_pitched_notation_does_not_corrupt_outs_based_math():
    # "25.0" IP with 75 outs -- if code mistakenly parsed "25.2" as 25.2
    # decimal instead of 25 innings + 2 outs (77 outs), K% would shift.
    line = parse_season_pitching_stats(
        _season_split(inningsPitched="25.2", outs=77, battersFaced=110, strikeOuts=33),
        "9001", "2026", RETRIEVED_AT,
    )
    assert line.outs == 77          # from the authoritative "outs" field, not string-parsed as 25.2
    assert line.innings_pitched == pytest.approx(77 / 3.0, abs=0.001)
    assert line.k_percent == 30.0   # 33/110, unaffected by innings notation either way


def test_fip_without_constant_is_computed_but_never_labeled_official_fip():
    line = parse_season_pitching_stats(
        _season_split(homeRuns=3, baseOnBalls=10, hitBatsmen=2, strikeOuts=30, outs=75, inningsPitched="25.0"),
        "9001", "2026", RETRIEVED_AT,
    )
    # (13*3 + 3*(10+2) - 2*30) / 25 = (39 + 36 - 60) / 25 = 15/25 = 0.6
    assert line.fip_without_constant == pytest.approx(0.6)
    # SeasonStatLine has no "fip" field at all -- it cannot be confused with official FIP.
    assert not hasattr(line, "fip")


def test_parse_season_pitching_stats_zero_batters_faced_is_safe():
    line = parse_season_pitching_stats(_season_split(battersFaced=0, strikeOuts=0, baseOnBalls=0), "9001", "2026", RETRIEVED_AT)
    assert line is not None
    assert line.k_percent is None
    assert line.bb_percent is None
    assert line.k_minus_bb_percent is None


@pytest.mark.parametrize("raw", [None, {}, {"stats": []}, {"stats": [{"splits": []}]}])
def test_parse_season_pitching_stats_handles_missing_data(raw):
    assert parse_season_pitching_stats(raw, "9001", "2026", RETRIEVED_AT) is None


# ----------------------------------------------------------------------------
# Recent form (last 3 starts)
# ----------------------------------------------------------------------------


def _gamelog(splits):
    return {"stats": [{"splits": splits}]}


def _start(outs, bf, k, bb, pitches, started=1, date=None):
    split = {"stat": {"gamesStarted": started, "outs": outs, "battersFaced": bf, "strikeOuts": k, "baseOnBalls": bb, "numberOfPitches": pitches}}
    if date:
        split["date"] = date
    return split


def test_parse_recent_pitching_stats_captures_start_dates_for_statcast_scoping():
    splits = [
        _start(18, 25, 5, 2, 90, date="2026-07-20"),   # oldest, excluded
        _start(20, 27, 7, 2, 100, date="2026-07-25"),  # included
        _start(21, 28, 8, 1, 98, date="2026-07-31"),   # included
        _start(17, 24, 9, 3, 92, date="2026-08-05"),   # included, most recent
    ]
    line = parse_recent_pitching_stats(_gamelog(splits), "9001", "2026", RETRIEVED_AT)
    assert line.start_dates == ["2026-07-25", "2026-07-31", "2026-08-05"]


def test_parse_recent_pitching_stats_uses_only_last_3_starts():
    splits = [
        _start(18, 25, 5, 2, 90),   # oldest, excluded
        _start(19, 26, 6, 1, 95),   # excluded
        _start(20, 27, 7, 2, 100),  # included
        _start(21, 28, 8, 1, 98),   # included
        _start(17, 24, 9, 3, 92),   # included, most recent
    ]
    line = parse_recent_pitching_stats(_gamelog(splits), "9001", "2026", RETRIEVED_AT)

    assert line.starts_used == 3
    assert line.outs == 20 + 21 + 17
    assert line.batters_faced == 27 + 28 + 24
    assert line.strikeouts == 7 + 8 + 9
    assert line.walks == 2 + 1 + 3
    assert line.k_percent == pytest.approx(24 / 79 * 100, abs=0.05)
    assert line.bb_percent == pytest.approx(6 / 79 * 100, abs=0.05)
    assert line.pitch_count_average == pytest.approx((100 + 98 + 92) / 3, abs=0.05)
    assert line.stat_scope == "last_3_starts"


def test_parse_recent_pitching_stats_ignores_relief_appearances():
    splits = [
        _start(20, 27, 7, 2, 100),
        _start(21, 28, 8, 1, 98),
        _start(17, 24, 9, 3, 92),
        {"stat": {"gamesStarted": 0, "outs": 3, "battersFaced": 4, "strikeOuts": 1, "baseOnBalls": 0, "numberOfPitches": 15}},
    ]
    line = parse_recent_pitching_stats(_gamelog(splits), "9001", "2026", RETRIEVED_AT)
    # The relief appearance (gamesStarted=0) is chronologically last but must
    # NOT be one of the "last 3 STARTS".
    assert line.starts_used == 3
    assert line.outs == 20 + 21 + 17


def test_parse_recent_pitching_stats_fewer_than_3_starts_available():
    splits = [_start(18, 25, 5, 2, 90)]
    line = parse_recent_pitching_stats(_gamelog(splits), "9001", "2026", RETRIEVED_AT)
    assert line.starts_used == 1
    assert line.stat_scope == "last_1_starts"


@pytest.mark.parametrize("raw", [None, {}, {"stats": []}])
def test_parse_recent_pitching_stats_handles_missing_data(raw):
    assert parse_recent_pitching_stats(raw, "9001", "2026", RETRIEVED_AT) is None


# ----------------------------------------------------------------------------
# Opponent (team) strikeout rate
# ----------------------------------------------------------------------------


def test_parse_team_k_rate_is_overall_not_handedness_specific():
    raw = {"stats": [{"splits": [{"stat": {"strikeOuts": 900, "plateAppearances": 4500}}]}]}
    line = parse_team_k_rate(raw, "116", "2026", RETRIEVED_AT)
    assert line.k_percent == 20.0
    assert line.split_type == "overall"


def test_parse_team_k_rate_handles_missing_plate_appearances():
    raw = {"stats": [{"splits": [{"stat": {"strikeOuts": 900}}]}]}
    assert parse_team_k_rate(raw, "116", "2026", RETRIEVED_AT) is None


# ----------------------------------------------------------------------------
# Merge into PitcherInput + real-data Pitcher Agent smoke test
# ----------------------------------------------------------------------------


def _bare_pitcher_input(player_id="9001", opponent="OAK"):
    return PitcherInput(player_id=player_id, name="Test Real Pitcher", team="SEA", opponent=opponent, game_id="555")


def test_apply_stats_merges_season_recent_and_opponent_without_inventing_hand_split():
    p = _bare_pitcher_input()
    raw_stats = RawPitcherStats(
        date="2026-08-11",
        season="2026",
        season_pitching={"9001": _season_split()},
        game_log_pitching={"9001": _gamelog([_start(20, 27, 7, 2, 100), _start(21, 28, 8, 1, 98), _start(17, 24, 9, 3, 92)])},
        team_hitting={"117": {"stats": [{"splits": [{"stat": {"strikeOuts": 900, "plateAppearances": 4500}}]}]}},
    )
    enriched, provenance = apply_stats_to_pitcher_inputs([p], raw_stats, {"9001": "117"}, RETRIEVED_AT)

    entry = enriched[0]
    assert entry.season.k_percent == 30.0
    assert entry.season.bb_percent == 10.0
    assert entry.season.era == 3.60
    assert entry.recent.k_percent is not None
    assert entry.opponent_stats.strikeout_percent == 20.0
    assert entry.opponent_stats.strikeout_percent_split_type == "overall"
    # Never fabricate a handedness-specific split from team-overall data.
    assert entry.opponent_stats.strikeout_percent_vs_hand is None

    types = {rec["type"] for rec in provenance}
    assert types == {"season_pitching", "recent_pitching", "opponent_team_k_rate"}
    for rec in provenance:
        assert rec["retrieved_at"] == RETRIEVED_AT
        assert rec["source"] == "mlb_stats_api"


def test_apply_stats_leaves_pitcher_unenriched_when_no_data_available():
    p = _bare_pitcher_input(player_id="9002")
    raw_stats = RawPitcherStats(date="2026-08-11", season="2026")  # nothing fetched for anyone
    enriched, provenance = apply_stats_to_pitcher_inputs([p], raw_stats, {}, RETRIEVED_AT)

    assert enriched[0].season.k_percent is None
    assert enriched[0].recent.k_percent is None
    assert enriched[0].opponent_stats.strikeout_percent is None
    assert provenance == []


def test_real_data_pitcher_agent_smoke_test():
    """A PitcherInput built the way the real pipeline builds it (adapter
    identity + enrichment stats, no Statcast, no salary) must run cleanly
    through the UNCHANGED existing Pitcher Agent and show real signal
    instead of pure neutral fallbacks."""
    p = _bare_pitcher_input()
    raw_stats = RawPitcherStats(
        date="2026-08-11",
        season="2026",
        season_pitching={"9001": _season_split(strikeOuts=35, battersFaced=110, baseOnBalls=8)},
        game_log_pitching={"9001": _gamelog([_start(20, 27, 7, 2, 100), _start(21, 28, 8, 1, 98), _start(17, 24, 9, 3, 92)])},
        team_hitting={"117": {"stats": [{"splits": [{"stat": {"strikeOuts": 900, "plateAppearances": 4500}}]}]}},
    )
    enriched, _ = apply_stats_to_pitcher_inputs([p], raw_stats, {"9001": "117"}, RETRIEVED_AT)

    entry = analyze_pitcher(enriched[0])

    assert entry.player_id == "9001"
    assert entry.salary is None
    assert entry.projection >= 0.0
    # Real season K% should move strikeout_score meaningfully off the neutral 50 fallback.
    assert entry.strikeout_score != 50.0
    # No Statcast/park/weather/Vegas -> confidence must be well below 100,
    # but real season+recent+opponent data should keep it above a
    # fully-sparse pitcher's floor.
    assert 15.0 < entry.confidence < 100.0
    # The auto-generated reason must describe the opponent K% honestly as
    # "overall", never claim a handedness split we don't have.
    assert any("overall" in r for r in entry.reasons)
    assert not any("against right-handed pitching" in r or "against left-handed pitching" in r for r in entry.reasons)
