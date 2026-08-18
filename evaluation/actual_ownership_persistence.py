"""Immutable storage for imported actual DraftKings ownership --
deliberately a SEPARATE root from ownership_predictions/, predictions/,
and dfs_input/ so pregame and postgame data can never be confused for
each other on disk, mirroring the milestone's explicit separation rule.

    actual_ownership/
      YYYY-MM-DD/
        contest_<contest_id>_<timestamp>.json

Milestone 27: `slate_id` is recorded on the document (never inferred --
the caller must know which slate a contest export belongs to) so Main
and Turbo actual-ownership imports are unambiguous even though the
existing per-contest-id filename already keeps them physically separate
on disk (a real DK contest ID is unique per contest/slate)."""

from pathlib import Path
from typing import List, Optional

from evaluation.actual_ownership_models import ActualOwnershipRecord, ContestMetadata
from research.storage import save_json

DEFAULT_ACTUAL_OWNERSHIP_ROOT = Path(__file__).resolve().parent.parent / "actual_ownership"


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing actual-ownership import: {path}")


def build_actual_ownership_document(
    slate_date: str, contest: ContestMetadata, format_used: str, warnings: List[str],
    records: List[ActualOwnershipRecord], slate_id: Optional[str] = None,
) -> dict:
    matched = sum(1 for r in records if r.match_status == "matched")
    return {
        "slate_date": slate_date,
        "slate_id": slate_id,
        "contest": contest.to_dict(),
        "format_used": format_used,
        "import_warnings": warnings,
        "record_count": len(records),
        "matched_count": matched,
        "unmatched_count": sum(1 for r in records if r.match_status == "unmatched"),
        "ambiguous_count": sum(1 for r in records if r.match_status == "ambiguous"),
        "match_rate": round(matched / len(records), 4) if records else 0.0,
        "records": [r.to_dict() for r in records],
    }


def save_actual_ownership_document(
    document: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_ACTUAL_OWNERSHIP_ROOT,
) -> Path:
    contest_id = document["contest"].get("contest_id") or "unknown"
    path = Path(output_root) / slate_date / f"contest_{contest_id}_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path
