"""NFL M10 -- ties the real M6-M9 pipeline to the real, trained nfl_v1
models for one live DraftGroup, offline (no Railway/web wiring yet).

Historical basis: real, complete 2025 season usage (as-of week 19 --
i.e. every real 2025 week, since week 19 doesn't exist) is used as each
player's most recent trailing usage state. This is a documented,
honest M10 limitation, not an oversight: true cross-season rollover
(blending a real 2026 week 1's own usage once it exists with 2025's
tail) is not built this milestone -- see this module's own report in
the M10 final write-up. A player who has genuinely never played (a true
rookie) still correctly gets zero history either way.

Never fabricates: a player with no crosswalk GSIS match, or whose
position has no trained model artifact, is simply absent from the
returned list -- never assigned a guessed/salary-derived/zero
projection."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from historical_models.nfl_v1.config import DST_POSITION, OFFENSE_POSITIONS, MODEL_VERSION
from historical_models.nfl_v1.inference import NflModelArtifactError, load_position_model, predict_one
from historical_nfl.dk_actual_scoring import calculate_actual_offense_dk_points
from historical_nfl.dst_rolling import compute_dst_rolling_features
from historical_nfl.dst_usage_normalize import build_dst_usage_records
from historical_nfl.identity_persistence import load_crosswalk
from historical_nfl.usage_normalize import build_usage_records
from historical_nfl.usage_identity_bridge import build_pfr_to_gsis_bridge
from historical_nfl import nflverse_client as nc
from nfl.pool_builder import build_pool
from nfl.projection_features import build_projection_features
from nfl.projection_models import NflProjectionRecord

HISTORY_SEASON = 2025
HISTORY_AS_OF_WEEK = 19  # every real 2025 week is < 19 -- see module docstring
HISTORY_WEEKS = list(range(1, 19))


def _load_2025_history():
    """Real, cached (nflreadpy) 2025 season usage + DST records + per-
    week actual DK points (for the recent-3-week baseline feature) --
    identical construction to historical_models/nfl_v1/dataset.py's
    training data, so live feature rows match training feature rows
    exactly."""
    schedules_df, _, _ = nc.fetch_schedules(HISTORY_SEASON)
    schedule_rows = schedules_df.filter(schedules_df["game_type"] == "REG").to_dicts()
    ff_df, _, _ = nc.fetch_ff_playerids()
    pfr_bridge = build_pfr_to_gsis_bridge(ff_df)

    usage_records = []
    dst_records = []
    dk_points_by_gsis_week: Dict[str, Dict[int, float]] = {}
    dk_points_by_team_week: Dict[str, Dict[int, float]] = {}

    for week in HISTORY_WEEKS:
        ws_df, fetched_at, _ = nc.fetch_weekly_player_stats(HISTORY_SEASON, week)
        snap_df, _, _ = nc.fetch_snap_counts(HISTORY_SEASON, week)
        pbp_df, _, _ = nc.fetch_play_by_play(HISTORY_SEASON, week)
        team_df, _, _ = nc.fetch_team_stats(HISTORY_SEASON, week)
        ws_rows, snap_rows, pbp_rows, team_rows = ws_df.to_dicts(), snap_df.to_dicts(), pbp_df.to_dicts(), team_df.to_dicts()
        if not ws_rows:
            continue

        records, _ = build_usage_records(HISTORY_SEASON, week, ws_rows, snap_rows, pbp_rows, pfr_bridge, {}, fetched_at)
        usage_records.extend(records)

        week_schedule = [r for r in schedule_rows if r.get("week") == week]
        dst_records.extend(build_dst_usage_records(HISTORY_SEASON, week, team_rows, week_schedule, fetched_at))

        for row in ws_rows:
            gsis_id = row.get("player_id")
            if not gsis_id:
                continue
            target = calculate_actual_offense_dk_points(row)
            if target["scored"]:
                dk_points_by_gsis_week.setdefault(gsis_id, {})[week] = target["dfs_points"]

    return usage_records, dst_records, dk_points_by_gsis_week, schedule_rows


def _recent3(history: Dict[int, float], as_of_week: int) -> Optional[float]:
    vals = [history[w] for w in range(as_of_week - 3, as_of_week) if w in history]
    return sum(vals) / len(vals) if vals else None


def generate_projections(draft_group_id: int, slate_date: str) -> List[NflProjectionRecord]:
    pool = build_pool(slate_date, draft_group_id, sport_code="NFL")
    crosswalk = load_crosswalk()

    usage_records, dst_records, dk_points_by_gsis_week, schedule_rows = _load_2025_history()

    offense_players = [p for p in pool.players if not p.is_team_entity]
    join_result = build_projection_features(offense_players, crosswalk, usage_records, [], as_of_season=HISTORY_SEASON, as_of_week=HISTORY_AS_OF_WEEK)

    generated_at = datetime.now(timezone.utc).isoformat()
    records: List[NflProjectionRecord] = []
    models_cache = {}

    def get_model(position):
        if position not in models_cache:
            try:
                models_cache[position] = load_position_model(position)
            except NflModelArtifactError:
                models_cache[position] = None
        return models_cache[position]

    players_by_dk_id = {p.draftkings_player_id: p for p in offense_players}
    for feature in join_result.features:
        model = get_model(feature.position)
        if model is None:
            continue

        feature_row = {**feature.rolling, **feature.season_to_date}
        feature_row["weeks_of_history"] = feature.rolling.get("weeks_of_history", 0)
        feature_row["has_prior_week"] = 1.0 if feature_row["weeks_of_history"] > 0 else 0.0
        player = players_by_dk_id[feature.draftkings_player_id]
        feature_row["is_home"] = None  # game context null until real M7 credentials exist (see nfl/odds_provider.py)
        feature_row["rest_days"] = None
        history = dk_points_by_gsis_week.get(feature.gsis_id, {})
        feature_row["recent_dk_points_mean_last3"] = _recent3(history, HISTORY_AS_OF_WEEK)

        prediction = predict_one(model, feature_row)

        records.append(NflProjectionRecord(
            sport="NFL", draft_group_id=draft_group_id,
            canonical_player_id=player.draftkings_player_id, draftkings_player_id=player.draftkings_player_id,
            draftable_ids=player.draftable_ids, name=player.name, position=player.position,
            team=player.team, opponent=player.opponent,
            projection=prediction["projection"], floor=prediction["floor"], ceiling=prediction["ceiling"],
            model_name="big_money_native_nfl", model_version=MODEL_VERSION,
            generated_at=generated_at, data_timestamp=f"{HISTORY_SEASON}_through_week_18", feature_version=MODEL_VERSION,
        ))

    dst_players = [p for p in pool.players if p.is_team_entity]
    dst_model = get_model(DST_POSITION)
    if dst_model is not None:
        for player in dst_players:
            rolling = compute_dst_rolling_features(dst_records, player.team, HISTORY_AS_OF_WEEK)
            feature_row = dict(rolling)
            feature_row["has_prior_week"] = 1.0 if rolling.get("weeks_of_history", 0) > 0 else 0.0
            feature_row["is_home"] = None
            feature_row["recent_dk_points_mean_last3"] = None

            prediction = predict_one(dst_model, feature_row)
            records.append(NflProjectionRecord(
                sport="NFL", draft_group_id=draft_group_id,
                canonical_player_id=player.draftkings_player_id, draftkings_player_id=player.draftkings_player_id,
                draftable_ids=player.draftable_ids, name=player.name, position="DST",
                team=player.team, opponent=player.opponent,
                projection=prediction["projection"], floor=prediction["floor"], ceiling=prediction["ceiling"],
                model_name="big_money_native_nfl", model_version=MODEL_VERSION,
                generated_at=generated_at, data_timestamp=f"{HISTORY_SEASON}_through_week_18", feature_version=MODEL_VERSION,
            ))

    return records
