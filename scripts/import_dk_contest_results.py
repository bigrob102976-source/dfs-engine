"""CLI entry point: parse, resolve, and persist a real DraftKings contest
standings CSV export as an immutable actual-ownership/contest-results
snapshot (Milestone 27 -- reuses the Milestone 11 ingestion architecture
in evaluation/actual_ownership_*.py unchanged; this script only wires
its three existing steps together, mirroring
scripts/save_projection_csv_import.py's exact structure).

    python scripts/import_dk_contest_results.py --csv-path FILE \
        --date YYYY-MM-DD [--slate-id SLATE_ID]

Resolves each row against the pregame ownership prediction snapshot for
`--date` (scoped to `--slate-id` when given, exactly like every other
Milestone 26 slate-aware artifact) so actual ownership/contest rows are
matched to the SAME player pool the pregame prediction was made against
-- never a different slate's pool.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.actual_ownership_parser import DKResultsFormatError, parse_dk_results_csv  # noqa: E402
from evaluation.actual_ownership_persistence import build_actual_ownership_document, save_actual_ownership_document  # noqa: E402
from evaluation.actual_ownership_resolver import resolve_actual_ownership  # noqa: E402
from ownership.persistence import load_latest_ownership_snapshot  # noqa: E402


def now_iso_compact() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a real DraftKings contest-standings CSV as actual ownership/contest results.")
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-id", default=None, help="Scopes player-pool resolution to this slate's pregame ownership snapshot.")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(json.dumps({"status": "error", "reason": f"CSV file not found: {csv_path}"}))
        return

    try:
        raw_rows, contest, format_used, warnings = parse_dk_results_csv(csv_path)
    except DKResultsFormatError as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    try:
        ownership_doc = load_latest_ownership_snapshot(args.date, slate_id=args.slate_id)
    except FileNotFoundError as e:
        print(json.dumps({"status": "error", "reason": str(e)}))
        return

    records = resolve_actual_ownership(raw_rows, ownership_doc.get("players", []), contest, source_file=csv_path.name)
    document = build_actual_ownership_document(args.date, contest, format_used, warnings, records, slate_id=args.slate_id)

    if document["record_count"] == 0:
        print(json.dumps({"status": "no_players", "reason": "No rows parsed from this contest-results CSV."}))
        return

    path = save_actual_ownership_document(document, args.date, now_iso_compact())

    print(f"Contest: {contest.contest_name} ({contest.contest_id})")
    print(f"Rows imported: {document['record_count']}  Matched: {document['matched_count']} ({document['match_rate'] * 100:.1f}%)")
    print(f"Saved: {path}")
    print(json.dumps({
        "status": "ready",
        "path": str(path),
        "record_count": document["record_count"],
        "matched_count": document["matched_count"],
        "match_rate": document["match_rate"],
        "contest_name": contest.contest_name,
        "contest_id": contest.contest_id,
    }))


if __name__ == "__main__":
    main()
