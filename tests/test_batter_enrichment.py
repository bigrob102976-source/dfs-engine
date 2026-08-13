import pytest

from models.batter import BatterInput
from research.collector import RawBatterStats
from research.batter_enrichment import (
    apply_bios_to_batter_inputs,
    apply_stats_to_batter_inputs,
    compute_rate_percent,
    parse_platoon_split,
    parse_recent_batting_stats,
    parse_season_batting_stats,
)

RETRIEVED_AT = "2026-08-11T12:00:00+00:00"


def _season_split(**overrides):
    stat = {
        "plateAppearances": 200, "atBats": 175, "hits": 50, "doubles": 10, "triples": 1,
        "homeRuns": 8, "baseOnBalls": 20, "strikeOuts": 40, "stolenBases": 3,
        "avg": ".286", "obp": ".360", "slg": ".480", "ops": ".840",
    }
    stat.update(overrides)
    return {"stats": [{"splits": [{"stat": stat}]}]}


def _gamelog(splits):
    return {"stats": [{"splits": splits}]}


def _game(date, pa, k, bb):
    return {"date": date, "stat": {"plateAppearances": pa, "strikeOuts": k, "baseOnBalls": bb}}


# ----------------------------------------------------------------------------
# Season parsing: K%, BB%, ISO
# ----------------------------------------------------------------------------


def test_parse_season_batting_stats_k_percent_uses_plate_appearances():
    line = parse_season_batting_stats(_season_split(strikeOuts=40, plateAppearances=200), "1", "2026", RETRIEVED_AT)
    assert line.k_percent == 20.0  # 40/200, NOT strikeouts/AB


def test_parse_season_batting_stats_bb_percent_uses_plate_appearances():
    line = parse_season_batting_stats(_season_split(baseOnBalls=20, plateAppearances=200), "1", "2026", RETRIEVED_AT)
    assert line.bb_percent == 10.0


def test_parse_season_batting_stats_iso_is_slg_minus_avg():
    line = parse_season_batting_stats(_season_split(avg=".286", slg=".480"), "1", "2026", RETRIEVED_AT)
    assert line.iso == pytest.approx(0.194, abs=0.001)


def test_parse_season_batting_stats_basic_fields():
    line = parse_season_batting_stats(_season_split(), "1", "2026", RETRIEVED_AT)
    assert line.plate_appearances == 200
    assert line.hits == 50
    assert line.doubles == 10
    assert line.home_runs == 8
    assert line.stolen_bases == 3
    assert line.avg == 0.286


def test_compute_rate_percent_zero_denominator_is_safe():
    assert compute_rate_percent(5, 0) is None
    assert compute_rate_percent(0, None) is None


@pytest.mark.parametrize("raw", [None, {}, {"stats": []}, {"stats": [{"splits": []}]}])
def test_parse_season_batting_stats_handles_missing_data(raw):
    assert parse_season_batting_stats(raw, "1", "2026", RETRIEVED_AT) is None


# ----------------------------------------------------------------------------
# Recent form (last 14 days)
# ----------------------------------------------------------------------------


def test_parse_recent_batting_stats_uses_only_last_14_days():
    splits = [
        _game("2026-07-20", 4, 1, 0),  # 22 days before reference -- excluded
        _game("2026-07-29", 5, 2, 1),  # 13 days before -- included
        _game("2026-08-05", 4, 0, 2),  # 6 days before -- included
        _game("2026-08-10", 5, 1, 0),  # 1 day before -- included
    ]
    line = parse_recent_batting_stats(_gamelog(splits), "1", "2026", RETRIEVED_AT, reference_date="2026-08-11")
    assert line.games_sampled == 3
    assert line.plate_appearances == 5 + 4 + 5
    assert line.strikeouts == 2 + 0 + 1
    assert line.walks == 1 + 2 + 0


def test_parse_recent_batting_stats_k_and_bb_percent():
    splits = [_game("2026-08-05", 20, 5, 2)]
    line = parse_recent_batting_stats(_gamelog(splits), "1", "2026", RETRIEVED_AT, reference_date="2026-08-11")
    assert line.k_percent == 25.0
    assert line.bb_percent == 10.0


