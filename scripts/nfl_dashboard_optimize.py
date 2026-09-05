"""NFL UI M1/M13 -- the real optimizer bridge the dashboard's NFL
Optimizer tab calls. Builds the real DK pool, attaches real Big Money
Native projections/ceiling and real ownership/leverage, and runs the
EXISTING nfl/solver.py CP-SAT solver -- never a duplicate/reimplemented
optimizer.

Never fakes feasibility: if data coverage can't fill every roster slot,
or locks/excludes/stack/exposure settings are contradictory, the real
error from nfl/solver.py is surfaced as-is, never swallowed into a
fabricated empty-but-successful result.

Usage:
    python scripts/nfl_dashboard_optimize.py <draft_group_id> <settings_json>

settings_json (all fields optional, sane defaults applied):
{
  "numLineups": 1,
  "mode": "roster_feasibility" | "projection" | "ceiling" | "leverage",
  "locks": ["<draftkings_player_id>", ...],
  "excludes": ["<draftkings_player_id>", ...],
  "stack": {
    "qbStackMode": "off" | "single" | "double",
    "bringBackMode": "off" | "one",
    "rbDstEnabled": false,
    "maxPlayersPerTeam": null | <int>,
    "maxPlayersPerGame": null | <int>
  },
  "maxExposure": {"<draftkings_player_id>": <0.0-1.0>, ...},
  "maxExposureDefault": 1.0,
  "minExposure": {"<draftkings_player_id>": <0.0-1.0>, ...}
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
from nfl.optimizer_models import NflOptimizerPlayer, NflOptimizerSettings, NflStackConfig
from nfl.ownership_model import _usage_share_for_player, build_nfl_ownership_projections
from nfl.ownership_models import NflOwnershipInputPlayer
from nfl.pool_builder import NflPoolBuildError, build_pool
from nfl.solver import NflProjectionCoverageError, generate_lineups
from nfl.constraints import NflOptimizerConfigError
from nfl.status import DEFAULT_EXCLUDE_BY_STATUS, normalize_status

SCORING_MODES = ("projection", "ceiling", "leverage")


def _parse_stack(raw: dict) -> NflStackConfig:
    return NflStackConfig(
        qb_stack_mode=raw.get("qbStackMode", "off"),
        bring_back_mode=raw.get("bringBackMode", "off"),
        rb_dst_enabled=bool(raw.get("rbDstEnabled", False)),
        max_players_per_team=raw.get("maxPlayersPerTeam"),
        max_players_per_game=raw.get("maxPlayersPerGame"),
    )


def main(draft_group_id: int, settings_raw: dict) -> int:
    universe = collector.collect_sport_universe("NFL")
    if universe.status != collector.STATUS_OK:
        print(json.dumps({"error": f"DISCOVERY_FAILED: {universe.status} ({universe.error})"}))
        return 1
    slate = next((s for s in universe.slates if s.draft_group_id == draft_group_id), None)
    if slate is None:
        print(json.dumps({"error": f"DraftGroup {draft_group_id} not found in current NFL universe."}))
        return 1
    slate_date = collector.slate_local_date(slate)

    mode = settings_raw.get("mode", "roster_feasibility")

    try:
        pool = build_pool(slate_date, draft_group_id, sport_code="NFL")
    except NflPoolBuildError as exc:
        print(json.dumps({"error": f"BUILD_POOL_FAILED: {exc}"}))
        return 1

    projections_by_dk_id = {}
    ownership_by_dk_id = {}
    if mode in SCORING_MODES:
        try:
            # NFL M12/M13: builds the SAME ctx generate_projections()
            # would otherwise build internally (usage/game-context
            # features), reused here for ownership's usage/Vegas inputs
            # too -- one fetch, not two.
            ctx = build_current_nfl_projection_features(draft_group_id, slate_date)
            records = generate_projections(draft_group_id, slate_date, ctx=ctx)
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
            ownership_by_dk_id = {r.draftkings_player_id: r for r in ownership_records}
        projections_by_dk_id = projection_records_by_dk_id

    optimizer_players = [
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

    locks = settings_raw.get("locks", [])
    explicit_excludes = set(settings_raw.get("excludes", []))
    # NFL M14 Phase 9/10 -- OUT/INACTIVE/IR excluded by default (never a
    # locked player, whose explicit lock always wins -- see nfl/status.py's
    # module docstring for the full real-status-vocabulary rationale).
    # QUESTIONABLE/UNKNOWN stay eligible, flagged in the UI via status_info
    # on /api/nfl/data, never silently dropped here.
    status_excludes = {
        p.draftkings_player_id for p in pool.players
        if p.draftkings_player_id not in locks and DEFAULT_EXCLUDE_BY_STATUS.get(normalize_status(p.status), False)
    }

    settings = NflOptimizerSettings(
        mode=mode,
        num_lineups=settings_raw.get("numLineups", 1),
        locks=locks,
        excludes=list(explicit_excludes | status_excludes),
        stack=_parse_stack(settings_raw.get("stack", {})),
        max_exposure=settings_raw.get("maxExposure", {}),
        max_exposure_default=settings_raw.get("maxExposureDefault", 1.0),
        min_exposure=settings_raw.get("minExposure", {}),
    )

    try:
        result = generate_lineups(optimizer_players, settings)
    except (NflOptimizerConfigError, NflProjectionCoverageError) as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}))
        return 1

    output = {
        "requested": result.requested, "generated": result.generated, "stopped_reason": result.stopped_reason,
        "mode": mode, "status_excluded_count": len(status_excludes),
        "lineups": [
            {
                "index": lu.index, "total_salary": lu.total_salary, "remaining_salary": lu.remaining_salary,
                "total_projection": lu.total_projection, "total_ceiling": lu.total_ceiling,
                "sum_ownership": lu.sum_ownership, "average_ownership": lu.average_ownership,
                "total_leverage_score": lu.total_leverage_score,
                "qb_stack_team": lu.qb_stack_team, "qb_stack_receiver_count": lu.qb_stack_receiver_count,
                "bring_back_player": lu.bring_back_player, "rb_dst_team": lu.rb_dst_team,
                "assignments": [
                    {
                        "slot": a.slot, "draftkings_player_id": a.draftkings_player_id, "name": a.name,
                        "position": a.position, "team": a.team, "salary": a.salary,
                        "projected_ownership": a.projected_ownership, "ceiling": a.ceiling,
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
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python scripts/nfl_dashboard_optimize.py <draft_group_id> [settings_json]"}))
        sys.exit(2)
    draft_group_id_arg = int(sys.argv[1])
    settings_json_arg = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else {}
    sys.exit(main(draft_group_id_arg, settings_json_arg))
