"""Orchestrates the full Native Projection Model pipeline for one hitter:

    playing_time.project_hitter_opportunity   (expected PA)
    -> hitter_rates.project_hitter_rates       (regressed event rates)
    -> dk_scoring.hitter_components            (rates * PA -> DK points, per component)
    -> matchup.hitter_matchup_adjustment        (opposing-pitcher / platoon, capped points)
    -> matchup.environment_adjustment           (park / Vegas / weather / bullpen, capped points)
    -> uncertainty.hitter_uncertainty           (ceiling / floor / confidence / variance)
    -> models.NativePlayerProjection

`game_environment` is one game's raw dict from a loaded
research.game_environment.storage.load_latest_environment_report()
snapshot (i.e. one entry of a SlateEnvironmentReport's `games` list) --
this module resolves which side of it (home/away, own bullpen vs
opponent's) applies to THIS hitter; matchup.environment_adjustment itself
stays game-agnostic and only sees already-resolved values.
"""

from datetime import datetime, timezone
from typing import Optional

from models.batter import BatterInput

from native_projections import dk_scoring, hitter_rates as hitter_rates_module, matchup, playing_time, uncertainty, validation
from native_projections.models import InputCoverage, NativePlayerProjection
from native_projections.version import NATIVE_PROJECTION_MODEL_VERSION


def _resolve_hitter_environment(b: BatterInput, game_report: Optional[dict]) -> dict:
    if not game_report:
        return {}
    is_home = game_report.get("home_team") == b.team
    vegas = game_report.get("vegas") or {}
    weather = game_report.get("weather") or {}
    weather_analysis = game_report.get("weather_analysis") or {}
    ballpark = game_report.get("ballpark") or {}
    bullpen_home = game_report.get("bullpen_home") or {}
    bullpen_away = game_report.get("bullpen_away") or {}
    opposing_bullpen = bullpen_away if is_home else bullpen_home

    conclusions = weather_analysis.get("conclusions") or []
    weather_favors = [c.get("favors") for c in conclusions if isinstance(c, dict) and c.get("favors")]

    return dict(
        park_factor=ballpark.get("park_factor"),
        team_implied_runs=vegas.get("home_implied_runs") if is_home else vegas.get("away_implied_runs"),
        vegas_is_mock=vegas.get("is_mock"),
        weather_favors=weather_favors,
        weather_is_mock=weather.get("is_mock"),
        opposing_bullpen_strength=opposing_bullpen.get("strength_score"),
        bullpen_is_mock=opposing_bullpen.get("is_mock"),
    )


def project_hitter(
    b: BatterInput,
    game_environment: Optional[dict] = None,
    generated_at: Optional[str] = None,
    source_batter_snapshot_path: Optional[str] = None,
    source_environment_snapshot_path: Optional[str] = None,
) -> NativePlayerProjection:
    opportunity = playing_time.project_hitter_opportunity(b)
    rates = hitter_rates_module.project_hitter_rates(b)
    components = dk_scoring.hitter_components(rates, opportunity.expected_pa, b.batting_order)
    base_projection = dk_scoring.hitter_base_projection(components)

    matchup_result = matchup.hitter_matchup_adjustment(b)
    env_inputs = _resolve_hitter_environment(b, game_environment)
    env_result = matchup.environment_adjustment("hitter", **env_inputs)

    adjusted_projection = base_projection + matchup_result.points + env_result.points

    completeness_fraction = (
        rates.coverage_fields_available / rates.coverage_fields_total if rates.coverage_fields_total else 0.0
    )
    unc = uncertainty.hitter_uncertainty(
        rates,
        opportunity.expected_pa,
        adjusted_projection,
        opportunity.pa_confidence,
        b.season.plate_appearances,
        b.recent.plate_appearances,
        completeness_fraction,
    )

    coverage = InputCoverage(
        fields_available=rates.coverage_fields_available,
        fields_total=rates.coverage_fields_total,
        missing_fields=list(rates.coverage_missing_fields),
    )
    reasons = list(opportunity.reasons) + list(rates.reasons) + list(matchup_result.reasons) + list(env_result.reasons)

    proj = NativePlayerProjection(
        player_id=b.player_id,
        name=b.name,
        team=b.team,
        player_type="hitter",
        opponent=b.opponent,
        game_id=b.game_id,
        salary=b.salary,
        positions=[b.position] if b.position else [],
        batting_order=b.batting_order,
        native_projection=round(adjusted_projection, 3),
        native_ceiling=unc.ceiling,
        native_floor=unc.floor,
        confidence=unc.confidence,
        variance=unc.variance,
        model_version=NATIVE_PROJECTION_MODEL_VERSION,
        hitter_opportunity=opportunity,
        hitter_components=components,
        input_coverage=coverage,
        reasons=reasons,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
        source_batter_snapshot_path=source_batter_snapshot_path,
        source_environment_snapshot_path=source_environment_snapshot_path,
    )
    proj.warnings = validation.validate_projection(proj, b.season.plate_appearances)
    return proj
