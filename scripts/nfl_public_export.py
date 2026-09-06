"""NFL public access -- stateless, request-scoped-only DK CSV export.

Never touches the database or any persisted saved-lineup record;
formats exactly the lineup data the caller supplies in this same
request (the SAME assignments scripts/nfl_dashboard_optimize.py already
returned them moments earlier). No auth is required and none would be
meaningful here -- there is no user-owned state this could ever leak,
by construction (see nfl/lineup_export.py::inline_assignments_to_dk_row's
own docstring).

Usage:
    python scripts/nfl_public_export.py <request_json>

request_json:
{
  "lineups": [ { "assignments": [ {"slot": "QB", "draftkings_player_id": "...", "name": "..."}, ... ] }, ... ]
}
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nfl.lineup_export import LineupExportError, export_inline_lineups_to_csv

MAX_LINEUPS = 50


def main(request: dict) -> int:
    lineups = request.get("lineups")
    if not isinstance(lineups, list) or not lineups:
        print(json.dumps({"error": "At least one lineup is required."}))
        return 1
    if len(lineups) > MAX_LINEUPS:
        print(json.dumps({"error": f"At most {MAX_LINEUPS} lineups may be exported at once."}))
        return 1

    try:
        csv_text = export_inline_lineups_to_csv(lineups)
    except LineupExportError as exc:
        print(json.dumps({"error": str(exc), "error_type": type(exc).__name__}))
        return 1

    print(json.dumps({"csv": csv_text, "lineup_count": len(lineups)}))
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python scripts/nfl_public_export.py <request_json>"}))
        sys.exit(1)
    try:
        parsed_request = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Malformed request JSON: {exc}"}))
        sys.exit(1)
    sys.exit(main(parsed_request))
