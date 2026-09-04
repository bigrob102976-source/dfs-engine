"""NFL M9 -- real, GSIS-keyed weekly injury report status from
nflreadpy.load_injuries() (confirmed live, 2025: season/week/gsis_id/
report_status/report_primary_injury/practice_status columns -- real
official injury-report data, not derived or inferred).

Classification: PARTIAL, not AVAILABLE. This is the real, published
in-week injury REPORT (Questionable/Doubtful/Out/None), which genuinely
is public before kickoff -- but it is not the same thing as a confirmed
final active/inactive gameday status (a "Questionable" player often
does play). Used here only as an honest pre-game signal, never as a
substitute for real snap/usage data, and never used to infer or
backfill a missing-usage row as "was injured" -- that would be
guessing a reason nflverse itself doesn't report."""

from typing import Dict, List, Optional


def build_injury_status_lookup(injury_rows: List[dict], week: int) -> Dict[str, Optional[str]]:
    """{gsis_id -> report_status} for real rows at exactly this week --
    never carried forward from a prior week (a stale injury tag is worse
    than none). A player not in `injury_rows` for this week simply has
    no lookup entry (never assumed healthy or assumed injured)."""
    lookup: Dict[str, Optional[str]] = {}
    for row in injury_rows:
        if row.get("week") != week:
            continue
        gsis_id = row.get("gsis_id")
        if not gsis_id:
            continue
        lookup[gsis_id] = row.get("report_status")
    return lookup
