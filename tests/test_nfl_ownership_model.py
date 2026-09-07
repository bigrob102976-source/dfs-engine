"""NFL M12 -- targeted tests for nfl/ownership_model.py: roster-aware
mass (Phase 2), FLEX-aware normalization (Phase 7), player bounds
(Phase 8), and deterministic/reproducible output (Phase 20)."""

import copy

import pytest

from nfl.ownership_model import build_nfl_ownership_projections
from nfl.ownership_models import NflOwnershipInputPlayer

DG_ID = 151307
DATE = "2026-09-13"


def _p(pid, position, salary, projection, ceiling, team="BUF", opponent="HOU", usage_share=None, team_total=None, opp_total=None):
    return NflOwnershipInputPlayer(
        draftkings_player_id=pid, name=f"Player {pid}", position=position, team=team, opponent=opponent,
        salary=salary, projection=projection, ceiling=ceiling, usage_share=usage_share,
        team_implied_total=team_total, opponent_implied_total=opp_total,
    )


def _realistic_slate():
    players = []
    # 2 QBs
    players.append(_p("qb1", "QB", 8000, 22.0, 30.0, team_total=27.5))
    players.append(_p("qb2", "QB", 6200, 17.0, 24.0, team_total=21.0))
    # 6 RBs
    rb_specs = [
        ("rb1", 9000, 20.0, 32.0, 0.65), ("rb2", 7500, 16.0, 26.0, 0.55),
        ("rb3", 6000, 13.0, 22.0, 0.45), ("rb4", 5200, 10.0, 18.0, 0.35),
        ("rb5", 4400, 7.5, 14.0, 0.25), ("rb6", 3800, 5.0, 10.0, 0.15),
    ]
    for pid, sal, proj, ceil, usage in rb_specs:
        players.append(_p(pid, "RB", sal, proj, ceil, usage_share=usage))
    # 8 WRs
    wr_specs = [
        ("wr1", 8800, 19.0, 31.0, 0.28), ("wr2", 7600, 15.5, 26.0, 0.24),
        ("wr3", 6400, 12.5, 21.0, 0.20), ("wr4", 5600, 10.0, 17.0, 0.17),
        ("wr5", 4800, 8.0, 14.0, 0.14), ("wr6", 4200, 6.5, 11.0, 0.11),
        ("wr7", 3600, 5.0, 9.0, 0.08), ("wr8", 3000, 3.5, 7.0, 0.05),
    ]
    for pid, sal, proj, ceil, usage in wr_specs:
        players.append(_p(pid, "WR", sal, proj, ceil, usage_share=usage))
    # 3 TEs
    te_specs = [("te1", 6800, 13.0, 21.0, 0.22), ("te2", 4600, 8.0, 14.0, 0.14), ("te3", 3200, 4.5, 8.0, 0.08)]
    for pid, sal, proj, ceil, usage in te_specs:
        players.append(_p(pid, "TE", sal, proj, ceil, usage_share=usage))
    # 2 DSTs
    players.append(_p("dst1", "DST", 3200, 8.0, 14.0, opp_total=19.0))
    players.append(_p("dst2", "DST", 2600, 6.5, 12.0, opp_total=24.5))
    return players


def _build():
    players = _realistic_slate()
    records, report = build_nfl_ownership_projections(players, DG_ID, DATE, "TEST_PROVENANCE", "2026-09-13T12:00:00Z")
    return records, report


def test_every_ownership_within_bounds():
    records, _ = _build()
    for r in records:
        assert r.ownership_projection is not None
        assert 0.0 <= r.ownership_projection <= 100.0


def test_qb_ownership_sums_to_one_slot():
    records, report = _build()
    qb_sum = sum(r.ownership_projection for r in records if r.position == "QB")
    assert qb_sum == pytest.approx(100.0, abs=1.0)
    assert report["ownership_sum_by_position"]["QB"] == pytest.approx(100.0, abs=1.0)


def test_dst_ownership_sums_to_one_slot():
    records, report = _build()
    dst_sum = sum(r.ownership_projection for r in records if r.position == "DST")
    assert dst_sum == pytest.approx(100.0, abs=1.0)
    assert report["ownership_sum_by_position"]["DST"] == pytest.approx(100.0, abs=1.0)


