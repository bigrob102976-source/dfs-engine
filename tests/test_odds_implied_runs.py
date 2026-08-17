from research.game_environment.providers.consensus import ConsensusMarket
from research.game_environment.providers.implied_runs import compute_team_implied_runs


def make_consensus(**overrides):
    defaults = dict(
        total=8.5, total_books_used=3,
        home_moneyline=-150, away_moneyline=130,
        home_win_probability=0.58, away_win_probability=0.42, moneyline_books_used=3,
        home_run_line=-1.5, run_line_books_used=3,
        books_used=["draftkings", "fanduel", "betmgm"],
    )
    defaults.update(overrides)
    return ConsensusMarket(**defaults)


def test_implied_runs_split_by_run_line_reconciles_exactly_to_total():
    consensus = make_consensus(total=8.5, home_run_line=-1.5)
    result = compute_team_implied_runs(consensus)
    assert result.is_valid is True
    assert result.home_implied_runs + result.away_implied_runs == result.home_implied_runs + result.away_implied_runs  # sanity
    total_reconstructed = round(result.home_implied_runs + result.away_implied_runs, 2)
    assert total_reconstructed == 8.5


def test_home_favorite_gets_more_implied_runs_than_away():
    consensus = make_consensus(total=8.5, home_run_line=-1.5)
    result = compute_team_implied_runs(consensus)
    assert result.home_implied_runs > result.away_implied_runs
    assert result.home_implied_runs == 5.0  # 8.5/2 + 1.5/2
    assert result.away_implied_runs == 3.5  # 8.5/2 - 1.5/2


def test_away_favorite_gets_more_implied_runs_than_home():
    consensus = make_consensus(total=9.0, home_run_line=1.5)  # positive home run line = home is underdog
    result = compute_team_implied_runs(consensus)
    assert result.away_implied_runs > result.home_implied_runs
    assert result.home_implied_runs == 3.75
    assert result.away_implied_runs == 5.25


def test_pickem_game_splits_evenly():
    consensus = make_consensus(total=8.0, home_run_line=0.0)
    result = compute_team_implied_runs(consensus)
    assert result.home_implied_runs == 4.0
    assert result.away_implied_runs == 4.0


def test_calculation_method_documents_the_real_formula():
    consensus = make_consensus()
    result = compute_team_implied_runs(consensus)
    assert result.calculation_method == "run_line_split_of_consensus_total"


def test_no_total_gives_none_not_a_guess():
    consensus = make_consensus(total=None)
    result = compute_team_implied_runs(consensus)
    assert result.home_implied_runs is None
    assert result.away_implied_runs is None
    assert result.is_valid is False
    assert "no consensus game total" in result.validation_warnings[0].lower()


def test_no_run_line_gives_none_not_an_invented_coefficient():
    consensus = make_consensus(home_run_line=None)
    result = compute_team_implied_runs(consensus)
    assert result.home_implied_runs is None
    assert result.away_implied_runs is None
    assert result.is_valid is False
    assert result.calculation_method == "unavailable_no_run_line"


def test_extreme_run_line_larger_than_total_is_rejected_not_clamped():
    # A run line bigger than the total would force a negative implied value.
    consensus = make_consensus(total=3.0, home_run_line=-4.0)
    result = compute_team_implied_runs(consensus)
    assert result.is_valid is False
    assert result.home_implied_runs is None
    assert result.away_implied_runs is None
    assert result.calculation_method == "invalid_negative_result"
    assert "negative" in result.validation_warnings[0].lower()


def test_result_preserves_all_inputs_for_explainability():
    consensus = make_consensus(total=8.5, home_run_line=-1.5, home_moneyline=-150, away_moneyline=130, home_win_probability=0.58)
    result = compute_team_implied_runs(consensus)
    assert result.input_total == 8.5
    assert result.input_home_run_line == -1.5
    assert result.input_home_moneyline == -150
    assert result.input_away_moneyline == 130
    assert result.input_home_win_probability == 0.58