def test_parse_recent_batting_stats_excludes_game_on_reference_date_itself():
    # window is [reference-14, reference) -- a game ON the reference date
    # (e.g. today's own game, if any) is not "recent form" relative to itself.
    splits = [_game("2026-08-11", 4, 1, 0)]
    line = parse_recent_batting_stats(_gamelog(splits), "1", "2026", RETRIEVED_AT, reference_date="2026-08-11")
    assert line is None


@pytest.mark.parametrize("raw", [None, {}, {"stats": []}])
def test_parse_recent_batting_stats_handles_missing_data(raw):
    assert parse_recent_batting_stats(raw, "1", "2026", RETRIEVED_AT, reference_date="2026-08-11") is None


# ----------------------------------------------------------------------------
# Platoon splits
# ----------------------------------------------------------------------------


def test_parse_platoon_split_labels_split_type_correctly():
    raw = _season_split()
    line = parse_platoon_split(raw, "1", "2026", "vr", RETRIEVED_AT)
    assert line.sit_code == "vr"
    assert line.k_percent == 20.0
    assert line.woba is not None  # approximated from real counting stats


def test_parse_platoon_split_woba_approximation_uses_real_counting_stats():
    # Hand-computable: singles = 50-10-1-8 = 31. Weights: bb .69, hbp .72,
    # 1b .89, 2b 1.27, 3b 1.62, hr 2.10. denom = AB+BB-IBB+SF+HBP.
    raw = _season_split(atBats=175, baseOnBalls=20, intentionalWalks=0, hitByPitch=0, sacFlies=0, hits=50, doubles=10, triples=1, homeRuns=8)
    line = parse_platoon_split(raw, "1", "2026", "vl", RETRIEVED_AT)
    numerator = 0.69 * 20 + 0.89 * 31 + 1.27 * 10 + 1.62 * 1 + 2.10 * 8
    denominator = 175 + 20
    assert line.woba == pytest.approx(round(numerator / denominator, 3))


def test_parse_platoon_split_missing_data():
    assert parse_platoon_split(None, "1", "2026", "vr", RETRIEVED_AT) is None


# ----------------------------------------------------------------------------
# Merge into BatterInput
# ----------------------------------------------------------------------------


def test_apply_stats_merges_season_recent_and_platoon():
    raw = RawBatterStats(
        date="2026-08-11", season="2026",
        season_hitting={"1": _season_split()},
        game_log_hitting={"1": _gamelog([_game("2026-08-05", 20, 5, 2)])},
        platoon_vs_rhp={"1": _season_split(avg=".300")},
        platoon_vs_lhp={"1": _season_split(avg=".220")},
    )
    p = BatterInput(player_id="1", name="Test", team="AAA", opponent="BBB")
    enriched, provenance = apply_stats_to_batter_inputs([p], raw, "2026-08-11", RETRIEVED_AT)

    e = enriched[0]
    assert e.season.k_percent == 20.0
    assert e.recent.plate_appearances == 20
    assert e.vs_rhp.split_type == "vs_hand"
    assert e.vs_lhp.split_type == "vs_hand"
    assert e.vs_rhp.iso != e.vs_lhp.iso  # distinct real per-side data, never conflated

    types = {r["type"] for r in provenance}
    assert types == {"season_batting", "recent_batting", "platoon_vs_rhp", "platoon_vs_lhp"}


def test_apply_stats_leaves_batter_unenriched_when_no_data_available():
    raw = RawBatterStats(date="2026-08-11", season="2026")
    p = BatterInput(player_id="2", name="Nobody", team="AAA", opponent="BBB")
    enriched, provenance = apply_stats_to_batter_inputs([p], raw, "2026-08-11", RETRIEVED_AT)

    assert enriched[0].season.k_percent is None
    assert enriched[0].recent.plate_appearances is None
    assert provenance == []


def test_apply_bios_sets_batting_hand_without_network():
    p = BatterInput(player_id="1", name="Test", team="AAA", opponent="BBB")
    people = {"1": {"batSide": {"code": "L"}}}
    enriched = apply_bios_to_batter_inputs([p], people)
    assert enriched[0].batting_hand == "L"


def test_apply_bios_leaves_batting_hand_none_when_missing():
    p = BatterInput(player_id="1", name="Test", team="AAA", opponent="BBB")
    enriched = apply_bios_to_batter_inputs([p], {})
    assert enriched[0].batting_hand is None
