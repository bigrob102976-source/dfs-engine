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
from dfs.providers.source_realism import PROVIDER_KIND_CSV, PROVIDER_KIND_DRAFTKINGS_UNOFFICIAL
from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage, to_artifact_key


def _find_latest_provider_slate(date: str, dfs_input_root: str) -> Path:
    """Mirrors research/adapters/pitcher_input.py's _load_json_list
    fallback: fetch_dfs_slate.py writes this document exclusively through
    research.storage.save_json() (object storage is the source of truth),
    so "the latest one for this date" has to be discoverable there too --
    a fresh container has no local dfs_input/ copy at all until this
    script pulls one down."""
    folder = Path(dfs_input_root) / date
    local_matches = sorted(folder.glob("provider_slate_*.json")) if folder.exists() else []
    if local_matches:
        return local_matches[-1]

    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    remote_keys = storage.list_files(to_artifact_key(folder), prefix="provider_slate_", ext=".json")
    return (ARTIFACT_ROOT / remote_keys[-1]) if remote_keys else None


def _load_provider_slate(path: Path):
    """Mirrors research/adapters/pitcher_input.py's _load_json_list
    object-storage fallback -- see that module's copy for the full
    rationale. Returns None (never raises) when the artifact truly
    doesn't exist on either backend, so main() can print its own
    actionable error."""
    if not path.exists():
        storage = resolve_artifact_storage(ARTIFACT_ROOT)
        data = storage.read_bytes(to_artifact_key(path))
        if data is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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
    slate_doc = _load_provider_slate(slate_path) if slate_path is not None else None
    if slate_doc is None:
        print(f"\nERROR: No provider slate artifact found for {args.date} under {args.dfs_input_root}/ "
              f"(checked local disk and object storage). Run scripts/fetch_dfs_slate.py --date {args.date} first.")
        sys.exit(1)

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

    # Milestone 32.2B: content-realism rules must be evaluated
    # provider-aware -- draftkings_unofficial's real Classic draftables
    # endpoint has a live-proven-legitimate broad pitcher pool that must
    # never BLOCK; every other provider (CSV, mock) keeps the original
    # CSV-calibrated behavior unchanged.
    is_draftkings_unofficial = slate_doc.get("provider_name") == "draftkings_unofficial"
    provider_kind = PROVIDER_KIND_DRAFTKINGS_UNOFFICIAL if is_draftkings_unofficial else PROVIDER_KIND_CSV

    try:
        result = build_pool(
            dk_rows, args.date, args.output, args.predictions_root, args.pitcher_snapshot, args.batter_snapshot,
            source_provenance_claim=source_provenance_claim,
            slate_id=slate_doc.get("selected_slate_id"), dfs_input_root=args.dfs_input_root,
            provider_kind=provider_kind,
        )
    except UnsafeSourceProvenanceError as e:
        print(f"\nDFS SALARIES: SOURCE PROVENANCE BLOCKED\n{e}")
        if is_draftkings_unofficial:
            # Milestone 32.2B: manual CSV upload is not a fallback for
            # this provider -- report the outage plainly and wait for the
            # provider to recover, never silently substitute CSV/mock/
            # synthetic/a stale slate from another date.
            print("\nDK LIVE PROVIDER UNAVAILABLE")
        else:
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
