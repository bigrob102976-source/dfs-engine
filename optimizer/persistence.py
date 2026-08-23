"""Immutable, reproducible storage for one optimizer run: JSON (full
detail, every setting used) plus a CSV (one row per lineup, for quick
inspection). Mirrors dfs/persistence.py's and
research/prediction_snapshot.py's save discipline -- new timestamped
file every run, FileExistsError instead of silent overwrite.

    lineups/
      YYYY-MM-DD/
        dk_lineups_<timestamp>.json
        dk_lineups_<timestamp>.csv
"""

import csv
from pathlib import Path
from typing import Optional

# Reuses the exact same UTC/local/timezone metadata helper the Pitcher and
# Batter snapshots already use (America/Chicago, tzdata-backed) instead of
# re-deriving the same timezone-conversion logic a third time.
from research.prediction_snapshot import _timezone_metadata
from research.storage import save_json

DEFAULT_LINEUPS_ROOT = Path(__file__).resolve().parent.parent / "lineups"

_CSV_COLUMNS = ["Lineup", "P1", "P2", "C", "1B", "2B", "3B", "SS", "OF1", "OF2", "OF3", "Salary", "Projection", "Ceiling"]


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing lineup file: {path}")


def build_lineup_set_document(
    slate_date: str, generated_at_utc: str, pool_path: str, pitcher_snapshot_path: Optional[str],
    batter_snapshot_path: Optional[str], optimizer_version: str, settings: dict, result, players_by_key: dict,
    ownership_snapshot_path: Optional[str] = None,
    # Milestone 32.4 -- Big Money ML lineup provenance. All None/default
    # for every pre-existing Projection Source (independent/external/
    # adjusted/ai/native/fantasypros); populated only when a build
    # actually used Big Money ML, so every prior document shape is
    # unaffected (these keys simply carry null, same as before this
    # milestone existed).
    projection_source: str = "independent",
    slate_id: Optional[str] = None,
    pitcher_model_version: Optional[str] = None,
    hitter_model_version: Optional[str] = None,
    pitcher_projection_snapshot_generated_at: Optional[str] = None,
    hitter_projection_snapshot_generated_at: Optional[str] = None,
    excluded_missing_projection_source: Optional[list] = None,
) -> dict:
    return {
        "slate_date": slate_date,
        "generated_at": generated_at_utc,
        **_timezone_metadata(generated_at_utc),
        "optimizer_version": optimizer_version,
        "source_player_pool_path": str(pool_path),
        "pitcher_snapshot_reference": pitcher_snapshot_path,
        "batter_snapshot_reference": batter_snapshot_path,
        "ownership_snapshot_reference": ownership_snapshot_path,
        "settings": settings,
        "lineups_requested": result.requested,
        "lineups_generated": result.generated,
        "stopped_reason": result.stopped_reason,
        "lineups": [lu.to_dict() for lu in result.lineups],
        # Milestone 32.4 provenance block.
        "projection_source": projection_source,
        "slate_id": slate_id,
        "pitcher_model_version": pitcher_model_version,
        "hitter_model_version": hitter_model_version,
        "pitcher_projection_snapshot_generated_at": pitcher_projection_snapshot_generated_at,
        "hitter_projection_snapshot_generated_at": hitter_projection_snapshot_generated_at,
        "excluded_missing_projection_source": list(excluded_missing_projection_source or []),
    }


def save_lineup_set_json(document: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_LINEUPS_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"dk_lineups_{timestamp}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def _slot_players(assignments, slot: str):
    return [a for a in assignments if a["slot"] == slot]


def save_lineup_set_csv(document: dict, slate_date: str, timestamp: str, output_root: Path = DEFAULT_LINEUPS_ROOT) -> Path:
    path = Path(output_root) / slate_date / f"dk_lineups_{timestamp}.csv"
    _no_overwrite(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_COLUMNS)
        for lineup in document["lineups"]:
            assignments = lineup["assignments"]
            pitchers = _slot_players(assignments, "P")
            ofs = _slot_players(assignments, "OF")
            by_slot = {a["slot"]: a for a in assignments if a["slot"] not in ("P", "OF")}
            row = [
                lineup["index"],
                pitchers[0]["name"] if len(pitchers) > 0 else "",
                pitchers[1]["name"] if len(pitchers) > 1 else "",
                by_slot.get("C", {}).get("name", ""),
                by_slot.get("1B", {}).get("name", ""),
                by_slot.get("2B", {}).get("name", ""),
                by_slot.get("3B", {}).get("name", ""),
                by_slot.get("SS", {}).get("name", ""),
                ofs[0]["name"] if len(ofs) > 0 else "",
                ofs[1]["name"] if len(ofs) > 1 else "",
                ofs[2]["name"] if len(ofs) > 2 else "",
                lineup["salary"],
                lineup["projection"],
                lineup["ceiling"],
            ]
            writer.writerow(row)
    return path
