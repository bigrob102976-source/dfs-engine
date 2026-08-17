"""CLI entry point: run the Native Projection Model for a slate date.

    Pitcher/Batter Board Snapshots (+ optional Game Environment, + optional
    DK player pool for salary) -> reconstruct PitcherInput/BatterInput
    -> native_projections (playing_time -> rates -> dk_scoring -> matchup
    -> uncertainty -> validation) -> Native Projection Snapshot

    python scripts/run_native_projection_engine.py --date YYYY-MM-DD

Mirrors scripts/run_ai_projection_engine.py's shape and NO-EXTERNAL
-DEPENDENCY guarantee: requires at least one of the pitcher/batter board
snapshots (the same Independent-Projection research data every projection
in this codebase starts from); Game Environment and the DK pool are both
optional (missing either just means fewer signals fire / no salary field,
never a hard failure). Never touches external_projections/ or evaluation/
-- see tests/test_architecture_separation.py.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.snapshot_selection import select_snapshot  # noqa: E402
from models.batter import (  # noqa: E402
    BatterInput,
    OpposingPitcherContext,
    PlatoonSplitStats,
    RecentBattingStats,
    SeasonBattingStats,
    TrendMetrics as BatterTrendMetrics,
)
from models.pitcher import (  # noqa: E402
    Availability,
    GameContext,
    OpponentStats,
    PitcherInput,
    RecentStats,
    SeasonStats,
    TrendMetrics as PitcherTrendMetrics,
)
from projection_engine.persistence import load_latest_dfs_pool  # noqa: E402
from research.game_environment.storage import list_environment_reports, load_environment_report  # noqa: E402

from native_projections.hitter_projection import project_hitter  # noqa: E402
from native_projections.matchup import build_opposing_lineup_index  # noqa: E402
from native_projections.models import NativeProjectionDocument  # noqa: E402
from native_projections.persistence import save_native_projection_document  # noqa: E402
from native_projections.pitcher_projection import project_pitcher  # noqa: E402
from native_projections.version import NATIVE_PROJECTION_MODEL_VERSION  # noqa: E402


def _pitcher_input_from_record(record: dict, salary: Optional[int]) -> PitcherInput:
    return PitcherInput(
        player_id=str(record["player_id"]),
        name=record.get("name", ""),
        team=record.get("team", ""),
        opponent=record.get("opponent", ""),
        salary=salary,
        game_id=record.get("game_id"),
        venue_name=record.get("venue"),
        season=SeasonStats(**record.get("season_metrics", {})),
        recent=RecentStats(**record.get("recent_metrics", {})),
        opponent_stats=OpponentStats(**record.get("opponent_metrics", {})),
        game=GameContext(**record.get("game_metrics", {})),
        availability=Availability(**record.get("availability_metrics", {})),
        trends=PitcherTrendMetrics(**record.get("trend_metrics", {})),
    )


def _batter_input_from_record(record: dict, salary: Optional[int]) -> BatterInput:
    return BatterInput(
        player_id=str(record["player_id"]),
        name=record.get("name", ""),
        team=record.get("team", ""),
        opponent=record.get("opponent", ""),
        game_id=record.get("game_id"),
        venue_name=record.get("venue"),
        batting_hand=record.get("batting_hand"),
        batting_order=record.get("batting_order"),
        position=record.get("position"),
        salary=salary,
        season=SeasonBattingStats(**record.get("season_metrics", {})),
        recent=RecentBattingStats(**record.get("recent_metrics", {})),
        vs_rhp=PlatoonSplitStats(**record.get("vs_rhp", {})),
        vs_lhp=PlatoonSplitStats(**record.get("vs_lhp", {})),
        opposing_pitcher=OpposingPitcherContext(**record.get("opposing_pitcher", {})),
        trends=BatterTrendMetrics(**record.get("trend_metrics", {})),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Native Projection Model for a slate date.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--predictions-root", default="predictions")
    args = parser.parse_args()

    pitcher_snapshot, pitcher_snapshot_path = select_snapshot(None, args.date, Path(args.predictions_root), "pitcher_board")
    batter_snapshot, batter_snapshot_path = select_snapshot(None, args.date, Path(args.predictions_root), "batter_board")
    if pitcher_snapshot is None and batter_snapshot is None:
        print(json.dumps({"status": "no_research", "reason": f"No pitcher or batter snapshot found for {args.date}. Run the Pitcher/Batter Agent first."}))
        return

    environment_reports = list_environment_reports(args.date)
    environment_report = load_environment_report(environment_reports[-1]) if environment_reports else None
    environment_snapshot_path = str(environment_reports[-1]) if environment_reports else None

    pool_doc = load_latest_dfs_pool(args.date)
    salary_by_player_id: Dict[str, int] = {}
    if pool_doc:
        for row in pool_doc.get("players", []):
            if row.get("mlb_player_id") and row.get("salary") is not None:
                salary_by_player_id[str(row["mlb_player_id"])] = row["salary"]

    games_by_id: Dict[str, dict] = {}
    if environment_report:
        for g in environment_report.get("games", []):
            if g.get("game_id"):
                games_by_id[g["game_id"]] = g

    pitcher_inputs = [
        _pitcher_input_from_record(r, salary_by_player_id.get(str(r["player_id"])))
        for r in (pitcher_snapshot or {}).get("pitchers", [])
    ]
    batter_inputs = [
        _batter_input_from_record(r, salary_by_player_id.get(str(r["player_id"])))
        for r in (batter_snapshot or {}).get("hitters", [])
    ]

    opposing_lineup_index = build_opposing_lineup_index(batter_inputs)

    generated_at = datetime.now(timezone.utc).isoformat()
    players: List = []

    for b in batter_inputs:
        game_report = games_by_id.get(b.game_id)
        proj = project_hitter(
            b,
            game_environment=game_report,
            generated_at=generated_at,
            source_batter_snapshot_path=batter_snapshot_path,
            source_environment_snapshot_path=environment_snapshot_path,
        )
        players.append(proj)

    for p in pitcher_inputs:
        opposing_lineup = opposing_lineup_index.get(p.opponent)
        game_report = games_by_id.get(p.game_id)
        proj = project_pitcher(
            p,
            opposing_lineup=opposing_lineup,
            game_environment=game_report,
            generated_at=generated_at,
            source_pitcher_snapshot_path=pitcher_snapshot_path,
            source_environment_snapshot_path=environment_snapshot_path,
        )
        players.append(proj)

    warnings: List[str] = []
    for proj in players:
        for w in proj.warnings:
            warnings.append(f"{proj.name} ({proj.player_type}): {w}")

    document = NativeProjectionDocument(
        slate_date=args.date,
        generated_at=generated_at,
        model_version=NATIVE_PROJECTION_MODEL_VERSION,
        pitcher_snapshot_path=pitcher_snapshot_path,
        batter_snapshot_path=batter_snapshot_path,
        environment_snapshot_path=environment_snapshot_path,
        player_count=len(players),
        players=players,
        warnings=warnings,
    )

    path = save_native_projection_document(document)

    hitters = [p for p in players if p.player_type == "hitter"]
    pitchers = [p for p in players if p.player_type == "pitcher"]

    print(f"Native Projection Model version: {NATIVE_PROJECTION_MODEL_VERSION}")
    print(f"Hitters projected: {len(hitters)}")
    print(f"Pitchers projected: {len(pitchers)}")
    print(f"Warnings: {len(warnings)}")
    if hitters:
        top_hitter = max(hitters, key=lambda p: p.native_projection)
        print(f"Top hitter: {top_hitter.name} ({top_hitter.native_projection:.2f})")
    if pitchers:
        top_pitcher = max(pitchers, key=lambda p: p.native_projection)
        print(f"Top pitcher: {top_pitcher.name} ({top_pitcher.native_projection:.2f})")
    print(f"\nSaved: {path}")
    print(json.dumps({"status": "ready", "path": str(path), "hitter_count": len(hitters), "pitcher_count": len(pitchers), "warning_count": len(warnings)}))


if __name__ == "__main__":
    main()
