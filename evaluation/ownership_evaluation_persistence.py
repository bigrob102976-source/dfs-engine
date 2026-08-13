"""Immutable, reproducible storage for one ownership-evaluation run.
Preserves contest context in the filename (never merges different
contests into one saved result) and mirrors the rest of the codebase's
save discipline -- new timestamped file every run, FileExistsError
instead of silent overwrite.

    ownership_evaluations/
      YYYY-MM-DD/
        contest_<contest_id>_ownership_eval_<timestamp>.json
        contest_<contest_id>_ownership_eval_<timestamp>.csv
"""

import csv
from pathlib import Path

# Reuses the same UTC/local/timezone metadata helper every other
# immutable artifact in this project uses (America/Chicago, tzdata-backed).
from research.prediction_snapshot import _timezone_metadata
from research.storage import save_json

DEFAULT_OWNERSHIP_EVALUATIONS_ROOT = Path(__file__).resolve().parent.parent / "ownership_evaluations"

_CSV_COLUMNS = [
    "date", "contest_id", "dk_player_id", "name", "team", "position", "salary",
    "projected_ownership", "actual_ownership", "error", "absolute_error",
    "projected_rank", "actual_rank", "ownership_model_version",
]


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing ownership evaluation: {path}")


def build_evaluation_document(report_dict: dict, generated_at_utc: str) -> dict:
    return {**report_dict, **_timezone_metadata(generated_at_utc)}


def save_evaluation_json(document: dict, slate_date: str, contest_id: str, timestamp: str,
                          output_root: Path = DEFAULT_OWNERSHIP_EVALUATIONS_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"contest_{contest_id}_ownership_eval_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def save_evaluation_csv(document: dict, slate_date: str, contest_id: str, timestamp: str,
                         output_root: Path = DEFAULT_OWNERSHIP_EVALUATIONS_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"contest_{contest_id}_ownership_eval_{timestamp}.csv"
    _no_overwrite(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    model_version = document.get("ownership_model_version")
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_COLUMNS)
        for r in document.get("records", []):
            if not r.get("matched"):
                continue
            writer.writerow([
                slate_date, contest_id, r.get("dk_player_id"), r.get("name"), r.get("team"),
                "/".join(r.get("dk_positions") or []), r.get("salary"),
                r.get("projected_ownership"), r.get("actual_ownership"), r.get("error"), r.get("abs_error"),
                r.get("projected_rank"), r.get("actual_rank"), model_version,
            ])
    return path
