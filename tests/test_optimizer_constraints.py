import pytest

from optimizer.constraints import (
    OptimizerConfigError,
    compute_exposure_count_caps,
    compute_min_exposure_targets,
    explain_infeasibility,
    filter_eligible_players,
    hitters_by_team,
    pitcher_vs_hitter_conflicts,
    resolve_player_by_name,
    resolve_settings,
)
from optimizer.models import OptimizerSettings
from tests._optimizer_fixtures import feasible_pool, hitter, pitcher


def test_filter_min_confidence_excludes_below_threshold():
    players = feasible_pool()
    settings = OptimizerSettings(min_confidence=92.0)
    eligible = filter_eligible_players(players, settings)
    assert all(p.confidence >= 92.0 for p in eligible)
    assert len(eligible) < len(players)


def test_filter_min_season_pa_only_applies_to_hitters():
    players = feasible_pool()
    tiny_sample = hitter("tiny", "ZZZ", ["OF"], 2000, 3.0, season_pa=4)
    players = players + [tiny_sample]
    settings = OptimizerSettings(min_season_pa=50)
    eligible = filter_eligible_players(players, settings)
    assert "tiny" not in {p.key for p in eligible}
    # Pitchers (season_sample_size=None) are never filtered by this rule.
    assert any(p.player_type == "pitcher" for p in eligible)


def test_filter_max_player_risk_excludes_above_threshold():
    players = feasible_pool()
    settings = OptimizerSettings(max_player_risk=26.0)
    eligible = filter_eligible_players(players, settings)
    assert all(p.risk_score is None or p.risk_score <= 26.0 for p in eligible)


def test_resolve_player_by_name_exact():
    players = feasible_pool()
    p = resolve_player_by_name(players, "Phi C")
    assert p.key == "phi_c"


def test_resolve_player_by_name_not_found_raises():
    players = feasible_pool()
    with pytest.raises(OptimizerConfigError):
        resolve_player_by_name(players, "Nobody Real")


def test_resolve_player_by_name_ambiguous_raises():
    players = feasible_pool() + [hitter("dupe1", "AAA", ["OF"], 2000, 5.0), hitter("dupe2", "BBB", ["OF"], 2000, 5.0)]
    players[-1].name = "Same Name"
    players[-2].name = "Same Name"
    with pytest.raises(OptimizerConfigError):
        resolve_player_by_name(players, "Same Name")


class TestRealDuplicateNameDisambiguation:
    """MLB WORKFLOW QA: confirmed live 2026-09-03 -- two real, different,
    active MLB players can genuinely share a name on the same real slate
    (two "Max Muncy"s, ATH and LAD). A bare name is still honestly
    rejected as ambiguous (never guessed), but the "Name (TEAM)" format
    the error message itself suggests must actually resolve -- this is
    what lets the web UI (OptimizerWorkspace.tsx's buildRequestBody)
    disambiguate automatically without a second round trip."""

    def _duplicate_named_pool(self):
        players = feasible_pool() + [
            hitter("dupe1", "AAA", ["OF"], 2000, 5.0),
            hitter("dupe2", "BBB", ["OF"], 2000, 5.0),
        ]
        players[-1].name = "Same Name"
        players[-2].name = "Same Name"
        return players

    def test_team_suffix_resolves_the_specific_player(self):
        players = self._duplicate_named_pool()
        p = resolve_player_by_name(players, "Same Name (AAA)")
        assert p.key == "dupe1"
        p2 = resolve_player_by_name(players, "Same Name (BBB)")
        assert p2.key == "dupe2"

    def test_team_suffix_is_case_insensitive_on_team(self):
        players = self._duplicate_named_pool()
        p = resolve_player_by_name(players, "Same Name (aaa)")
        assert p.key == "dupe1"

    def test_nonexistent_team_suffix_falls_through_to_ambiguous_error(self):
        players = self._duplicate_named_pool()
        with pytest.raises(OptimizerConfigError, match="matches more than one active player"):
            resolve_player_by_name(players, "Same Name (ZZZ)")

    def test_a_name_with_no_collision_is_unaffected_by_a_team_suffix_format(self):
        players = feasible_pool()
        # "Phi C" has no collision -- exact bare-name resolution (the
        # overwhelming common case) must stay byte-for-byte unchanged.
        p = resolve_player_by_name(players, "Phi C")
        assert p.key == "phi_c"


def test_resolve_settings_lock_and_exclude_conflict_raises():
    players = feasible_pool()
    settings = OptimizerSettings(locks=["Phi C"], excludes=["Phi C"])
    with pytest.raises(OptimizerConfigError):
        resolve_settings(players, settings)