def test_rb_wr_te_combined_mass_accounts_for_flex():
    """RB (2 slots) + WR (3 slots) + TE (1 slot) + the shared FLEX slot
    (1 slot) together own exactly 7 * 100 = 700% of ownership mass --
    never each position independently normalized to its own base-only
    total (which would only sum to 600%, dropping FLEX's mass
    entirely)."""
    records, _ = _build()
    combined = sum(r.ownership_projection for r in records if r.position in ("RB", "WR", "TE"))
    assert combined == pytest.approx(700.0, abs=2.0)


def test_flex_component_sums_to_flex_slot_mass():
    records, _ = _build()
    flex_total = sum(r.flex_ownership_component for r in records if r.position in ("RB", "WR", "TE"))
    assert flex_total == pytest.approx(100.0, abs=1.0)


def test_flex_component_is_none_for_qb_and_dst():
    records, _ = _build()
    for r in records:
        if r.position in ("QB", "DST"):
            assert r.flex_ownership_component is None


def test_flex_allocation_favors_higher_quality_players_over_flat_split():
    """The FLEX concentration exponent (config/nfl_ownership_config.py)
    should give the best RB/WR/TE meaningfully more FLEX share than the
    weakest ones -- not a flat per-player split."""
    records, _ = _build()
    by_id = {r.draftkings_player_id: r for r in records}
    assert by_id["rb1"].flex_ownership_component > by_id["wr8"].flex_ownership_component
    assert by_id["rb1"].flex_ownership_component > 1.0
    assert by_id["wr8"].flex_ownership_component < 1.0


def test_total_expected_mass_matches_nine_roster_slots():
    _, report = _build()
    assert report["total_expected_mass"] == 900.0


def test_output_is_deterministic_across_repeated_calls():
    players_a = _realistic_slate()
    players_b = copy.deepcopy(_realistic_slate())
    records_a, _ = build_nfl_ownership_projections(players_a, DG_ID, DATE, "TEST_PROVENANCE", "2026-09-13T12:00:00Z")
    records_b, _ = build_nfl_ownership_projections(players_b, DG_ID, DATE, "TEST_PROVENANCE", "2026-09-13T12:00:00Z")
    a_by_id = {r.draftkings_player_id: r.ownership_projection for r in records_a}
    b_by_id = {r.draftkings_player_id: r.ownership_projection for r in records_b}
    assert a_by_id == b_by_id


def test_higher_projection_and_value_player_outranks_lower_within_position():
    records, _ = _build()
    by_id = {r.draftkings_player_id: r for r in records}
    assert by_id["rb1"].ownership_projection > by_id["rb6"].ownership_projection
    assert by_id["wr1"].ownership_projection > by_id["wr8"].ownership_projection


def test_ownership_rank_is_one_indexed_and_unique():
    records, _ = _build()
    ranks = sorted(r.ownership_rank for r in records)
    assert ranks == list(range(1, len(records) + 1))
    top = min(records, key=lambda r: r.ownership_rank)
    assert top.ownership_rank == 1
    assert top.ownership_projection == max(r.ownership_projection for r in records)


def test_method_and_source_are_honestly_labeled_never_implying_trained_ml():
    records, _ = _build()
    for r in records:
        assert r.method == "deterministic_estimator"
        assert r.model_version == "nfl_ownership_v1"
        assert r.source == "BIG_MONEY_NATIVE_OWNERSHIP_V1"


def test_nullable_vegas_never_blocks_ownership():
    """Every player in _realistic_slate() already has team_total/
    opp_total = None except QBs/DSTs -- confirms RB/WR/TE/most positions
    still get a real ownership estimate with zero Vegas signal."""
    records, _ = _build()
    rb_wr_te = [r for r in records if r.position in ("RB", "WR", "TE")]
    assert len(rb_wr_te) == 17
    assert all(r.ownership_projection is not None for r in rb_wr_te)


def test_single_player_position_pool_does_not_crash():
    players = [
        _p("qb1", "QB", 8000, 22.0, 30.0),
        _p("rb1", "RB", 9000, 20.0, 32.0),
        _p("wr1", "WR", 8800, 19.0, 31.0),
        _p("te1", "TE", 6800, 13.0, 21.0),
        _p("dst1", "DST", 3200, 8.0, 14.0),
    ]
    records, _ = build_nfl_ownership_projections(players, DG_ID, DATE, "TEST_PROVENANCE", "2026-09-13T12:00:00Z")
    assert len(records) == 5
    for r in records:
        assert 0.0 <= r.ownership_projection <= 100.0
