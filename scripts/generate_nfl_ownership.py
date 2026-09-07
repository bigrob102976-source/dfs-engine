"""NFL M12 -- generates and PERSISTS one Big Money Native NFL ownership
snapshot for a real DraftGroup. Mirrors scripts/nfl_dashboard_data.py's
exact real-data pipeline (same pool, same projections, same usage/game
context -- never a second/different fetch), but additionally writes an
immutable, timestamped artifact via nfl/ownership_persistence.py, which
the live dashboard bridge deliberately does NOT do on every request
(same "compute live, persist offline" split NFL M4's projection
persistence module already established and left unwired from the
dashboard path).

Usage:
    python scripts/generate_nfl_ownership.py <draft_group_id>
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draftkings_unofficial import collector
from nfl.big_money_native_inference import build_current_nfl_projection_features, generate_projections
from nfl.game_context_builder import build_nfl_game_context
from nfl.ownership_model import _usage_share_for_player, build_nfl_ownership_projections
from nfl.ownership_models import NflOwnershipInputPlayer, NflOwnershipSnapshot
from nfl.ownership_persistence import save_nfl_ownership_snapshot
from nfl.ownership_validator import validate_ownership
from nfl.pool_builder import NflPoolBuildError


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
    game_ctx_result = build_nfl_game_context(pool.players, draft_group_id, pool.slate_date)
    games_by_id = {g.canonical_game_id: g for g in game_ctx_result.match_result.games}

    try:
        projection_records = generate_projections(draft_group_id, slate_date, ctx=ctx)
    except Exception as exc:  # noqa: BLE001 -- honestly reported, never crashes
        print(json.dumps({"error": f"PROJECTIONS_UNAVAILABLE: {exc}"}))
        return 1
    projections_by_dk_id = {r.draftkings_player_id: r for r in projection_records}

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

    if not ownership_input_players:
        print(json.dumps({"error": "No players with a usable projection -- nothing to estimate ownership from."}))
        return 1

    generated_at = datetime.now(timezone.utc).isoformat()
    records, normalization_report = build_nfl_ownership_projections(
        ownership_input_players, draft_group_id, slate_date, pool.source_provenance, generated_at,
    )
    validation = validate_ownership(len(pool.players), records)

    snapshot = NflOwnershipSnapshot(
        sport="NFL", draft_group_id=draft_group_id, slate_date=slate_date,
        source=records[0].source, source_provenance=pool.source_provenance,
        method=records[0].method, model_version=records[0].model_version, generated_at=generated_at,
        records=records, validation=validation, normalization_report=normalization_report,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = save_nfl_ownership_snapshot(snapshot, timestamp)

    print(json.dumps({
        "draft_group_id": draft_group_id, "slate_date": slate_date,
        "saved_path": str(path), "player_count": len(pool.players),
        "ownership_generated": len(records), "validation_passed": validation.passed,
        "validation_findings": [f.to_dict() for f in validation.findings],
        "normalization_report": normalization_report,
    }, indent=2))
    return 0 if validation.passed else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python scripts/generate_nfl_ownership.py <draft_group_id>"}))
        sys.exit(2)
    sys.exit(main(int(sys.argv[1])))
