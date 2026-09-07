"""NFL M14 -- the real DK-ready CSV export bridge the dashboard's Saved
Lineups UI calls. Operates purely on already-persisted saved lineups
(no live pool needed -- see nfl/lineup_export.py::export_saved_lineups_to_csv).

Usage:
    python scripts/nfl_dashboard_export.py <request_json>

request_json:
{
  "savedLineups": [ ...NflSavedLineup.to_dict(), ... ],
  "template": "<real DK-exported template CSV text>"   // optional
}
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nfl.lineup_export import LineupExportError, export_saved_lineups_to_csv, fill_dk_template_csv_from_saved
from nfl.saved_lineup_models import NflSavedLineup, SavedLineupCorruptionError


def main(request: dict) -> int:
    try:
        saved_lineups = [NflSavedLineup.from_dict(d) for d in request.get("savedLineups", [])]
    except SavedLineupCorruptionError as exc:
        print(json.dumps({"error": f"INVALID_SAVED_LINEUP: {exc}", "error_type": type(exc).__name__}))
        return 1

    if not saved_lineups:
        print(json.dumps({"error": "No saved lineups were supplied to export."}))
        return 1

    template = request.get("template")
    try:
        csv_text = fill_dk_template_csv_from_saved(template, saved_lineups) if template else export_saved_lineups_to_csv(saved_lineups)
    except LineupExportError as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}))
        return 1

    print(json.dumps({"csv": csv_text, "lineup_count": len(saved_lineups), "used_template": bool(template)}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python scripts/nfl_dashboard_export.py <request_json>"}))
        sys.exit(2)
    sys.exit(main(json.loads(sys.argv[1])))
