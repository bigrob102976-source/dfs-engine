"""Milestone 32.1, Part 8 -- incremental player crosswalk builder.

Wraps M32.0's historical_mlb.identity module (reused, not duplicated)
with the bookkeeping a full warehouse build needs that a single-date
POC didn't: a player is SEEN across many dates, so first_seen/last_seen
must be tracked across the whole build, and handedness only needs to be
looked up (fetch_cached_person, cached -- Part 4) once per player ever,
not once per game appearance.
"""

from typing import Dict, Optional

from historical_mlb.identity import PlayerCrosswalkRow, crosswalk_row_from_mlbam
from historical_mlb.sources.mlb_stats import fetch_cached_person, person_handedness


class PlayerCrosswalkBuilder:
    def __init__(self):
        self._rows: Dict[str, PlayerCrosswalkRow] = {}

    def observe(self, mlbam_id, name: str, team: Optional[str], game_date: str) -> PlayerCrosswalkRow:
        mlbam_id = str(mlbam_id)
        row = self._rows.get(mlbam_id)
        if row is None:
            row = crosswalk_row_from_mlbam(mlbam_id, name, team)
            person = fetch_cached_person(mlbam_id)
            hand = person_handedness(person)
            row.bat_side = hand["bat_side"]
            row.throw_side = hand["throw_hand"]
            row.first_seen = game_date
            row.last_seen = game_date
            self._rows[mlbam_id] = row
        else:
            if game_date < row.first_seen:
                row.first_seen = game_date
            if game_date > row.last_seen:
                row.last_seen = game_date
            if team:
                row.team = team  # most-recently-observed team wins -- a traded player's crosswalk row reflects their latest team, matching this project's existing "never stale team" precedent elsewhere
        return row

    def rows(self):
        return list(self._rows.values())

    def get(self, mlbam_id) -> Optional[PlayerCrosswalkRow]:
        return self._rows.get(str(mlbam_id))
