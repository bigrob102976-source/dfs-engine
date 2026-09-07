"""NFL M10/M11 -- ties the real M6-M9 pipeline to the real, trained
nfl_v1 models for one live DraftGroup, offline (no Railway/web wiring
yet).

NFL M11 -- TRUE season-rollover (replaces M10's hardcoded "always use
2025"): current season/week is looked up from the real schedule for
`slate_date` (historical_nfl/season_timeline.py::determine_season_week_
for_date). Prior-season history (a full, real, completed season) and
any REAL completed weeks of the current season are both loaded, then
remapped onto one continuous week timeline
(historical_nfl/season_timeline.py::remap_to_continuous_timeline) so
the EXISTING, already-tested leakage-safe rolling functions blend them
with zero new blending code -- see that module's own docstring for
exactly why this produces Phase 6's requested "early season leans on
prior-season history, later weeks lean on current-season usage"
behavior automatically, without an invented weight.

Never fabricates: a player with no crosswalk GSIS match, or whose
position has no trained model artifact, is simply absent from the
returned list -- never assigned a guessed/salary-derived/zero
projection."""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from historical_models.nfl_v1.config import DST_POSITION, MODEL_VERSION
from historical_models.nfl_v1.inference import NflModelArtifactError, load_position_model, predict_one
from historical_nfl.dk_actual_scoring import calculate_actual_offense_dk_points
from historical_nfl.dst_rolling import compute_dst_rolling_features
from historical_nfl.dst_usage_normalize import build_dst_usage_records
from historical_nfl.identity_persistence import load_crosswalk
from historical_nfl.season_timeline import completed_weeks_in_season, continuous_week, determine_season_week_for_date, remap_to_continuous_timeline
from historical_nfl.team_offense_normalize import build_team_offense_records
from historical_nfl.team_offense_rolling import compute_team_offense_rolling_features
from historical_nfl.usage_identity_bridge import build_pfr_to_gsis_bridge
from historical_nfl.usage_normalize import build_usage_records
from historical_nfl import nflverse_client as nc
from nfl.pool_builder import build_pool_preferring_cache
from nfl.projection_features import build_projection_features
from nfl.projection_models import NflProjectionRecord


def _load_season_history(season: int, weeks: List[int]):
    """Real per-week fetch identical to historical_models/nfl_v1/train.py's
    training-data construction, parametrized by season/weeks so it works
    for both a full completed prior season and a partial in-progress
    current season."""
    schedules_df, _, _ = nc.fetch_schedules(season)
    schedule_rows = schedules_df.filter(schedules_df["game_type"] == "REG").to_dicts()
    ff_df, _, _ = nc.fetch_ff_playerids()
    pfr_bridge = build_pfr_to_gsis_bridge(ff_df)

    usage_records, dst_records, team_offense_records = [], [], []
    dk_points_by_gsis_week: Dict[str, Dict[int, float]] = {}

    for week in weeks:
        try:
            ws_df, fetched_at, _ = nc.fetch_weekly_player_stats(season, week)
        except Exception:  # noqa: BLE001 -- a real, expected miss when this week's stat file isn't published yet
            continue
        snap_df, _, _ = nc.fetch_snap_counts(season, week)
        pbp_df, _, _ = nc.fetch_play_by_play(season, week)
        team_df, _, _ = nc.fetch_team_stats(season, week)
        ws_rows, snap_rows, pbp_rows, team_rows = ws_df.to_dicts(), snap_df.to_dicts(), pbp_df.to_dicts(), team_df.to_dicts()
        if not ws_rows:
            continue

        records, _ = build_usage_records(season, week, ws_rows, snap_rows, pbp_rows, pfr_bridge, {}, fetched_at)
        usage_records.extend(records)

        week_schedule = [r for r in schedule_rows if r.get("week") == week]
        dst_records.extend(build_dst_usage_records(season, week, team_rows, week_schedule, fetched_at))
        team_offense_records.extend(build_team_offense_records(season, week, team_rows, week_schedule, fetched_at))

        for row in ws_rows:
            gsis_id = row.get("player_id")
            if not gsis_id:
                continue
            target = calculate_actual_offense_dk_points(row)
            if target["scored"]:
                dk_points_by_gsis_week.setdefault(gsis_id, {})[week] = target["dfs_points"]

    return usage_records, dst_records, team_offense_records, dk_points_by_gsis_week


def _recent3(history: Dict[int, float], as_of_week: int) -> Optional[float]:
    vals = [history[w] for w in range(as_of_week - 3, as_of_week) if w in history]
    return sum(vals) / len(vals) if vals else None


