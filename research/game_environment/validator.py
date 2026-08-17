"""Validates a Game Environment report's structure before it is
persisted. Mirrors external_projections/validator.py in spirit --
returns a list of human-readable warning strings, never raises, never
silently drops or "fixes" bad data.

Milestone 24 adds Vegas-specific sanity checks (game_environment_config
.VEGAS_TOTAL_MIN_PLAUSIBLE/MAX_PLAUSIBLE and the implied-runs
reconciliation check below) -- these run AFTER
providers/implied_runs.py's own validation (which already rejects a
negative split), as a second, independent backstop against ANY VegasSnapshot
ever reaching a saved snapshot with numbers that don't reconcile, not
just ones built through that one code path."""

from typing import List

from config.game_environment_config import VEGAS_TOTAL_MAX_PLAUSIBLE, VEGAS_TOTAL_MIN_PLAUSIBLE
from research.game_environment.models import GameEnvironmentReport, SlateEnvironmentReport, VegasSnapshot

IMPLIED_RUNS_RECONCILIATION_TOLERANCE = 0.05


def validate_vegas_snapshot(vegas: VegasSnapshot) -> List[str]:
    warnings: List[str] = []
    total = vegas.current_home.total

    if total is not None and not (VEGAS_TOTAL_MIN_PLAUSIBLE <= total <= VEGAS_TOTAL_MAX_PLAUSIBLE):
        warnings.append(
            f"Game {vegas.game_id!r}: Vegas total {total} is outside the plausible MLB range "
            f"[{VEGAS_TOTAL_MIN_PLAUSIBLE}, {VEGAS_TOTAL_MAX_PLAUSIBLE}]."
        )

    home_ir = vegas.home_implied_runs
    away_ir = vegas.away_implied_runs
    if home_ir is not None and home_ir < 0:
        warnings.append(f"Game {vegas.game_id!r}: home_implied_runs is negative ({home_ir}).")
    if away_ir is not None and away_ir < 0:
        warnings.append(f"Game {vegas.game_id!r}: away_implied_runs is negative ({away_ir}).")

    if home_ir is not None and away_ir is not None and total is not None:
        combined = home_ir + away_ir
        if abs(combined - total) > IMPLIED_RUNS_RECONCILIATION_TOLERANCE:
            warnings.append(
                f"Game {vegas.game_id!r}: home_implied_runs ({home_ir}) + away_implied_runs ({away_ir}) "
                f"= {combined:.2f}, which does not reconcile with the game total ({total}) -- "
                f"components do not add up, flagging rather than silently accepting."
            )

    if not vegas.implied_runs_is_valid and (home_ir is not None or away_ir is not None):
        warnings.append(
            f"Game {vegas.game_id!r}: implied_runs_is_valid is False but implied runs are still populated -- "
            f"an invalid calculation must never be silently presented as valid."
        )

    return warnings


def validate_game_report(game: GameEnvironmentReport) -> List[str]:
    warnings: List[str] = []

    if not game.game_id:
        warnings.append("Game report is missing game_id.")
    if not game.home_team or not game.away_team:
        warnings.append(f"Game {game.game_id!r} is missing home_team/away_team.")

    score = game.environment_score
    for label, value in (("overall", score.overall), ("pitcher", score.pitcher), ("hitter", score.hitter), ("stack", score.stack)):
        if value is None or not (0.0 <= value <= 100.0):
            warnings.append(f"Game {game.game_id!r} has an out-of-range {label} environment score: {value!r}.")

    if game.umpire is not None and game.umpire.status not in ("KNOWN", "UNKNOWN"):
        warnings.append(f"Game {game.game_id!r} has an unrecognized umpire status: {game.umpire.status!r}.")

    if not game.summary.headline:
        warnings.append(f"Game {game.game_id!r} is missing a summary headline.")

    if game.vegas is not None:
        warnings.extend(validate_vegas_snapshot(game.vegas))

    return warnings


def validate_slate_report(report: SlateEnvironmentReport) -> List[str]:
    warnings: List[str] = []
    if not report.games:
        warnings.append("Slate environment report contains zero games.")
    for game in report.games:
        warnings.extend(validate_game_report(game))
    return warnings
