"""Orchestrates the full Native Projection Model pipeline for one pitcher --
mirrors hitter_projection.py's structure exactly:

    playing_time.project_pitcher_opportunity  (expected innings/BF/pitch count)
    -> pitcher_rates.project_pitcher_rates     (regressed event rates)
    -> dk_scoring.pitcher_components           (rates * BF/IP -> DK points, per component)
    -> matchup.pitcher_matchup_adjustment       (opposing lineup quality, capped points)
    -> matchup.environment_adjustment           (park / Vegas / weather, capped points)
    -> uncertainty.pitcher_uncertainty          (ceiling / floor / confidence / variance)
    -> models.NativePlayerProjection

`opposing_lineup` is looked up once per slate by the caller from
matchup.build_opposing_lineup_index(all_batter_inputs)[p.opponent] --
this module doesn't build the index itself since it only ever sees one
pitcher at a time.
"""

from datetime import datetime, timezone
from typing import Optional

from models.pitcher import PitcherInput

from native_projections import dk_scoring, matchup, pitcher_rates as pitcher_rates_module, playing_time, uncertainty, validation
from native_projections.matchup import OpposingLineupQuality
from native_projections.models import InputCoverage, NativePlayerProjection
from native_projections.version import NATIVE_PROJECTION_MODEL_VERSION


def _resolve_pitcher_environment(p: PitcherInput, game_report: Optional[dict]) -> dict:
    if not game_report:
        return {}
    is_home = game_report.get("home_team") == p.team
    vegas = game_report.get("vegas") or {}
    weather = game_report.get("weather") or {}
    weather_analysis = game_report.get("weather_analysis") or {}
    ballpark = game_report.get("ballpark") or {}

    conclusions = weather_analysis.get("conclusions") or []
    weather_favors = [c.get("favors") for c in conclusions if isinstance(c, dict) and c.get("favors")]

    return dict(
        park_factor=ballpark.get("park_factor"),
        # The pitcher's own team's implied runs don't affect his DK points
        # (win bonus is postgame-only, see dk_scoring.py) -- the OPPONENT's
        # implied runs are what matter (a tougher run environment against him).
        team_implied_runs=vegas.get("away_implied_runs") if is_home else vegas.get("home_implied_runs"),
        vegas_is_mock=vegas.get("is_mock"),
        weather_favors=weather_favors,
        weather_is_mock=weather.get("is_mock"),
    )


def project_pitcher(
    p: PitcherInput,
    opposing_lineup: Optional[OpposingLineupQuality] = None,
    game_environment: Optional[dict] = None,
    generated_at: Optional[str] = None,
    source_pitcher_snapshot_path: Optional[str] = None,
    source_environment_snapshot_path: Optional[str] = None,
) -> NativePlayerProjection:
    opportunity = playing_time.project_pitcher_opportunity(p)
    rates = pitcher_rates_module.project_pitcher_rates(p)
    components = dk_scoring.pitcher_components(rates, opportunity)
    base_projection = dk_scoring.pitcher_base_projection(components)

    matchup_result = matchup.pitcher_matchup_adjustment(p, opposing_lineup)
    env_inputs = _resolve_pitcher_environment(p, game_environment)
    env_result = matchup.environment_adjustment("pitcher", **env_inputs)

    adjusted_projection = base_projection + matchup_result.points + env_result.points

    completeness_fraction = (
        rates.coverage_fields_available / rates.coverage_fields_total if rates.coverage_fields_total else 0.0
    )
    unc = uncertainty.pitcher_uncertainty(
        rates,
        opportunity,
        adjusted_projection,
        rates.season_opportunities,
        rates.recent_opportunities,
        completeness_fraction,
    )

    coverage = InputCoverage(
        fields_available=rates.coverage_fields_available,
        fields_total=rates.coverage_fields_total,
        missing_fields=list(rates.coverage_missing_fields),
    )
    reasons = list(opportunity.reasons) + list(rates.reasons) + list(matchup_result.reasons) + list(env_result.reasons)

    proj = NativePlayerProjection(
        player_id=p.player_id,
        name=p.name,
        team=p.team,
        player_type="pitcher",
        opponent=p.opponent,
        game_id=p.game_id,
        salary=p.salary,
        positions=["P"],
        batting_order=None,
        native_projection=round(adjusted_projection, 3),
        native_ceiling=unc.ceiling,
        native_floor=unc.floor,
        confidence=unc.confidence,
        variance=unc.variance,
        model_version=NATIVE_PROJECTION_MODEL_VERSION,
        pitcher_opportunity=opportunity,
        pitcher_components=components,
        input_coverage=coverage,
        reasons=reasons,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        source_pitcher_snapshot_path=source_pitcher_snapshot_path,
        source_environment_snapshot_path=source_environment_snapshot_path,
    )
    proj.warnings = validation.validate_projection(proj, rates.season_opportunities)
    return proj