def test_resolve_settings_too_many_locks_raises():
    players = feasible_pool()
    all_names = [p.name for p in players][:11]
    settings = OptimizerSettings(locks=all_names)
    with pytest.raises(OptimizerConfigError):
        resolve_settings(players, settings)


def test_resolve_settings_locked_player_filtered_out_raises():
    players = feasible_pool()
    settings = OptimizerSettings(locks=["Phi C"], min_confidence=999.0)  # filters everyone out
    with pytest.raises(OptimizerConfigError):
        resolve_settings(players, settings)


def test_resolve_settings_max_exposure_below_one_conflicts_with_lock():
    players = feasible_pool()
    settings = OptimizerSettings(locks=["Phi C"], max_exposure={"Phi C": 0.5})
    with pytest.raises(OptimizerConfigError):
        resolve_settings(players, settings)


def test_resolve_settings_invalid_exposure_fraction_raises():
    players = feasible_pool()
    settings = OptimizerSettings(max_exposure={"Phi C": 1.5})
    with pytest.raises(OptimizerConfigError):
        resolve_settings(players, settings)


def test_resolve_settings_happy_path_returns_resolved_keys():
    players = feasible_pool()
    settings = OptimizerSettings(locks=["Phi C"], excludes=["Nyy C"], max_exposure={"Phi 1B": 0.5})
    eligible, locked, excluded, max_exp, min_exp = resolve_settings(players, settings)
    assert "phi_c" in locked
    assert "nyy_c" in excluded
    assert max_exp["phi_1b"] == 0.5


def test_compute_exposure_count_caps_default_and_override():
    caps = compute_exposure_count_caps({"a": 0.5}, 1.0, 20, ["a", "b"])
    assert caps["a"] == 10
    assert caps["b"] == 20  # default 1.0 -> unrestricted


def test_compute_min_exposure_targets_rounds_up():
    targets = compute_min_exposure_targets({"a": 0.1}, 15)
    assert targets["a"] == 2  # ceil(1.5)


class TestExposureRoundingDeterminism:
    """Phase 11: one deterministic rounding rule -- max exposure FLOORS,
    min exposure CEILS -- verified against IEEE-754 float multiplication
    ambiguity, not just the "nice" cases. 0.58 * 50 is exactly 29 in real
    arithmetic but floats to 28.999999999999996 in float64; a bare
    int(fraction * num_lineups) would silently under-allow by one lineup
    (see optimizer/constraints.py's _EXPOSURE_ROUNDING_EPSILON)."""

    def test_20_lineups_at_25_percent_allows_5(self):
        caps = compute_exposure_count_caps({"a": 0.25}, 1.0, 20, ["a"])
        assert caps["a"] == 5

    def test_5_lineups_at_25_percent_allows_1(self):
        caps = compute_exposure_count_caps({"a": 0.25}, 1.0, 5, ["a"])
        assert caps["a"] == 1

    def test_3_lineups_at_50_percent_allows_1(self):
        caps = compute_exposure_count_caps({"a": 0.5}, 1.0, 3, ["a"])
        assert caps["a"] == 1

    def test_max_exposure_floors_on_a_float_boundary_that_rounds_down_in_binary(self):
        # 0.58 * 50 == 29 exactly in real arithmetic; float64 computes
        # 28.999999999999996. A naive int() would wrongly cap at 28.
        caps = compute_exposure_count_caps({"a": 0.58}, 1.0, 50, ["a"])
        assert caps["a"] == 29

    def test_min_exposure_ceils_on_a_float_boundary_that_rounds_up_in_binary(self):
        # 0.14 * 50 == 7 exactly in real arithmetic; float64 computes
        # 7.000000000000001. A naive math.ceil() would wrongly require 8.
        targets = compute_min_exposure_targets({"a": 0.14}, 50)
        assert targets["a"] == 7


def test_pitcher_vs_hitter_conflicts_detected():
    players = feasible_pool()
    conflicts = pitcher_vs_hitter_conflicts(players)
    assert conflicts.get("p_tor") == ["conflict_hitter"]


def test_hitters_by_team_excludes_pitchers():
    players = feasible_pool()
    grouped = hitters_by_team(players)
    assert "TOR" not in grouped or all(p.player_type == "hitter" for p in grouped.get("TOR", []))
    assert len(grouped["PHI"]) == 7


def test_explain_infeasibility_reports_missing_position():
    players = [p for p in feasible_pool() if p.key not in ("phi_c", "nyy_c")]
    settings = OptimizerSettings()
    reasons = explain_infeasibility(players, settings)
    assert any("C" in r for r in reasons)


def test_explain_infeasibility_reports_impossible_stack():
    players = feasible_pool()
    settings = OptimizerSettings(stack_size=20)
    reasons = explain_infeasibility(players, settings)
    assert any("stack" in r.lower() for r in reasons)