def build_current_nfl_projection_features(draft_group_id: int, slate_date: str):
    """NFL M11 Phase 8 -- the one production-safe entry point: resolves
    DK->GSIS, determines real current season/week, loads only completed
    historical data (prior season in full + any real completed current-
    season weeks), blends them via the continuous-week timeline, and
    returns everything generate_projections() needs. No manually
    selected season -- see determine_season_week_for_date()."""
    current_season, current_week = determine_season_week_for_date(slate_date)
    prior_season = current_season - 1
    current_completed_weeks = [w for w in completed_weeks_in_season(current_season) if w < current_week]

    prior_usage, prior_dst, prior_team_off, prior_dk_points = _load_season_history(prior_season, list(range(1, 19)))
    if current_completed_weeks:
        cur_usage, cur_dst, cur_team_off, cur_dk_points = _load_season_history(current_season, current_completed_weeks)
    else:
        cur_usage, cur_dst, cur_team_off, cur_dk_points = [], [], [], {}

    usage_records = remap_to_continuous_timeline(prior_usage, current_season) + remap_to_continuous_timeline(cur_usage, current_season)
    dst_records = remap_to_continuous_timeline(prior_dst, current_season) + remap_to_continuous_timeline(cur_dst, current_season)
    team_offense_records = remap_to_continuous_timeline(prior_team_off, current_season) + remap_to_continuous_timeline(cur_team_off, current_season)

    dk_points_by_gsis_week: Dict[str, Dict[int, float]] = {}
    for gsis_id, weeks_map in prior_dk_points.items():
        dk_points_by_gsis_week.setdefault(gsis_id, {}).update({continuous_week(prior_season, w, current_season): v for w, v in weeks_map.items()})
    for gsis_id, weeks_map in cur_dk_points.items():
        dk_points_by_gsis_week.setdefault(gsis_id, {}).update({continuous_week(current_season, w, current_season): v for w, v in weeks_map.items()})

    pool = build_pool_preferring_cache(slate_date, draft_group_id, sport_code="NFL")
    crosswalk = load_crosswalk()
    offense_players = [p for p in pool.players if not p.is_team_entity]
    dst_players = [p for p in pool.players if p.is_team_entity]

    join_result = build_projection_features(offense_players, crosswalk, usage_records, [], as_of_season=current_season, as_of_week=current_week)

    return {
        "current_season": current_season, "current_week": current_week,
        "prior_season": prior_season, "current_completed_weeks": current_completed_weeks,
        "pool": pool, "offense_players": offense_players, "dst_players": dst_players,
        "join_result": join_result, "dst_records": dst_records, "team_offense_records": team_offense_records,
        "dk_points_by_gsis_week": dk_points_by_gsis_week,
    }


def generate_projections(draft_group_id: int, slate_date: str, ctx: Optional[dict] = None) -> List[NflProjectionRecord]:
    """NFL UI M1: accepts an optional pre-built `ctx` (from
    build_current_nfl_projection_features()) so a caller that also needs
    the raw usage/matchup context (e.g. scripts/nfl_dashboard_data.py)
    can build it ONCE and reuse it here, rather than this function
    re-fetching the entire real historical dataset a second time."""
    if ctx is None:
        ctx = build_current_nfl_projection_features(draft_group_id, slate_date)
    current_week = ctx["current_week"]

    generated_at = datetime.now(timezone.utc).isoformat()
    data_timestamp = f"prior_season={ctx['prior_season']}_full+current_season={ctx['current_season']}_weeks_{ctx['current_completed_weeks']}"
    records: List[NflProjectionRecord] = []
    models_cache = {}

    def get_model(position):
        if position not in models_cache:
            try:
                models_cache[position] = load_position_model(position)
            except NflModelArtifactError:
                models_cache[position] = None
        return models_cache[position]

    players_by_dk_id = {p.draftkings_player_id: p for p in ctx["offense_players"]}
    for feature in ctx["join_result"].features:
        model = get_model(feature.position)
        if model is None:
            continue

        feature_row = {**feature.rolling, **feature.season_to_date}
        feature_row["weeks_of_history"] = feature.rolling.get("weeks_of_history", 0)
        feature_row["has_prior_week"] = 1.0 if feature_row["weeks_of_history"] > 0 else 0.0
        player = players_by_dk_id[feature.draftkings_player_id]
        feature_row["is_home"] = None  # game context null until real M7 credentials exist (see nfl/odds_provider.py)
        feature_row["rest_days"] = None
        history = ctx["dk_points_by_gsis_week"].get(feature.gsis_id, {})
        feature_row["recent_dk_points_mean_last3"] = _recent3(history, current_week)

        prediction = predict_one(model, feature_row)
        _append_record(records, player, feature.position, prediction, draft_group_id, generated_at, data_timestamp, model)

    dst_model = get_model(DST_POSITION)
    if dst_model is not None:
        for player in ctx["dst_players"]:
            rolling = dict(compute_dst_rolling_features(ctx["dst_records"], player.team, current_week))
            if player.opponent:
                rolling.update(compute_team_offense_rolling_features(ctx["team_offense_records"], player.opponent, current_week))
            feature_row = dict(rolling)
            feature_row["has_prior_week"] = 1.0 if rolling.get("weeks_of_history", 0) > 0 else 0.0
            feature_row["is_home"] = None
            feature_row["recent_dk_points_mean_last3"] = None

            prediction = predict_one(dst_model, feature_row)
            _append_record(records, player, "DST", prediction, draft_group_id, generated_at, data_timestamp, dst_model)

    return records


def _append_record(records, player, position, prediction, draft_group_id, generated_at, data_timestamp, model) -> None:
    # NFL M11 Phase 11: an honest, distinct source label when the
    # selected model is a non-learned baseline fallback (e.g. DST's
    # positional_mean_baseline -- see historical_models/nfl_v1/train.py's
    # module docstring) -- never disguised as the learned model.
    model_family = model.metadata.get("model_family", "")
    is_baseline = "baseline" in model_family
    source = f"BIG_MONEY_NATIVE_{position}_BASELINE" if is_baseline else "BIG_MONEY_NATIVE"
    model_name = f"big_money_native_nfl_{model_family}" if is_baseline else "big_money_native_nfl"

    records.append(NflProjectionRecord(
        sport="NFL", draft_group_id=draft_group_id,
        canonical_player_id=player.draftkings_player_id, draftkings_player_id=player.draftkings_player_id,
        draftable_ids=player.draftable_ids, name=player.name, position=position,
        team=player.team, opponent=player.opponent,
        projection=prediction["projection"], floor=prediction["floor"], ceiling=prediction["ceiling"],
        source=source, source_provenance=source,
        model_name=model_name, model_version=MODEL_VERSION,
        generated_at=generated_at, data_timestamp=data_timestamp, feature_version=MODEL_VERSION,
    ))
