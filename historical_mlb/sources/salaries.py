"""Historical DraftKings MLB salary adapter.

Milestone 32.0 audit finding (report honestly, not glossed over): NO
confirmed free, programmatically-fetchable historical DraftKings MLB
salary source was found during this audit.

- RotoGuru1.com is the historical DFS salary archive referenced across
  multiple public developer write-ups (e.g. Ergo Sum's "Scrape
  Historical DraftKings Data" post), but the domain timed out on every
  live connection attempt from this environment (both direct urllib and
  curl, ~10s timeout, no HTTP response at all -- indistinguishable from
  either the site being down or this specific outbound path being
  blocked; NOT confirmed as permanently unreachable in production).
- No historical-DFS-salary-specific dataset was found on Kaggle or
  GitHub during this audit's search; the MLB salary datasets that DO
  exist there (e.g. "MLB Player Salaries 2011-2024") are REAL player
  salaries, not DraftKings DFS contest salaries -- a genuinely
  different, unrelated dataset that must not be confused with what this
  milestone needs.
- Per this milestone's own Part E: "Historical salaries are helpful but
  do not block building the core model if unavailable" -- confirmed:
  the projection-model training target is actual_dk_points computed
  from real MLB outcomes (see historical_mlb/scoring.py), which needs
  NO salary data at all. Salaries only matter for optimizer-side
  historical backtesting (value/ownership-style analysis), a later
  milestone's concern.

This module therefore does NOT implement a live fetch (there is nothing
confirmed-working to fetch from). It implements a defensive PARSER for
a human-supplied CSV in RotoGuru's documented column layout (or any
similarly-shaped file), so that IF a real historical salary file is
obtained later (a manual RotoGuru download once reachable, a purchased
archive, a partner's data dump), this package can already ingest it
without further code changes.
"""

import csv
import io
from typing import List, Optional

# RotoGuru's own documented MLB DK export columns (gene-hi-mlb.pl):
# GID, Name, Team, Oppt, DKSlot, DKSal, and others we don't consume.
# Accepts either RotoGuru's raw header names OR a plain
# date/player/team/position/salary header (case-insensitive) -- both
# map onto the same normalized output rows below.
_COLUMN_ALIASES = {
    "date": ("date", "gid"),
    "player": ("player", "name"),
    "team": ("team",),
    "position": ("position", "dkslot", "pos"),
    "salary": ("salary", "dksal"),
}


def _find_column(header: List[str], candidates: tuple) -> Optional[str]:
    lower = {h.lower(): h for h in header}
    for candidate in candidates:
        if candidate in lower:
            return lower[candidate]
    return None


def parse_historical_salary_csv(csv_text: str, date: Optional[str] = None) -> List[dict]:
    """Pure parsing, no network. Returns one dict per row: date, player,
    team, position, salary (salary as int cents-free dollars, e.g.
    4200). `date` is used as a fallback when the file has no date
    column of its own (a single-day RotoGuru export's filename usually
    carries the date instead of a column) -- never invented beyond that
    explicit fallback."""
    reader = csv.DictReader(io.StringIO(csv_text))
    header = reader.fieldnames or []
    col = {key: _find_column(header, aliases) for key, aliases in _COLUMN_ALIASES.items()}

    rows: List[dict] = []
    for raw in reader:
        salary_raw = raw.get(col["salary"]) if col["salary"] else None
        try:
            salary = int(str(salary_raw).replace("$", "").replace(",", "")) if salary_raw not in (None, "") else None
        except ValueError:
            salary = None
        rows.append({
            "date": (raw.get(col["date"]) if col["date"] else None) or date,
            "player": raw.get(col["player"]) if col["player"] else None,
            "team": raw.get(col["team"]) if col["team"] else None,
            "position": raw.get(col["position"]) if col["position"] else None,
            "salary": salary,
        })
    return rows
