"""Validates a Game Environment report's structure before it is
persisted. Mirrors external_projections/validator.py in spirit --
returns a list of human-readable warning strings, never raises, never
silently drops or "fixes" bad data."""

from typing import List

from research.game_environment.models import GameEnvironmentReport, SlateEnvironmentReport


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

    return warnings


def validate_slate_report(report: SlateEnvironmentReport) -> List[str]:
    warnings: List[str] = []
    if not report.games:
        warnings.append("Slate environment report contains zero games.")
    for game in report.games:
        warnings.extend(validate_game_report(game))
    return warnings
