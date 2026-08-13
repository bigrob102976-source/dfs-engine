import pytest

from config.dk_roster_config import DK_CLASSIC_SALARY_CAP
from config.optimizer_config import OPTIMIZER_VERSION
from optimizer.lineup_generator import generate_lineups
from optimizer.models import OptimizerSettings
from tests._optimizer_fixtures import feasible_pool


def test_optimizer_version_is_set():
    assert OPTIMIZER_VERSION == "0.1.0"


def test_optimizer_settings_to_dict_round_trips_key_fields():
    settings = OptimizerSettings(objective_mode="balanced", num_lineups=5, locks=["A"], excludes=["B"])
    d = settings.to_dict()
    assert d["objective_mode"] == "balanced"
    assert d["num_lineups"] == 5
    assert d["locks"] == ["A"]
    assert d["excludes"] == ["B"]


def test_lineup_metrics_are_computed_correctly():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1))
    lineup = out.result.lineups[0]

    assert lineup.salary == sum(a.salary for a in lineup.assignments)
    assert lineup.remaining_salary == DK_CLASSIC_SALARY_CAP - lineup.salary
    assert lineup.projection == pytest.approx(sum(a.projection for a in lineup.assignments), abs=0.01)
    assert lineup.ceiling == pytest.approx(sum(a.ceiling for a in lineup.assignments), abs=0.01)
    risks = [a.risk_score for a in lineup.assignments if a.risk_score is not None]
    assert lineup.average_risk == pytest.approx(sum(risks) / len(risks), abs=0.01)
    confidences = [a.confidence for a in lineup.assignments if a.confidence is not None]
    assert lineup.average_confidence == pytest.approx(sum(confidences) / len(confidences), abs=0.01)

    total_from_team_counts = sum(lineup.team_counts.values())
    assert total_from_team_counts == 10


def test_primary_stack_reflects_hitters_only():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1, stack_size=5, stack_team="PHI"))
    lineup = out.result.lineups[0]
    assert lineup.primary_stack_team == "PHI"
    assert lineup.primary_stack_size == lineup.team_counts.get("PHI")  # no PHI pitcher exists in the pool


def test_lineup_to_dict_serializes_assignments():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1))
    lineup = out.result.lineups[0]
    d = lineup.to_dict()
    assert len(d["assignments"]) == 10
    assert "salary" in d and "projection" in d and "primary_stack_team" in d


def test_player_keys_matches_assignment_count():
    players = feasible_pool()
    out = generate_lineups(players, OptimizerSettings(num_lineups=1))
    lineup = out.result.lineups[0]
    assert len(lineup.player_keys()) == 10
    assert len(set(lineup.player_keys())) == 10
