"""Milestone 32.2B -- orchestrates one Big Money ML shadow-inference run
for a slate date:

    eligible starting pitchers (M30.1)
      -> pregame lock/freeze decision per pitcher
      -> live pregame features (same feature defs as training)
      -> frozen Pitcher Model V1 inference
      -> MLProjectionDocument
      -> immutable snapshot

Never retrains, never tunes, never looks at postgame data. A single
call to run_ml_shadow_inference() is what scripts/run_ml_shadow_inference.py
and the admin pipeline both call.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from historical_mlb.paths import WAREHOUSE_VERSION
from historical_models.pitcher_v1.features import assert_no_leakage
from historical_models.pitcher_v1.inference import predict_pitcher

from big_money_ml.artifact import ModelArtifactError, load_and_validate_frozen_pitcher_model
from big_money_ml.eligible_pitchers import build_eligibility_summary, get_eligible_starting_pitchers
from big_money_ml.feature_parity import build_feature_parity_report, parity_is_sufficient_for_inference, summarize_parity
from big_money_ml.live_features import build_live_pregame_pitcher_features, build_live_statcast_buffer
from big_money_ml.lock import FREEZE_EXISTING, GENERATE, NO_VALID_PREGAME, determine_action
from big_money_ml.models import INVALID_FEATURE_PARITY, LIVE_PREGAME, MISSING, PREGAME_FROZEN, MLPitcherProjection, MLProjectionDocument
from big_money_ml.persistence import load_latest_ml_projection_snapshot, save_ml_projection_document


class ShadowInferenceError(Exception):
    """Raised only for conditions the caller must treat as a hard stop
    (e.g. INCOMPATIBLE feature parity, frozen-artifact load failure).
    Callers (the CLI/admin pipeline) must catch this and report a
    non-blocking status, never let it take down the whole slate."""


@dataclass
class GameContext:
    game_id: str
    home_team_abbr: str
    away_team_abbr: str
    venue_id: Optional[int]
    game_datetime_utc: Optional[str]
    status: Optional[str]


def _coerce_venue_id(raw) -> Optional[int]:
    """research_output/<date>/games.json serializes venue_id as a JSON
    STRING (e.g. "32"), but the frozen model was trained on venue_id as
    an int64 warehouse column (see data/historical/mlb/processed/
    pitcher_game_features.parquet). Passing the string straight through
    would make the OneHotEncoder compare live values against training
    categories of a different dtype -- coerced here, once, at the
    single point live data enters this pipeline."""
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _load_games_by_id(slate_date: str, research_output_root: str = "research_output") -> Dict[str, GameContext]:
    path = Path(research_output_root) / slate_date / "games.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("games", data) if isinstance(data, dict) else data
    games: Dict[str, GameContext] = {}
    for g in items:
        game_id = g.get("game_id")
        if not game_id:
            continue
        games[str(game_id)] = GameContext(
            game_id=str(game_id), home_team_abbr=g.get("home_team_abbr", ""), away_team_abbr=g.get("away_team_abbr", ""),
            venue_id=_coerce_venue_id(g.get("venue_id")), game_datetime_utc=g.get("game_datetime_utc"), status=g.get("status"),
        )
    return games


def _existing_player_records(slate_date: str, output_root=None) -> Dict[str, dict]:
    kwargs = {} if output_root is None else {"output_root": output_root}
    doc = load_latest_ml_projection_snapshot(slate_date, **kwargs)
    if not doc:
        return {}
    return {p["player_id"]: p for p in doc.get("players", [])}


def _freeze_record(existing: dict) -> MLPitcherProjection:
    return MLPitcherProjection(
        player_id=existing["player_id"], dk_player_id=existing.get("dk_player_id"), name=existing.get("name", ""),
        team=existing.get("team", ""), opponent=existing.get("opponent", ""), game_id=existing.get("game_id"),
        salary=existing.get("salary"), projection=existing.get("projection"), model_version=existing.get("model_version", ""),
        data_quality_score=existing.get("data_quality_score"), feature_coverage=existing.get("feature_coverage"),
        missing_features=list(existing.get("missing_features", [])), projection_status=PREGAME_FROZEN,
        feature_timestamp=existing.get("feature_timestamp"), game_scheduled_start_utc=existing.get("game_scheduled_start_utc"),
        warnings=list(existing.get("warnings", [])),
    )


def run_ml_shadow_inference(
    slate_date: str, artifact_dir=None, now_utc: Optional[datetime] = None,
    research_output_root: str = "research_output", dfs_input_root=None,
    ml_projection_root=None,
) -> MLProjectionDocument:
    now_utc = now_utc or datetime.now(timezone.utc)
    generated_at = now_utc.isoformat()

    parity_rows = build_feature_parity_report()
    parity_summary = summarize_parity(parity_rows)
    eligibility_summary = build_eligibility_summary(slate_date, dfs_input_root=dfs_input_root)

    if not parity_is_sufficient_for_inference(parity_summary):
        raise ShadowInferenceError(
            f"Feature parity insufficient for live inference: {parity_summary['incompatible_count']} "
            f"INCOMPATIBLE feature(s): {parity_summary['incompatible_features']}. STOP LIVE INFERENCE."
        )

    try:
        frozen = load_and_validate_frozen_pitcher_model(artifact_dir)
    except ModelArtifactError as exc:
        raise ShadowInferenceError(str(exc)) from exc

    eligible = get_eligible_starting_pitchers(slate_date, dfs_input_root=dfs_input_root)
    games_by_id = _load_games_by_id(slate_date, research_output_root=research_output_root)
    existing_by_player = _existing_player_records(slate_date, output_root=ml_projection_root)
    statcast_buffer = build_live_statcast_buffer(slate_date)

    players: List[MLPitcherProjection] = []
    warnings: List[str] = []

    for p in eligible:
        game = games_by_id.get(str(p.game_id)) if p.game_id else None
        existing = existing_by_player.get(p.mlb_player_id)
        existing_status = existing.get("projection_status") if existing else None

        action = determine_action(
            mlb_detailed_state=game.status if game else None,
            game_scheduled_start_utc=game.game_datetime_utc if game else None,
            existing_projection_status=existing_status,
            now_utc=now_utc,
        )

        if action == FREEZE_EXISTING:
            players.append(_freeze_record(existing))
            continue

        if action == NO_VALID_PREGAME:
            players.append(MLPitcherProjection(
                player_id=p.mlb_player_id, dk_player_id=p.dk_player_id, name=p.name, team=p.team, opponent=p.opponent,
                game_id=p.game_id, salary=p.salary, projection=None, model_version=frozen.model_version,
                data_quality_score=None, feature_coverage=None, missing_features=[], projection_status=MISSING,
                feature_timestamp=None, game_scheduled_start_utc=game.game_datetime_utc if game else None,
                warnings=["NO VALID PREGAME ML PROJECTION"],
            ))
            continue

        # action == GENERATE
        if game is None:
            players.append(MLPitcherProjection(
                player_id=p.mlb_player_id, dk_player_id=p.dk_player_id, name=p.name, team=p.team, opponent=p.opponent,
                game_id=p.game_id, salary=p.salary, projection=None, model_version=frozen.model_version,
                data_quality_score=None, feature_coverage=None, missing_features=[], projection_status=MISSING,
                warnings=[f"No game context found for game_id={p.game_id} in research_output/{slate_date}/games.json"],
            ))
            continue

        home_away = "home" if p.team == game.home_team_abbr else "away"
        feature_result = build_live_pregame_pitcher_features(
            player_id=p.mlb_player_id, team=p.team, opponent=p.opponent, home_away=home_away,
            as_of_date=slate_date, venue_id=game.venue_id, statcast_buffer=statcast_buffer,
        )

        try:
            assert_no_leakage(list(feature_result.features.keys()))
            prediction = predict_pitcher(
                {**feature_result.features, "player_id": p.mlb_player_id}, artifact_dir=frozen.artifact_dir,
                pipeline=frozen.pipeline, metadata=frozen.metadata,
            )
        except ValueError as exc:
            players.append(MLPitcherProjection(
                player_id=p.mlb_player_id, dk_player_id=p.dk_player_id, name=p.name, team=p.team, opponent=p.opponent,
                game_id=p.game_id, salary=p.salary, projection=None, model_version=frozen.model_version,
                data_quality_score=None, feature_coverage=None, missing_features=[], projection_status=INVALID_FEATURE_PARITY,
                warnings=[str(exc)],
            ))
            continue

        feature_timestamp = datetime.now(timezone.utc).isoformat()
        player_warnings = list(feature_result.warnings)
        if game.game_datetime_utc and feature_timestamp >= game.game_datetime_utc:
            player_warnings.append("Feature timestamp is not strictly before game start -- this run should not have been classified GENERATE.")

        players.append(MLPitcherProjection(
            player_id=p.mlb_player_id, dk_player_id=p.dk_player_id, name=p.name, team=p.team, opponent=p.opponent,
            game_id=p.game_id, salary=p.salary, projection=prediction.projection, model_version=prediction.model_version,
            data_quality_score=prediction.data_quality_score, feature_coverage=prediction.feature_coverage,
            missing_features=prediction.missing_features, projection_status=LIVE_PREGAME,
            feature_timestamp=feature_timestamp, game_scheduled_start_utc=game.game_datetime_utc,
            warnings=player_warnings,
        ))

    generated_count = sum(1 for pl in players if pl.projection_status in (LIVE_PREGAME, PREGAME_FROZEN))
    missing_count = sum(1 for pl in players if pl.projection_status in (MISSING, INVALID_FEATURE_PARITY))

    document = MLProjectionDocument(
        slate_date=slate_date, generated_at=generated_at, model_version=frozen.model_version,
        warehouse_version=WAREHOUSE_VERSION, raw_dk_pitcher_count=eligibility_summary.raw_dk_pitcher_rows,
        starting_pitcher_count=eligibility_summary.starting_pitcher_count,
        ml_eligible_pitcher_count=eligibility_summary.ml_eligible_pitcher_count,
        ml_projections_generated=generated_count, ml_projections_missing=missing_count,
        feature_parity_summary=parity_summary, players=players, warnings=warnings,
    )
    save_kwargs = {} if ml_projection_root is None else {"output_root": ml_projection_root}
    save_ml_projection_document(document, **save_kwargs)
    return document
