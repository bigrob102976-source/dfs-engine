"""Team implied runs (Milestone 24) -- CRITICAL, fully explainable
methodology.

This is deliberately NOT "game total / 2" (that ignores which team is
favored entirely, and the milestone explicitly forbids it) and
deliberately NOT the pre-M24 mock provider's old formula
(`total * (0.5 + (home_win_prob - 0.5) * 0.3)` -- see
research/game_environment/vegas.py's git history) -- that 0.3 dampening
constant was never sourced from anything real, and re-auditing it during
this milestone is the most likely explanation for the reported
Dodgers-implied-runs discrepancy this milestone was opened to
investigate (see the milestone's final report for the live comparison
against real SportsGameOdds data).

--------------------------------------------------------------------------
METHOD: split the consensus TOTAL by the consensus RUN LINE's own margin
--------------------------------------------------------------------------
The run line already IS the market's own stated expected scoring MARGIN
between the two teams (e.g. a home run line of -1.5 means the market
expects the home team to win by 1.5 runs). Splitting the total around
that real, already-published margin needs no invented coefficient at
all:

    margin_home = -consensus_run_line_home
    home_implied_runs = consensus_total / 2 + margin_home / 2
    away_implied_runs = consensus_total / 2 - margin_home / 2

By construction, home_implied_runs + away_implied_runs ==
consensus_total EXACTLY (not merely "approximately") whenever both
inputs are present -- this is a hard algebraic identity of the formula
above, not a coincidence that needs separate reconciliation checking (a
reconciliation check still exists in validator.py as a defensive
backstop for any future code path that might set these fields a
different way).

The consensus no-vig win probabilities (consensus.py) are always
reported alongside this result for context/display, but are NOT used to
derive the split -- using both the run line AND independently deriving
a second, moneyline-based split would risk the two disagreeing with no
way to reconcile them; the run line is the more direct signal for a
scoring MARGIN specifically (moneyline encodes WIN probability, a
different, nonlinear quantity), so it alone is the split's input.

--------------------------------------------------------------------------
No run line available
--------------------------------------------------------------------------
If no book returned a run line, implied runs are NOT computed --
`home_implied_runs`/`away_implied_runs` are None, with `calculation_method`
explaining why. This project does not fall back to an uncited,
hand-calibrated probability-to-margin coefficient (see CLAUDE.md's "AI
should NOT invent statistics").
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional

from research.game_environment.providers.consensus import ConsensusMarket


@dataclass
class ImpliedRunsResult:
    home_implied_runs: Optional[float]
    away_implied_runs: Optional[float]
    calculation_method: str
    input_total: Optional[float]
    input_home_run_line: Optional[float]
    input_home_moneyline: Optional[int]
    input_away_moneyline: Optional[int]
    input_home_win_probability: Optional[float]
    input_away_win_probability: Optional[float]
    is_valid: bool
    validation_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def compute_team_implied_runs(consensus: ConsensusMarket) -> ImpliedRunsResult:
    common_inputs = dict(
        input_total=consensus.total,
        input_home_run_line=consensus.home_run_line,
        input_home_moneyline=consensus.home_moneyline,
        input_away_moneyline=consensus.away_moneyline,
        input_home_win_probability=consensus.home_win_probability,
        input_away_win_probability=consensus.away_win_probability,
    )

    if consensus.total is None:
        return ImpliedRunsResult(
            home_implied_runs=None,
            away_implied_runs=None,
            calculation_method="unavailable_no_consensus_total",
            is_valid=False,
            validation_warnings=["No consensus game total available -- cannot compute implied runs."],
            **common_inputs,
        )

    if consensus.home_run_line is None:
        return ImpliedRunsResult(
            home_implied_runs=None,
            away_implied_runs=None,
            calculation_method="unavailable_no_run_line",
            is_valid=False,
            validation_warnings=[
                "No consensus run line available -- implied runs require a real market-provided margin, "
                "not an invented one (see this module's docstring)."
            ],
            **common_inputs,
        )

    margin_home = -consensus.home_run_line
    home_implied = round(consensus.total / 2.0 + margin_home / 2.0, 2)
    away_implied = round(consensus.total / 2.0 - margin_home / 2.0, 2)

    if home_implied < 0 or away_implied < 0:
        return ImpliedRunsResult(
            home_implied_runs=None,
            away_implied_runs=None,
            calculation_method="invalid_negative_result",
            is_valid=False,
            validation_warnings=[
                f"Run-line split produced a negative implied-runs value (home={home_implied}, away={away_implied}) "
                f"from total={consensus.total}, home_run_line={consensus.home_run_line} -- rejected rather than clamped."
            ],
            **common_inputs,
        )

    return ImpliedRunsResult(
        home_implied_runs=home_implied,
        away_implied_runs=away_implied,
        calculation_method="run_line_split_of_consensus_total",
        is_valid=True,
        validation_warnings=[],
        **common_inputs,
    )
