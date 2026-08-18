"""Top-level entry point for the Game Environment Engine (Milestone
DS2): builds a full SlateEnvironmentReport for every game on a slate.

Reads game identity (teams, venue, start time) from the SAME Research
Package every other agent in this project already reads from
(research_output/<date>/games.json via research/adapters/pitcher_input.py)
-- never a second, competing source of truth for "what games are on the
slate today."
"""

from typing import List

from config.game_environment_config import GAME_ENVIRONMENT_ENGINE_VERSION
from research.adapters.pitcher_input import ResearchPackageNotFoundError, load_research_package
from research.game_environment import collector
from research.game_environment.models import GameEnvironmentReport, SlateEnvironmentReport
from research.game_environment.validator import validate_slate_report
from research.game_environment.vegas import analyze_vegas_slate


class GameEnvironmentEngineError(RuntimeError):
    """The engine could not run at all for this date (e.g. no Research
    Package exists yet) -- distinct from a single game's signal being
    unavailable, which degrades that section rather than failing the
    whole report."""


def build_slate_environment_report(slate_date: str, research_output_root: str = "research_output") -> SlateEnvironmentReport:
    try:
        package = load_research_package(research_output_root, slate_date)
    except ResearchPackageNotFoundError as e:
        raise GameEnvironmentEngineError(
            f"No Research Package found for {slate_date} under {research_output_root}/ -- build it first."
        ) from e

    weather_provider, _ = collector.get_configured_weather_provider()
    vegas_provider, _ = collector.get_configured_vegas_provider()
    umpire_provider, _ = collector.get_configured_umpire_provider()
    bullpen_provider, _ = collector.get_configured_bullpen_provider()

    game_reports: List[GameEnvironmentReport] = []
    for g in package["games"]:
        report = collector.build_game_report(
            game_id=g["game_id"], home_team=g["home_team_abbr"], away_team=g["away_team_abbr"],
            game_datetime_utc=g.get("game_datetime_utc"), venue_name=g.get("venue_name"),
            weather_provider=weather_provider, vegas_provider=vegas_provider,
            umpire_provider=umpire_provider, bullpen_provider=bullpen_provider,
            slate_date=slate_date, mlb_game_status=g.get("status"),
        )
        game_reports.append(report)

    vegas_snapshots = [g.vegas for g in game_reports if g.vegas is not None]
    vegas_slate_analysis = analyze_vegas_slate(vegas_snapshots) if vegas_snapshots else None

    report = SlateEnvironmentReport(
        slate_date=slate_date, generated_at=collector.now_iso(), engine_version=GAME_ENVIRONMENT_ENGINE_VERSION,
        games=game_reports, vegas_slate_analysis=vegas_slate_analysis,
    )
    report.warnings = validate_slate_report(report)
    return report
