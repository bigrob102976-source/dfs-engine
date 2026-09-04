"""NFL UI M1 -- the single real-data bridge the dashboard's NFL API
routes call (via the existing MLB_DFS_PYTHON subprocess convention,
mirroring dashboard/lib/orchestrator/pythonRunner.ts's pattern). Prints
ONE JSON object to stdout: real DK slate/pool, real usage features, real
matchup/game context (honestly empty without M7 odds credentials), and
real Big Money Native projections (honestly absent for any player/
position without a real trained model or resolved identity).

Never fabricates: every "not available" field is null, never a guessed
number -- the dashboard is responsible for rendering null as an honest
"--" / "Not Available", never as 0.

Usage:
    python scripts/nfl_dashboard_data.py <draft_group_id>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftkings_unofficial import collector
from historical_nfl.identity_persistence import load_crosswalk
from nfl.big_money_native_inference import build_current_nfl_projection_features, generate_projections
from nfl.game_context_builder import build_nfl_game_context
from nfl.pool_builder import NflPoolBuildError


def _player_dict(player) -> dict:
    return {
        "draftkings_player_id": player.draftkings_player_id,
        "name": player.name,
        "position": player.position,
        "team": player.team,
        "opponent": player.opponent,
        "game_id": player.game_id,
        "salary": player.salary,
        "roster_slots": player.roster_slots,
        "is_team_entity": player.is_team_entity,
        "status": player.status,
        "injury_status": player.injury_status,
    }


def main(draft_group_id: int) -> int:
    universe = collector.collect_sport_universe("NFL")
    if universe.status != collector.STATUS_OK:
        print(json.dumps({"error": f"DISCOVERY_FAILED: {universe.status} ({universe.error})"}))
        return 1
    slate = next((s for s in universe.slates if s.draft_group_id == draft_group_id), None)
    if slate is None:
        print(json.dumps({"error": f"DraftGroup {draft_group_id} not found in current NFL universe."}))
        return 1
    slate_date = collector.slate_local_date(slate)

    try:
        ctx = build_current_nfl_projection_features(draft_group_id, slate_date)
    except NflPoolBuildError as exc:
        print(json.dumps({"error": f"BUILD_POOL_FAILED: {exc}"}))
        return 1

    pool = ctx["pool"]
    crosswalk = load_crosswalk()

    # Real matchup/game context (M7) -- honestly empty without odds
    # credentials, never fabricated. Reuses M2's own canonical pool
    # (never a second fetch).
    game_ctx_result = build_nfl_game_context(pool.players, draft_group_id, pool.slate_date)
    games_by_id = {g.canonical_game_id: g for g in game_ctx_result.match_result.games}

    # Real projections (reuses the SAME ctx -- no second historical fetch)
    try:
        projection_records = generate_projections(draft_group_id, slate_date, ctx=ctx)
    except Exception as exc:  # noqa: BLE001 -- no trained model artifacts locally is a real, expected state to report honestly, never crash the dashboard
        projection_records = []
        projection_error = str(exc)
    else:
        projection_error = None
    projections_by_dk_id = {r.draftkings_player_id: r for r in projection_records}

    usage_by_dk_id = {f.draftkings_player_id: f for f in ctx["join_result"].features}

    # Real games list (from the canonical pool -- derived, not guessed)
    games = {}
    for p in pool.players:
        if p.game_id not in games:
            games[p.game_id] = {
                "game_id": p.game_id, "game_description": p.game_description, "game_start_time": p.game_start_time,
            }
    game_rows = []
    for game_id, g in games.items():
        matched = games_by_id.get(game_id)
        game_rows.append({
            **g,
            "spread_home": matched.spread if matched else None,
            "total": matched.total if matched else None,
            "home_implied_total": matched.home_implied_total if matched else None,
            "away_implied_total": matched.away_implied_total if matched else None,
        })

    players = []
    for p in pool.players:
        row = _player_dict(p)
        crosswalk_row = crosswalk.get(p.draftkings_player_id)
        row["gsis_id"] = crosswalk_row.gsis_id if crosswalk_row else None
        row["identity_resolved"] = bool(crosswalk_row and crosswalk_row.gsis_id)

        usage = usage_by_dk_id.get(p.draftkings_player_id)
        row["usage"] = {"rolling": usage.rolling, "season_to_date": usage.season_to_date} if usage else None

        proj = projections_by_dk_id.get(p.draftkings_player_id)
        if proj is not None:
            row["projection"] = {
                "projection": proj.projection, "floor": proj.floor, "ceiling": proj.ceiling,
                "source": proj.source, "model_name": proj.model_name, "model_version": proj.model_version,
            }
        else:
            row["projection"] = None

        matched_game = games_by_id.get(p.game_id)
        row["matchup"] = {
            "spread_home": matched_game.spread if matched_game else None,
            "total": matched_game.total if matched_game else None,
            "home_implied_total": matched_game.home_implied_total if matched_game else None,
            "away_implied_total": matched_game.away_implied_total if matched_game else None,
        } if matched_game else None

        # DST opponent-context usage (M11) -- attached separately since
        # DST players aren't in join_result (offense-only)
        if p.is_team_entity:
            from historical_nfl.dst_rolling import compute_dst_rolling_features
            from historical_nfl.team_offense_rolling import compute_team_offense_rolling_features
            rolling = dict(compute_dst_rolling_features(ctx["dst_records"], p.team, ctx["current_week"]))
            if p.opponent:
                rolling.update(compute_team_offense_rolling_features(ctx["team_offense_records"], p.opponent, ctx["current_week"]))
            row["usage"] = {"rolling": rolling, "season_to_date": {}}

        players.append(row)

    position_counts = {}
    for p in pool.players:
        pos = "DST" if p.is_team_entity else p.position
        position_counts[pos] = position_counts.get(pos, 0) + 1

    resolved_count = sum(1 for p in players if p["identity_resolved"] or p["is_team_entity"])
    projected_count = sum(1 for p in players if p["projection"] is not None)
    projection_coverage_by_position = {}
    for pos in ("QB", "RB", "WR", "TE", "DST"):
        pos_players = [p for p in players if (("DST" if p["is_team_entity"] else p["position"]) == pos)]
        pos_projected = [p for p in pos_players if p["projection"] is not None]
        projection_coverage_by_position[pos] = {"total": len(pos_players), "projected": len(pos_projected)}

    output = {
        "draft_group_id": draft_group_id,
        "slate_date": pool.slate_date,
        "slate_name": pool.slate_name,
        "source_provenance": pool.source_provenance,
        "salary_cap": 50000,
        "current_season": ctx["current_season"],
        "current_week": ctx["current_week"],
        "prior_season": ctx["prior_season"],
        "current_completed_weeks": ctx["current_completed_weeks"],
        "games": game_rows,
        "game_count": len(game_rows),
        "player_count": len(players),
        "position_counts": position_counts,
        "identity": {"total": len(players), "resolved": resolved_count, "unresolved": len(players) - resolved_count},
        "projection_coverage": projection_coverage_by_position,
        "projection_error": projection_error,
        "vegas_configured": game_ctx_result.odds_fetch.source_provenance != "not_configured",
        "vegas_source_provenance": game_ctx_result.odds_fetch.source_provenance,
        "players": players,
    }
    print(json.dumps(output, default=str))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python scripts/nfl_dashboard_data.py <draft_group_id>"}))
        sys.exit(2)
    sys.exit(main(int(sys.argv[1])))
