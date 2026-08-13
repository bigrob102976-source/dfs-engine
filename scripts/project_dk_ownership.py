"""CLI entry point: project DraftKings MLB ownership for every active
player on a saved DFS player pool.

    DK Player Pool + Projections + Salary + Position + Batting Order + Team/Game Context
        -> Ownership Feature Builder -> Ownership Model -> Projected Ownership
        -> Ownership Snapshot -> (optimizer/optimize_dk_lineups.py --ownership consumes it next)

Usage:
    python scripts/project_dk_ownership.py --date YYYY-MM-DD --pool dfs_input/YYYY-MM-DD/dk_player_pool_<timestamp>.json

projected_ownership is a MODEL PREDICTION -- see ownership/__init__.py.
Never presented or persisted as actual/field ownership.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.ownership_config import CHALK_OWNERSHIP_THRESHOLD, OWNERSHIP_MODEL_VERSION
from ownership.model import build_ownership_projections
from ownership.models import OwnershipInputPlayer
from ownership.persistence import build_ownership_document, save_ownership_document
from ownership.validator import validate_ownership_projections
from research.prediction_snapshot import timestamp_tag

TOP_N = 10


def _load_pool(pool_path: str) -> dict:
    with Path(pool_path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_input_players(pool_doc: dict):
    pitchers, hitters = [], []
    active_count = 0
    for record in pool_doc.get("players", []):
        if record.get("lineup_status") != "active":
            continue
        active_count += 1
        if record.get("projection") is None or record.get("ceiling") is None:
            continue
        player = OwnershipInputPlayer(
            dk_player_id=record["dk_player_id"], mlb_player_id=record.get("mlb_player_id"), name=record["name"],
            team=record["team"], opponent=record.get("opponent"), game_id=record.get("game_id"),
            player_type=record["player_type"], dk_positions=list(record.get("dk_positions") or []),
            salary=record["salary"], projection=record["projection"], ceiling=record["ceiling"],
            overall_score=record.get("overall_score"), risk_score=record.get("risk_score"),
            confidence=record.get("confidence"), batting_order=record.get("batting_order"),
            season_sample_size=record.get("season_sample_size"), tags=list(record.get("tags") or []),
        )
        (pitchers if player.player_type == "pitcher" else hitters).append(player)
    total_rows = len(pool_doc.get("players", []))
    lineup_fraction = (active_count / total_rows) if total_rows else 0.0
    return pitchers, hitters, lineup_fraction


def _fmt(value, digits=1):
    return f"{value:.{digits}f}" if value is not None else "--"


def main() -> None:
    parser = argparse.ArgumentParser(description="Project DraftKings MLB ownership from a saved DFS player pool.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--pool", required=True, help="Path to a dk_player_pool_<timestamp>.json file")
    parser.add_argument("--output-root", default="ownership_predictions")
    args = parser.parse_args()

    pool_doc = _load_pool(args.pool)
    pitchers, hitters, lineup_fraction = _build_input_players(pool_doc)

    print("=" * 70)
    print("MLB DFS PROJECTED OWNERSHIP")
    print("=" * 70)
    print(f"\nSlate: {args.date}")
    print(f"Model Version: {OWNERSHIP_MODEL_VERSION}")
    print(f"Active Players: {len(pitchers) + len(hitters)} ({len(pitchers)} pitchers, {len(hitters)} hitters)")
    print()

    projections, team_popularity, normalization_report = build_ownership_projections(pitchers, hitters, lineup_fraction)

    pitcher_rows = sorted([p for p in projections if p.player_type == "pitcher"], key=lambda p: -p.projected_ownership)
    hitter_rows = sorted([p for p in projections if p.player_type == "hitter"], key=lambda p: -p.projected_ownership)

    print("TOP OWNED PITCHERS")
    print()
    header = f"{'Rk':<3} {'Pitcher':<22} {'Salary':>7} {'Proj':>6} {'Own%':>6} {'Chalk':>6} {'Lev':>6} {'Conf':>6}"
    print(header)
    print("-" * len(header))
    for rank, p in enumerate(pitcher_rows[:TOP_N], start=1):
        print(f"{rank:<3} {p.name:<22} {p.salary:>7} {_fmt(p.projection):>6} {_fmt(p.projected_ownership):>6} "
              f"{_fmt(p.chalk_score):>6} {_fmt(p.leverage_score):>6} {_fmt(p.ownership_confidence):>6}")
    print()

    print("TOP OWNED HITTERS")
    print()
    header = f"{'Rk':<3} {'Hitter':<22} {'Team':<5} {'Ord':>3} {'Salary':>7} {'Proj':>6} {'Own%':>6} {'Lev':>6}"
    print(header)
    print("-" * len(header))
    for rank, h in enumerate(hitter_rows[:TOP_N], start=1):
        order = h.batting_order if h.batting_order is not None else "--"
        print(f"{rank:<3} {h.name:<22} {h.team:<5} {order:>3} {h.salary:>7} "
              f"{_fmt(h.projection):>6} {_fmt(h.projected_ownership):>6} {_fmt(h.leverage_score):>6}")
    print()

    print("TOP LEVERAGE")
    print()
    header = f"{'Rk':<3} {'Player':<22} {'Proj':>6} {'Ceil':>6} {'Own%':>6} {'Lev':>6}"
    print(header)
    print("-" * len(header))
    for rank, p in enumerate(sorted(projections, key=lambda p: -p.leverage_score)[:TOP_N], start=1):
        print(f"{rank:<3} {p.name:<22} {_fmt(p.projection):>6} {_fmt(p.ceiling):>6} {_fmt(p.projected_ownership):>6} {_fmt(p.leverage_score):>6}")
    print()

    print("LOW-OWNED CEILING")
    print()
    header = f"{'Rk':<3} {'Player':<22} {'Ceil':>6} {'Own%':>6} {'Lev':>6}"
    print(header)
    print("-" * len(header))
    low_owned_ceiling = sorted(
        projections, key=lambda p: -(p.feature_breakdown.get("ceiling_percentile", 0.0) - p.projected_ownership)
    )
    for rank, p in enumerate(low_owned_ceiling[:TOP_N], start=1):
        print(f"{rank:<3} {p.name:<22} {_fmt(p.ceiling):>6} {_fmt(p.projected_ownership):>6} {_fmt(p.leverage_score):>6}")
    print()

    print("TOP PROJECTED STACK OWNERSHIP")
    print()
    header = f"{'Team':<6} {'Team Popularity':>16} {'Aggregate Proj. Own%':>22}"
    print(header)
    print("-" * len(header))
    for team, stats in sorted(team_popularity.items(), key=lambda kv: -kv[1].team_popularity_score)[:TOP_N]:
        print(f"{team:<6} {_fmt(stats.team_popularity_score):>16} {_fmt(stats.aggregate_projected_ownership):>22}")
    print()

    print("QUALITY CHECK")
    print()
    pitcher_diff = normalization_report["pitcher_ownership_sum"] - normalization_report["pitcher_ownership_expected"]
    hitter_diff = normalization_report["hitter_ownership_sum"] - normalization_report["hitter_ownership_expected"]
    print(f"Pitcher ownership sum: {normalization_report['pitcher_ownership_sum']}")
    print(f"Expected: {normalization_report['pitcher_ownership_expected']}")
    print(f"Difference: {pitcher_diff:.2f}")
    print()
    print(f"Hitter ownership sum: {normalization_report['hitter_ownership_sum']}")
    print(f"Expected: {normalization_report['hitter_ownership_expected']}")
    print(f"Difference: {hitter_diff:.2f}")
    print()
    print(f"Players > 100%: {normalization_report['players_above_100']}")
    print(f"Players < 0%: {normalization_report['players_below_0']}")
    print()

    violations = validate_ownership_projections(projections)
    if violations:
        print(f"INDEPENDENT VALIDATION FAILED ({len(violations)} issue(s)):")
        for v in violations:
            print(f"  - {v}")
    else:
        print("Independent validation: PASSED.")
    print()

    generated_at = datetime.now(timezone.utc).isoformat()
    ts = timestamp_tag(generated_at)
    document = build_ownership_document(
        args.date, generated_at, OWNERSHIP_MODEL_VERSION, args.pool,
        pool_doc.get("pitcher_snapshot_path"), pool_doc.get("batter_snapshot_path"),
        projections, team_popularity, normalization_report,
    )
    path = save_ownership_document(document, args.date, ts, output_root=args.output_root)
    print(f"Ownership snapshot saved (immutable): {path}")


if __name__ == "__main__":
    main()
