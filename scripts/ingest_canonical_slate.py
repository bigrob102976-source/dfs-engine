"""CLI entry point: M2 shadow canonical ingestion for one already-fetched,
real DraftKings slate -- runs the parallel RAW -> normalize -> NORMALIZED
R2 pipeline (canonical_ingestion/pipeline.py) alongside (never instead
of) the legacy scripts/fetch_dfs_slate.py path.

Prints a structured JSON result to stdout and ALWAYS exits 0, even when
the shadow path itself fails (see canonical_ingestion/pipeline.py's
M2I docstring) -- this script is invoked, best-effort, by
fetch_dfs_slate.py right after that script's own legacy artifact write
has already succeeded, and a shadow-path failure must never be able to
turn a successful legacy DK fetch into a non-zero exit code for
whatever invoked it (the Windows worker, a human running this by hand
for the M2K integration proof, etc.). The failure is still fully
visible -- printed to stdout as `"ok": false` with `error`/`error_type`,
and to stderr as a one-line summary -- never silently swallowed.

Usage:
    python scripts/ingest_canonical_slate.py --date YYYY-MM-DD --slate-id dkunofficial-152904
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canonical_ingestion.pipeline import ingest_slate_shadow


def main() -> None:
    parser = argparse.ArgumentParser(description="M2 shadow canonical ingestion for one already-validated real DK slate.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-id", required=True, help="providerSlateId, e.g. dkunofficial-152904")
    parser.add_argument("--sport", default="MLB")
    parser.add_argument("--site", default="draftkings")
    args = parser.parse_args()

    print("=" * 70)
    print(f"M2 SHADOW CANONICAL INGESTION -- {args.slate_id} ({args.date})")
    print("=" * 70)

    result = ingest_slate_shadow(date=args.date, provider_slate_id=args.slate_id, sport=args.sport, site=args.site)
    print(json.dumps(result.to_dict(), indent=2, default=str))

    if result.ok:
        print(
            f"\nCANONICAL SHADOW INGESTION: OK -- {result.player_count} players "
            f"({result.resolved_count} resolved, {result.unresolved_count} unresolved, "
            f"{result.review_required_count} review-required)"
        )
    else:
        print(f"\nCANONICAL SHADOW INGESTION: FAILED -- {result.error_type}: {result.error}", file=sys.stderr)

    # Always exit 0 -- see this script's own module docstring.
    sys.exit(0)


if __name__ == "__main__":
    main()
