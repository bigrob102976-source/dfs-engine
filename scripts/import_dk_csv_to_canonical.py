"""CLI entry point: BREAK-GLASS ADMIN CSV IMPORT, step 2 of 2 (Python
half). Takes an already-uploaded, already-structurally-validated real
DraftKings CSV (dfs/providers/draftkings_csv_storage.py -- saved by the
EXISTING scripts/upload_draftkings_csv.py, reused unmodified here) and
writes it through to a NORMALIZED canonical artifact in object storage,
exactly like the automatic DK-fetch shadow path does (canonical_ingestion/
pipeline.py::build_normalized_from_fetch) except for the one genuine
difference documented in canonical_ingestion/admin_csv_import.py: slateDate
is the admin's own explicit input, never derived from a CSV that cannot
reliably expose real game-start instants.

This script never writes to Postgres -- same architectural boundary
every other canonical-ingestion script in this project follows (Python
owns RAW/NORMALIZED object storage; dashboard/lib/db/canonicalPromotion.ts
is the only thing that ever writes canonical Postgres CURRENT). The
caller (dashboard/lib/adminCsvImport.ts) reads this script's
RESULT_JSON, then calls promoteCanonicalArtifact() directly, in-process,
against the normalizedKey this script reports.

    python scripts/import_dk_csv_to_canonical.py --date 2026-09-04 --slate-label Main
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canonical_ingestion.admin_csv_import import build_normalized_from_admin_csv  # noqa: E402
from dfs.providers.base import ProviderNoSlateError, ProviderUnavailableError  # noqa: E402
from dfs.providers.draftkings_csv_provider import DraftKingsCsvProvider  # noqa: E402
from dfs.providers.draftkings_csv_storage import DEFAULT_DFS_INPUT_ROOT, list_uploads  # noqa: E402
from research.artifact_storage import ARTIFACT_ROOT, resolve_artifact_storage, to_artifact_key  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote an already-uploaded admin DraftKings CSV to a NORMALIZED canonical artifact.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD -- the admin's own explicit slate date, never derived.")
    parser.add_argument("--slate-label", required=True)
    parser.add_argument("--sport", default="MLB")
    parser.add_argument("--site", default="draftkings")
    args = parser.parse_args()

    provider_name = DraftKingsCsvProvider.name

    try:
        provider = DraftKingsCsvProvider()
        fetch_result = provider.get_slate(args.date, sport=args.sport, site=args.site)
    except (ProviderUnavailableError, ProviderNoSlateError) as e:
        print(json.dumps({"ok": False, "error": str(e), "errorType": type(e).__name__}))
        return

    slate_info = next((s for s in fetch_result.slates if s.slate_name == args.slate_label), None)
    if slate_info is None:
        print(json.dumps({
            "ok": False,
            "error": f"No parsed upload found for slate label {args.slate_label!r} on {args.date}. "
                     f"Labels found: {[s.slate_name for s in fetch_result.slates]}",
            "errorType": "slate_not_found",
        }))
        return
    provider_players = fetch_result.players_by_slate.get(slate_info.slate_id, [])

    uploads = [u for u in list_uploads(args.date, output_root=DEFAULT_DFS_INPUT_ROOT) if u.slate_label == args.slate_label]
    if not uploads:
        print(json.dumps({"ok": False, "error": f"No saved upload found for slate label {args.slate_label!r} on {args.date}.", "errorType": "upload_not_found"}))
        return
    latest_upload = max(uploads, key=lambda u: u.uploaded_at)

    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    csv_bytes = storage.read_bytes(to_artifact_key(Path(latest_upload.path)))
    if csv_bytes is None:
        print(json.dumps({"ok": False, "error": f"Saved upload file is missing from storage: {latest_upload.path}", "errorType": "upload_file_missing"}))
        return
    csv_text = csv_bytes.decode("utf-8-sig")

    result = build_normalized_from_admin_csv(
        sport=args.sport, site=args.site, provider=provider_name, slate_info=slate_info, provider_players=provider_players,
        slate_date=args.date, original_filename=latest_upload.original_filename, csv_text=csv_text,
    )

    salaries = [p.salary for p in provider_players]
    doc = result.to_dict()
    doc["slate_name"] = slate_info.slate_name
    doc["provider"] = provider_name
    doc["sport"] = args.sport
    doc["salary_min"] = min(salaries) if salaries else None
    doc["salary_max"] = max(salaries) if salaries else None
    doc["teams"] = sorted({p.team for p in provider_players if p.team})
    doc["positions"] = sorted({pos for p in provider_players for pos in p.position_eligibility})
    doc["source_provenance"] = slate_info.source_provenance
    doc["realism_blocked"] = slate_info.realism_blocked
    doc["realism_findings"] = slate_info.realism_findings
    doc["warnings"] = fetch_result.warnings
    print(json.dumps(doc))


if __name__ == "__main__":
    main()
