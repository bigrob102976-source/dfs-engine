"""NFL M14 -- the real late-swap bridge the dashboard's Late Swap UI
calls. Rebuilds the CURRENT live pool (same real fetch path as
scripts/nfl_dashboard_optimize.py -- never a second/stale pool), then
runs nfl/late_swap.py's run_late_swap() against a saved lineup, which
itself reuses the EXISTING nfl/solver.py CP-SAT engine. Never a second
optimizer, never a fabricated result.

Usage:
    python scripts/nfl_dashboard_late_swap.py <draft_group_id> <request_json>

request_json:
{
  "savedLineup": { ...NflSavedLineup.to_dict() shape... },
  "settings": { ...same shape as nfl_dashboard_optimize.py's settings_json... },
  "nowUtc": "2026-09-13T18:00:00+00:00"   // optional -- defaults to the real current time; tests/simulation only
}
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftkings_unofficial import collector
from nfl.big_money_native_inference import build_current_nfl_projection_features, generate_projections
from nfl.game_context_builder import build_nfl_game_context
from nfl.late_swap import LateSwapError, run_late_swap
from nfl.optimizer_models import NflOptimizerPlayer, NflOptimizerSettings, NflStackConfig
from nfl.ownership_model import _usage_share_for_player, build_nfl_ownership_projections
from nfl.ownership_models import NflOwnershipInputPlayer
from nfl.pool_builder import NflPoolBuildError, build_pool
from nfl.saved_lineup_models import NflSavedLineup, SavedLineupCorruptionError
from nfl.solver import NflProjectionCoverageError
from nfl.constraints import NflOptimizerConfigError

SCORING_MODES = ("projection", "ceiling", "leverage")


def _parse_stack(raw: dict) -> NflStackConfig:
    return NflStackConfig(
        qb_stack_mode=raw.get("qbStackMode", "off"), bring_back_mode=raw.get("bringBackMode", "off"),
        rb_dst_enabled=bool(raw.get("rbDstEnabled", False)),
        max_players_per_team=raw.get("maxPlayersPerTeam"), max_players_per_game=raw.get("maxPlayersPerGame"),
    )


def main(draft_group_id: int, request: dict) -> int:
    try:
        saved = NflSavedLineup.from_dict(request["savedLineup"])
    except (KeyError, SavedLineupCorruptionError) as exc:
        print(json.dumps({"error": f"INVALID_SAVED_LINEUP: {exc}", "error_type": type(exc).__name__}))
        return 1

    settings_raw = request.get("settings", {})
    mode = settings_raw.get("mode", saved.mode)

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
    if mode in SCORING_MODES:
        try:
            ctx = build_current_nfl_projection_features(draft_group_id, slate_date)
            records = generate_projections(draft_group_id, slate_date, ctx=ctx)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"error": f"PROJECTIONS_UNAVAILABLE: {exc}"}))
            return 1
        projections_by_dk_id = {r.draftkings_player_id: r for r in records}
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
            proj = projections_by_dk_id.get(p.draftkings_player_id)
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
            ownership_by_dk_id = {r.draftkings_player_id: r for r in ownership_records}

    current_pool = [
        NflOptimizerPlayer(
            key=p.draftkings_player_id, name=p.name, team=p.team, opponent=p.opponent, game_id=p.game_id,
            position=p.position, roster_slots=p.roster_slots, salary=p.salary, is_team_entity=p.is_team_entity,
            draft_group_id=p.draft_group_id, slate_date=p.slate_date,
            projection=(projections_by_dk_id[p.draftkings_player_id].projection if p.draftkings_player_id in projections_by_dk_id else None),
            ceiling=(projections_by_dk_id[p.draftkings_player_id].ceiling if p.draftkings_player_id in projections_by_dk_id else None),
            projected_ownership=(ownership_by_dk_id[p.draftkings_player_id].ownership_projection if p.draftkings_player_id in ownership_by_dk_id else None),
            leverage_score=(ownership_by_dk_id[p.draftkings_player_id].leverage_score if p.draftkings_player_id in ownership_by_dk_id else None),
            raw_status=p.status, game_start_time=p.game_start_time,
        )
        for p in pool.players
    ]

    settings = NflOptimizerSettings(
        mode=mode, num_lineups=1, locks=settings_raw.get("locks", []), excludes=settings_raw.get("excludes", []),
        stack=_parse_stack(settings_raw.get("stack", {})), max_exposure=settings_raw.get("maxExposure", {}),
        max_exposure_default=settings_raw.get("maxExposureDefault", 1.0), min_exposure=settings_raw.get("minExposure", {}),
    )

    now_utc_raw = request.get("nowUtc")
    now_utc = datetime.fromisoformat(now_utc_raw.replace("Z", "+00:00")) if now_utc_raw else datetime.now(timezone.utc)

    try:
        result = run_late_swap(saved, current_pool, settings, now_utc)
    except (LateSwapError, NflOptimizerConfigError, NflProjectionCoverageError, SavedLineupCorruptionError) as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}))
        return 1

    output = {
        "locked_slots": result.locked_slots, "unlocked_slots": result.unlocked_slots,
        "changed_player_keys": result.changed_player_keys, "fully_locked": result.fully_locked,
        "error": result.error,
        "lineup": None if result.lineup is None else {
            "total_salary": result.lineup.total_salary, "remaining_salary": result.lineup.remaining_salary,
            "total_projection": result.lineup.total_projection, "total_ceiling": result.lineup.total_ceiling,
            "sum_ownership": result.lineup.sum_ownership, "average_ownership": result.lineup.average_ownership,
            "total_leverage_score": result.lineup.total_leverage_score,
            "qb_stack_team": result.lineup.qb_stack_team, "qb_stack_receiver_count": result.lineup.qb_stack_receiver_count,
            "bring_back_player": result.lineup.bring_back_player, "rb_dst_team": result.lineup.rb_dst_team,
            "assignments": [
                {
                    "slot": a.slot, "draftkings_player_id": a.draftkings_player_id, "name": a.name,
                    "position": a.position, "team": a.team, "salary": a.salary,
                    "projected_ownership": a.projected_ownership, "ceiling": a.ceiling,
                    "locked": a.slot in result.locked_slots,
                }
                for a in result.lineup.assignments
            ],
        },
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python scripts/nfl_dashboard_late_swap.py <draft_group_id> <request_json>"}))
        sys.exit(2)
    sys.exit(main(int(sys.argv[1]), json.loads(sys.argv[2])))
