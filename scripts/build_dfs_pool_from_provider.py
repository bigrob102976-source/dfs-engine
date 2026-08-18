"""CLI entry point: build a unified DFS player pool from the latest
provider-fetched DFS slate artifact (scripts/fetch_dfs_slate.py) -- the
automatic replacement for scripts/build_dk_player_pool.py's manual
--csv flag (Milestone 13's one-click pipeline, steps 5-6).

This is the ONLY thing that changes vs. the CSV path: where the rows
come from. Matching, slate validation, pool assembly, roster
feasibility, and persistence are the exact same dfs/pool_builder.py
code the CSV script uses -- see that module's docstring.

Usage:
    python scripts/build_dfs_pool_from_provider.py --date YYYY-MM-DD
    python scripts/build_dfs_pool_from_provider.py --date YYYY-MM-DD --provider-slate dfs_input/YYYY-MM-DD/provider_slate_....json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.pool_builder import UnsafeSourceProvenanceError, build_pool, print_pool_report, save_pool
from dfs.providers.adapter import provider_players_to_dk_rows


def _find_latest_provider_slate(date: str, dfs_input_root: str) -> Path:
    folder = Path(dfs_input_root) / date
    if not folder.exists():
        return None
    matches = sorted(folder.glob("provider_slate_*.json"))
    return matches[-1] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a unified DFS player pool from the latest provider-fetched slate.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", default="research_output", help="Research package root directory")
    parser.add_argument("--predictions-root", default="predictions")
    parser.add_argument("--pitcher-snapshot", default=None)
    parser.add_argument("--batter-snapshot", default=None)
    parser.add_argument("--dfs-input-root", default="dfs_input")
    parser.add_argument("--provider-slate", default=None, help="Explicit provider_slate_<ts>.json path (default: latest for --date)")
    args = parser.parse_args()

    print("=" * 70)
    print("DFS PLAYER POOL FROM PROVIDER")
    print("=" * 70)

    slate_path = Path(args.provider_slate) if args.provider_slate else _find_latest_provider_slate(args.date, args.dfs_input_root)
    if slate_path is None or not slate_path.exists():
        print(f"\nERROR: No provider slate artifact found for {args.date} under {args.dfs_input_root}/. "
              f"Run scripts/fetch_dfs_slate.py --date {args.date} first.")
        sys.exit(1)

    with slate_path.open("r", encoding="utf-8") as f:
        slate_doc = json.load(f)

    print(f"\nProvider slate: {slate_path}")
    print(f"Provider: {slate_doc.get('provider_name')}")
    print(f"Status: {slate_doc['status']}")

    if slate_doc["status"] != "ready":
        print(f"\nDFS SALARIES: {slate_doc['status'].upper()}")
        if slate_doc.get("reason"):
            print(slate_doc["reason"])
        if slate_doc["status"] == "needs_selection":
            print("\nMultiple slates were discovered -- choose one and re-run:")
            for s in slate_doc.get("slates", []):
                print(f"  - {s['slate_id']}: {s.get('slate_name')} ({s.get('game_count')} games)")
            print("\npython scripts/fetch_dfs_slate.py --date " + args.date + " --slate-id <slate_id>")
        print("\nCannot build a player pool until a ready slate is selected.")
        sys.exit(1)

    dk_rows = provider_players_to_dk_rows(slate_doc["players"])
    print(f"Selected slate: {slate_doc.get('selected_slate_id')}")
    print(f"Players: {len(dk_rows)}\n")

    if not dk_rows:
        print("ERROR: The selected provider slate has zero players.")
        sys.exit(1)

    # Milestone 27.4: this slate's own source_provenance claim (from
    # DraftKingsCsvProvider/MockProvider's ProviderSlateInfo), so
    # build_pool() can refuse to build a production pool from a
    # synthetic/mock-contaminated source. `None` (never seen this field)
    # is treated the same as "UNKNOWN" -- still guarded, not skipped.
    chosen_slate = next(
        (s for s in slate_doc.get("slates", []) if s.get("slate_id") == slate_doc.get("selected_slate_id")), None,
    )
    source_provenance_claim = (chosen_slate or {}).get("source_provenance", "UNKNOWN")

    try:
        result = build_pool(
            dk_rows, args.date, args.output, args.predictions_root, args.pitcher_snapshot, args.batter_snapshot,
            source_provenance_claim=source_provenance_claim,
        )
    except UnsafeSourceProvenanceError as e:
        print(f"\nDFS SALARIES: SOURCE PROVENANCE BLOCKED\n{e}")
        print("\nThis is TEST / SYNTHETIC DATA, not a genuine DraftKings export. "
              "Enable Mock Mode to build a pool from it anyway (dev/testing only), "
              "or upload a real DraftKings salary CSV for this date.")
        sys.exit(1)
    print()

    print_pool_report(result)

    pool_path, report_path = save_pool(
        result, args.date, args.dfs_input_root,
        {
            "provider_source": slate_doc.get("provider_name"),
            "provider_slate_path": str(slate_path),
            "selected_slate_id": slate_doc.get("selected_slate_id"),
        },
    )

    print("Files written:")
    print(f"  - {pool_path}")
    print(f"  - {report_path}")


if __name__ == "__main__":
    main()
