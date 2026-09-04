"""NFL UI M1 -- the real optimizer bridge the dashboard's NFL Optimizer
tab calls. Builds the real DK pool, attaches real Big Money Native
projections, and runs the EXISTING nfl/solver.py CP-SAT solver --
never a duplicate/reimplemented optimizer.

Never fakes feasibility: if projection coverage can't fill every roster
slot, or locks/excludes are contradictory, the real error from
nfl/solver.py is surfaced as-is, never swallowed into a fabricated
empty-but-successful result.

Usage:
    python scripts/nfl_dashboard_optimize.py <draft_group_id> <num_lineups> [mode] [locks_csv] [excludes_csv]
    mode: "roster_feasibility" (default) or "projection"
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftkings_unofficial import collector
from nfl.big_money_native_inference import build_current_nfl_projection_features, generate_projections
from nfl.game_context_builder import build_nfl_game_context
from nfl.optimizer_models import NflOptimizerPlayer, NflOptimizerSettings
from nfl.ownership_model import _usage_share_for_player, build_nfl_ownership_projections
from nfl.ownership_models import NflOwnershipInputPlayer
from nfl.pool_builder import NflPoolBuildError, build_pool
from nfl.solver import NflOptimizerConfigError, NflProjectionCoverageError, generate_lineups


def main(draft_group_id: int, num_lineups: int, mode: str, locks: list, excludes: list) -> int:
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
        pool = build_pool(slate_date, draft_group_id, sport_code="NFL")
    except NflPoolBuildError as exc:
        print(json.dumps({"error": f"BUILD_POOL_FAILED: {exc}"}))
        return 1

    projections_by_dk_id = {}
    ownership_by_dk_id = {}
    if mode == "projection":
        try:
            # NFL M12: builds the SAME ctx generate_projections() would
            # otherwise build internally (usage/game-context features),
            # reused here for ownership's usage/Vegas inputs too -- one
            # fetch, not two.
            ctx = build_current_nfl_projection_features(draft_group_id, slate_date)
            records = generate_projections(draft_group_id, slate_date, ctx=ctx)
            projections_by_dk_id = {r.draftkings_player_id: r.projection for r in records}
        except Exception as exc:  # noqa: BLE001 -- real, reportable failure, never silently falls back
            print(json.dumps({"error": f"PROJECTIONS_UNAVAILABLE: {exc}"}))
            return 1

        projection_records_by_dk_id = {r.draftkings_player_id: r for r in records}
        game_ctx_result = build_nfl_game_context(pool.players, draft_group_id, pool.slate_date)
        games_by_id = {g.canonical_game_id: g for g in game_ctx_result.match_result.games}
        usage_by_dk_id = {f.draftkings_player_id: f for f in ctx["join_result"].features}
        team_implied_total = {}
        for g in games_by_id.values():
            if g.home_team:
                team_implied_total[g.home_team] = g.home_implied_total
            if g.away_team:
                team_implied_total[g.away_team] = g.away_implied_total

        ownership_input_players = []
        for p in pool.players:
            proj = projection_records_by_dk_id.get(p.draftkings_player_id)
            if proj is None or proj.projection is None:
                continue
            usage = usage_by_dk_id.get(p.draftkings_player_id)
            usage_share = _usage_share_for_player(
                p.position, usage.rolling if usage else None, usage.season_to_date if usage else None,
            )
            ownership_input_players.append(NflOwnershipInputPlayer(
                draftkings_player_id=p.draftkings_player_id, name=p.name, position=p.position, team=p.team,
                opponent=p.opponent, salary=p.salary, projection=proj.projection, ceiling=proj.ceiling,
                usage_share=usage_share, team_implied_total=team_implied_total.get(p.team),
                opponent_implied_total=(team_implied_total.get(p.opponent) if p.opponent else None),
            ))
        if ownership_input_players:
            ownership_records, _ = build_nfl_ownership_projections(
                ownership_input_players, draft_group_id, slate_date, pool.source_provenance,
                datetime.now(timezone.utc).isoformat(),
            )
            ownership_by_dk_id = {r.draftkings_player_id: r.ownership_projection for r in ownership_records}

    optimizer_players = [
        NflOptimizerPlayer(
            key=p.draftkings_player_id, name=p.name, team=p.team, opponent=p.opponent, game_id=p.game_id,
            position=p.position, roster_slots=p.roster_slots, salary=p.salary, is_team_entity=p.is_team_entity,
            draft_group_id=p.draft_group_id, slate_date=p.slate_date,
            projection=projections_by_dk_id.get(p.draftkings_player_id),
            projected_ownership=ownership_by_dk_id.get(p.draftkings_player_id),
        )
        for p in pool.players
    ]

    settings = NflOptimizerSettings(mode=mode, num_lineups=num_lineups, locks=locks, excludes=excludes)

    try:
        result = generate_lineups(optimizer_players, settings)
    except (NflOptimizerConfigError, NflProjectionCoverageError) as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}))
        return 1

    output = {
        "requested": result.requested, "generated": result.generated, "stopped_reason": result.stopped_reason,
        "mode": mode,
        "lineups": [
            {
                "index": lu.index, "total_salary": lu.total_salary, "remaining_salary": lu.remaining_salary,
                "total_projection": lu.total_projection,
                "assignments": [
                    {
                        "slot": a.slot, "draftkings_player_id": a.draftkings_player_id, "name": a.name,
                        "position": a.position, "team": a.team, "salary": a.salary,
                        "projected_ownership": a.projected_ownership,
                    }
                    for a in lu.assignments
                ],
            }
            for lu in result.lineups
        ],
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python scripts/nfl_dashboard_optimize.py <draft_group_id> <num_lineups> [mode] [locks_csv] [excludes_csv]"}))
        sys.exit(2)
    draft_group_id_arg = int(sys.argv[1])
    num_lineups_arg = int(sys.argv[2])
    mode_arg = sys.argv[3] if len(sys.argv) > 3 else "roster_feasibility"
    locks_arg = sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else []
    excludes_arg = sys.argv[5].split(",") if len(sys.argv) > 5 and sys.argv[5] else []
    sys.exit(main(draft_group_id_arg, num_lineups_arg, mode_arg, locks_arg, excludes_arg))
