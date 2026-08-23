"""CLI entry point: fetch BlueCollar DFS MLB DraftKings projections for
one real DK slate, match the correct BlueCollar slate, resolve player
identity, and save an immutable snapshot.

Usage:
    python scripts/fetch_bluecollar_projections.py --date YYYY-MM-DD --slate-id <dk_slate_id>

BlueCollar is OPTIONAL and this script never fails the caller's
pipeline: every outcome (not configured, no research package yet, API
error, slate match ambiguous/failed, or success) exits 0 and prints a
final JSON status line, mirroring
scripts/fetch_fantasypros_projections.py's own "best-effort, never
blocks the slate" convention. Only a genuinely unexpected exception (a
real bug) would produce a non-zero exit.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bluecollar.build import (  # noqa: E402
    STATUS_API_ERROR,
    STATUS_NOT_CONFIGURED,
    STATUS_NO_RESEARCH,
    STATUS_READY,
    STATUS_SLATE_MATCH_FAILED,
    build_bluecollar_snapshot,
)
from bluecollar.persistence import save_bluecollar_snapshot  # noqa: E402
from research.prediction_snapshot import timestamp_tag  # noqa: E402


def _find_latest_provider_slate(date: str, dfs_input_root: str):
    folder = Path(dfs_input_root) / date
    if not folder.exists():
        return None
    matches = sorted(folder.glob("provider_slate_*.json"))
    return matches[-1] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch BlueCollar DFS MLB DraftKings projections for one real DK slate and save a snapshot.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-id", required=True, help="The DK slate_id (from provider_slate_<ts>.json) to fetch/match BlueCollar projections for")
    parser.add_argument("--output", default="research_output", help="Research package root directory")
    parser.add_argument("--dfs-input-root", default="dfs_input")
    parser.add_argument("--provider-slate", default=None, help="Explicit provider_slate_<ts>.json path (default: latest for --date)")
    args = parser.parse_args()

    print("=" * 70)
    print("BLUECOLLAR DFS PROJECTIONS")
    print("=" * 70)

    slate_path = Path(args.provider_slate) if args.provider_slate else _find_latest_provider_slate(args.date, args.dfs_input_root)
    if slate_path is None or not slate_path.exists():
        print(f"\nBLUECOLLAR: SKIPPED -- no provider slate artifact found for {args.date} under {args.dfs_input_root}/.")
        print(json.dumps({"status": "no_dk_slate"}))
        return

    with slate_path.open("r", encoding="utf-8") as f:
        slate_doc = json.load(f)

    dk_slate = next((s for s in slate_doc.get("slates", []) if s.get("slate_id") == args.slate_id), None)
    if dk_slate is None:
        print(f"\nBLUECOLLAR: SKIPPED -- DK slate {args.slate_id!r} not found in {slate_path}.")
        print(json.dumps({"status": "no_dk_slate"}))
        return

    result = build_bluecollar_snapshot(dk_slate, args.date, args.output)

    if result["status"] == STATUS_NOT_CONFIGURED:
        print("\nBLUECOLLAR: NOT CONFIGURED (BLUECOLLAR_API_KEY is not set -- this is optional, skipping).")
        print(json.dumps({"status": "not_configured"}))
        return

    if result["status"] == STATUS_NO_RESEARCH:
        print(f"\nBLUECOLLAR: SKIPPED -- {result['error']}")
        print(json.dumps({"status": "no_research", "reason": result["error"]}))
        return

    if result["status"] == STATUS_API_ERROR:
        print(f"\nBLUECOLLAR API ERROR -- {result['error']}")
        print(json.dumps({"status": "api_error", "reason": result["error"]}))
        return

    if result["status"] == STATUS_SLATE_MATCH_FAILED:
        print(f"\nBLUECOLLAR NOT UPDATED -- {result['error']}")
        print(json.dumps({"status": "slate_match_failed", "reason": result["error"]}))
        return

    assert result["status"] == STATUS_READY
    snapshot = result["snapshot"]
    path = save_bluecollar_snapshot(snapshot.to_dict(), args.date, args.slate_id, timestamp_tag(snapshot.retrieved_at))

    print(f"DK slate: {args.slate_id}")
    print(f"BlueCollar slate: {snapshot.bluecollar_slate_id} ({snapshot.bluecollar_slate_name!r})")
    print(f"BlueCollar updated: {snapshot.bluecollar_updated}")
    print(f"Players: {snapshot.player_count} (matched: {snapshot.matched_count}, usable projections: {snapshot.usable_projection_count})")
    print(f"\nSaved: {path}")
    print(json.dumps({
        "status": "ready", "path": str(path),
        "dk_slate_id": args.slate_id,
        "bluecollar_slate_id": snapshot.bluecollar_slate_id,
        "bluecollar_slate_name": snapshot.bluecollar_slate_name,
        "bluecollar_updated": snapshot.bluecollar_updated,
        "player_count": snapshot.player_count,
        "matched_count": snapshot.matched_count,
        "usable_projection_count": snapshot.usable_projection_count,
    }))


if __name__ == "__main__":
    main()
