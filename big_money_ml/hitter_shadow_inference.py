"""Milestone 32.3B -- orchestrates one Big Money ML HITTER shadow-
inference run for a slate date:

    eligible starting hitters (M30.1)
      -> resolve confirmed opposing starter identity (AFTER_LINEUP gate)
      -> pregame lock/freeze decision per hitter (same lock.py as pitchers)
      -> live pregame features (same feature defs as training)
      -> frozen Hitter Model V1 inference
      -> MLHitterProjectionDocument
      -> immutable snapshot (separate filename prefix from the pitcher stream)

Never retrains, never tunes, never looks at postgame data. A SIBLING
of shadow_inference.py -- that pitcher orchestrator is never imported
for its logic (only its already-tested, non-pitcher-specific
_load_games_by_id helper is reused) so pitcher shadow inference stays
completely unaffected by this module's existence.

AFTER_LINEUP-only: a hitter with no resolvable opposing PROBABLE
starter for their own game is NOT ML-eligible for a projection this
run (NO_VALID_LIVE_ML_PROJECTION), never silently downgraded to a
different (unapproved) ALWAYS_PREGAME artifact.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from historical_mlb.paths import WAREHOUSE_VERSION
from historical_models.hitter_v1.features import assert_no_leakage
from historical_models.hitter_v1.inference import predict_hitter

from big_money_ml.eligible_hitters import build_hitter_eligibility_summary, get_eligible_starting_hitters
from big_money_ml.hitter_artifact import HitterModelArtifactError, load_and_validate_frozen_hitter_model
from big_money_ml.hitter_feature_parity import build_hitter_feature_parity_report, hitter_parity_is_sufficient_for_inference, summarize_hitter_parity
from big_money_ml.live_hitter_features import build_live_pregame_hitter_features
from big_money_ml.live_features import build_live_statcast_buffer
from big_money_ml.lock import FREEZE_EXISTING, GENERATE, NO_VALID_PREGAME, determine_action
from big_money_ml.models import INVALID_FEATURE_PARITY, LIVE_PREGAME, MISSING, PREGAME_FROZEN, MLHitterProjection, MLHitterProjectionDocument
from big_money_ml.persistence import load_latest_ml_hitter_projection_snapshot, save_ml_hitter_projection_document
from big_money_ml.shadow_inference import _load_games_by_id

NO_VALID_LIVE_ML_PROJECTION = "NO VALID LIVE ML PROJECTION"


class HitterShadowInferenceError(Exception):
    """Raised only for conditions the caller must treat as a hard stop
    (e.g. INCOMPATIBLE feature parity, frozen-artifact load failure).
    Callers (the CLI/admin pipeline) must catch this and report a
    non-blocking status, never let it take down the whole slate."""


def _load_probable_starters_by_team_and_game(slate_date: str, research_output_root: str = "research_output") -> Dict[tuple, str]:
    """{(game_id, team_abbr): mlb_player_id} for every PROBABLE starting
    pitcher in research_output/<date>/pitchers.json -- the only
    pregame-legitimate source of "who is starting for this team today,"
    same field the M32.2B pitcher shadow path already treats as
    authoritative."""
    path = Path(research_output_root) / slate_date / "pitchers.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("pitchers", data) if isinstance(data, dict) else data
    out: Dict[tuple, str] = {}
    for p in items:
        if p.get("status") != "probable":
            continue
        game_id, team_abbr, player_id = p.get("game_id"), p.get("team_abbr"), p.get("player_id")
        if not (game_id and team_abbr and player_id):
            continue
        out[(str(game_id), team_abbr)] = str(player_id)
    return out


def _existing_player_records(slate_date: str, output_root=None) -> Dict[str, dict]:
    kwargs = {} if output_root is None else {"output_root": output_root}
    doc = load_latest_ml_hitter_projection_snapshot(slate_date, **kwargs)
    if not doc:
        return {}
    return {p["player_id"]: p for p in doc.get("players", [])}


def _freeze_record(existing: dict) -> MLHitterProjection:
    return MLHitterProjection(
        player_id=existing["player_id"], dk_player_id=existing.get("dk_player_id"), name=existing.get("name", ""),
        team=existing.get("team", ""), opponent=existing.get("opponent", ""), game_id=existing.get("game_id"),
        salary=existing.get("salary"), batting_order=existing.get("batting_order"), projection=existing.get("projection"),
        model_version=existing.get("model_version", ""), data_quality_score=existing.get("data_quality_score"),
        feature_coverage=existing.get("feature_coverage"), missing_features=list(existing.get("missing_features", [])),
        projection_status=PREGAME_FROZEN, feature_timestamp=existing.get("feature_timestamp"),
        game_scheduled_start_utc=existing.get("game_scheduled_start_utc"), warnings=list(existing.get("warnings", [])),
    )


def _missing_record(p, model_version: str, game_scheduled_start_utc: Optional[str], warning: str) -> MLHitterProjection:
    return MLHitterProjection(
        player_id=p.mlb_player_id, dk_player_id=p.dk_player_id, name=p.name, team=p.team, opponent=p.opponent,
        game_id=p.game_id, salary=p.salary, batting_order=p.batting_order, projection=None, model_version=model_version,
        data_quality_score=None, feature_coverage=None, missing_features=[], projection_status=MISSING,
        game_scheduled_start_utc=game_scheduled_start_utc, warnings=[warning],
    )


def run_ml_hitter_shadow_inference(
    slate_date: str, artifact_dir=None, now_utc: Optional[datetime] = None,
    research_output_root: str = "research_output", dfs_input_root=None,
    ml_projection_root=None,
) -> MLHitterProjectionDocument:
    now_utc = now_utc or datetime.now(timezone.utc)
    generated_at = now_utc.isoformat()

    parity_rows = build_hitter_feature_parity_report()
    parity_summary = summarize_hitter_parity(parity_rows)
    eligibility_summary = build_hitter_eligibility_summary(slate_date, dfs_input_root=dfs_input_root)

    if not hitter_parity_is_sufficient_for_inference(parity_summary):
        raise HitterShadowInferenceError(
            f"Feature parity insufficient for live hitter inference: {parity_summary['incompatible_count']} "
            f"INCOMPATIBLE feature(s): {parity_summary['incompatible_features']}. STOP LIVE INFERENCE."
        )

    try:
        frozen = load_and_validate_frozen_hitter_model(artifact_dir)
    except HitterModelArtifactError as exc:
        raise HitterShadowInferenceError(str(exc)) from exc

    if frozen.feature_availability_class != "AFTER_LINEUP":
        raise HitterShadowInferenceError(
            f"Frozen hitter artifact's feature_availability_class is {frozen.feature_availability_class!r}, not "
            "'AFTER_LINEUP' -- this live path only supports the approved AFTER_LINEUP artifact. STOP LIVE INFERENCE."
        )

    eligible = get_eligible_starting_hitters(slate_date, dfs_input_root=dfs_input_root)
    games_by_id = _load_games_by_id(slate_date, research_output_root=research_output_root)
    probable_starters = _load_probable_starters_by_team_and_game(slate_date, research_output_root=research_output_root)
    existing_by_player = _existing_player_records(slate_date, output_root=ml_projection_root)
    statcast_buffer = build_live_statcast_buffer(slate_date)
    # Milestone 32.4 performance optimization: shared across every
    # hitter in this run so hitters facing the same opposing starter
    # (up to 8-9 per game) reuse one fetch instead of refetching per hitter.
    opposing_pitcher_cache: Dict[str, dict] = {}

    players: List[MLHitterProjection] = []
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
            players.append(_missing_record(p, frozen.model_version, game.game_datetime_utc if game else None, NO_VALID_LIVE_ML_PROJECTION))
            continue

        # action == GENERATE
        if game is None:
            players.append(_missing_record(p, frozen.model_version, None, f"No game context found for game_id={p.game_id} in research_output/{slate_date}/games.json"))
            continue

        opposing_starter_id = probable_starters.get((str(p.game_id), p.opponent))
        if opposing_starter_id is None:
            players.append(_missing_record(
                p, frozen.model_version, game.game_datetime_utc,
                f"{NO_VALID_LIVE_ML_PROJECTION} -- no confirmed PROBABLE starter found for opponent {p.opponent} in game {p.game_id} "
                "(AFTER_LINEUP model requires a resolvable opposing starter; never guessed).",
            ))
            continue

        if p.batting_order is None:
            players.append(_missing_record(
                p, frozen.model_version, game.game_datetime_utc,
                f"{NO_VALID_LIVE_ML_PROJECTION} -- no confirmed batting_order for this hitter (AFTER_LINEUP model requires a posted lineup slot; never guessed).",
            ))
            continue

        home_away = "home" if p.team == game.home_team_abbr else "away"
        feature_result = build_live_pregame_hitter_features(
            player_id=p.mlb_player_id, team=p.team, opponent=p.opponent, home_away=home_away,
            as_of_date=slate_date, venue_id=game.venue_id, statcast_buffer=statcast_buffer,
            opposing_starter_id=opposing_starter_id, batting_order_actual=p.batting_order,
            opposing_pitcher_cache=opposing_pitcher_cache,
        )

        try:
            assert_no_leakage(list(feature_result.features.keys()))
            prediction = predict_hitter(
                {**feature_result.features, "player_id": p.mlb_player_id}, artifact_dir=frozen.artifact_dir,
                pipeline=frozen.pipeline, feature_list=frozen.feature_list, metadata=frozen.metadata,
            )
        except ValueError as exc:
            players.append(MLHitterProjection(
                player_id=p.mlb_player_id, dk_player_id=p.dk_player_id, name=p.name, team=p.team, opponent=p.opponent,
                game_id=p.game_id, salary=p.salary, batting_order=p.batting_order, projection=None, model_version=frozen.model_version,
                data_quality_score=None, feature_coverage=None, missing_features=[], projection_status=INVALID_FEATURE_PARITY,
                warnings=[str(exc)],
            ))
            continue

        feature_timestamp = datetime.now(timezone.utc).isoformat()
        player_warnings = list(feature_result.warnings)
        if game.game_datetime_utc and feature_timestamp >= game.game_datetime_utc:
            player_warnings.append("Feature timestamp is not strictly before game start -- this run should not have been classified GENERATE.")

        players.append(MLHitterProjection(
            player_id=p.mlb_player_id, dk_player_id=p.dk_player_id, name=p.name, team=p.team, opponent=p.opponent,
            game_id=p.game_id, salary=p.salary, batting_order=p.batting_order, projection=prediction.projection,
            model_version=prediction.model_version, data_quality_score=prediction.data_quality_score,
            feature_coverage=prediction.feature_coverage, missing_features=prediction.missing_features,
            projection_status=LIVE_PREGAME, feature_timestamp=feature_timestamp, game_scheduled_start_utc=game.game_datetime_utc,
            warnings=player_warnings,
        ))

    generated_count = sum(1 for pl in players if pl.projection_status in (LIVE_PREGAME, PREGAME_FROZEN))
    missing_count = sum(1 for pl in players if pl.projection_status in (MISSING, INVALID_FEATURE_PARITY))

    document = MLHitterProjectionDocument(
        slate_date=slate_date, generated_at=generated_at, model_version=frozen.model_version,
        warehouse_version=WAREHOUSE_VERSION, raw_dk_hitter_count=eligibility_summary.raw_dk_hitter_rows,
        confirmed_starting_hitter_count=eligibility_summary.confirmed_starting_hitter_count,
        ml_eligible_hitter_count=eligibility_summary.ml_eligible_hitter_count,
        ml_projections_generated=generated_count, ml_projections_missing=missing_count,
        feature_parity_summary=parity_summary, players=players, warnings=warnings,
    )
    save_kwargs = {} if ml_projection_root is None else {"output_root": ml_projection_root}
    save_ml_hitter_projection_document(document, **save_kwargs)
    return document
