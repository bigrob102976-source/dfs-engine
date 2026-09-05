"""NFL M14 -- DraftKings-ready lineup CSV export.

DK's own real roster-slot ordering for NFL Classic is QB, RB, RB, WR,
WR, WR, TE, FLEX, DST (confirmed live -- config/dk_roster_config_nfl.py's
DK_NFL_CLASSIC_ROSTER_SLOTS, verified against real DraftGroup 151307).
Each cell uses DK's own real, publicly documented lineup-upload cell
format: "{Player Name} ({DraftKings player ID})" -- e.g.
"Patrick Mahomes (39971620)" -- so DK ID is always the disambiguating
identity, never the player name alone (NFL M14 Phase 19's explicit
requirement).

No Entry ID / Contest Name / Contest ID columns are fabricated: DK
requires those to already exist (they identify a specific real contest
entry a user owns) and this project has no real captured template to
know their exact real column names/values for -- inventing them would
violate this project's "never fabricate" rule. Two real, honest export
paths instead:
  - export_lineups_to_csv(): a roster-only CSV for user review / manual
    DK entry (no contest metadata at all).
  - fill_dk_template_csv(): fills roster columns into a REAL template
    CSV the admin/user supplies (already containing their own real
    Entry ID/Contest Name/etc. from DraftKings' own site export),
    leaving every other column untouched.

Every lineup is independently re-validated (nfl/lineup_validator.py)
immediately before export -- an invalid lineup is never written to a
CSV DK could reject or, worse, silently accept incorrectly."""

import csv
import io
from typing import Dict, List

from nfl.lineup_validator import validate_lineup
from nfl.optimizer_models import NflLineup, NflOptimizerPlayer
from nfl.saved_lineup_models import NflSavedLineup, validate_saved_lineup

DK_NFL_CSV_HEADER = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]

# Maps this project's own slot-instance labels (nfl/solver.py::
# _expand_slot_instances()) to their position in DK_NFL_CSV_HEADER.
_SLOT_LABEL_ORDER = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"]


class LineupExportError(ValueError):
    """A lineup failed independent validation, or a supplied DK template
    doesn't have the columns this export needs -- raised before any CSV
    is written, never a silently malformed export."""


def format_dk_player_cell(name: str, draftkings_player_id: str) -> str:
    """DK's own real lineup-entry cell format: "Name (ID)"."""
    return f"{name} ({draftkings_player_id})"


def _validate_or_raise(lineup: NflLineup, players_by_key: Dict[str, NflOptimizerPlayer]) -> None:
    violations = validate_lineup(lineup, players_by_key)
    if violations:
        raise LineupExportError(f"Lineup {lineup.index} failed validation and cannot be exported: {violations}")


def lineup_to_dk_row(lineup: NflLineup, players_by_key: Dict[str, NflOptimizerPlayer]) -> List[str]:
    """Returns one CSV row (list of cells) in DK_NFL_CSV_HEADER order.
    Raises LineupExportError if the lineup is invalid or a slot is missing."""
    _validate_or_raise(lineup, players_by_key)
    by_slot = {a.slot: a for a in lineup.assignments}
    row: List[str] = []
    for label in _SLOT_LABEL_ORDER:
        assignment = by_slot.get(label)
        if assignment is None:
            raise LineupExportError(f"Lineup {lineup.index} is missing slot {label!r} -- refusing to export an incomplete roster.")
        row.append(format_dk_player_cell(assignment.name, assignment.draftkings_player_id))
    return row


def export_lineups_to_csv(lineups: List[NflLineup], players_by_key: Dict[str, NflOptimizerPlayer]) -> str:
    """Roster-only CSV (no contest metadata) -- one row per lineup, for
    user review or manual DK entry. Every lineup is independently
    re-validated before being written."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(DK_NFL_CSV_HEADER)
    for lineup in lineups:
        writer.writerow(lineup_to_dk_row(lineup, players_by_key))
    return buffer.getvalue()


def saved_lineup_to_dk_row(saved: NflSavedLineup) -> List[str]:
    """Same DK_NFL_CSV_HEADER row shape as lineup_to_dk_row(), but built
    directly from a PERSISTED NflSavedLineup's own slot snapshots --
    never needs a live NflOptimizerPlayer pool (a saved lineup was
    already legal when built/late-swapped; export re-checks it for
    STRUCTURAL corruption -- duplicate players/slots -- via
    validate_saved_lineup(), not live-pool eligibility, which a saved
    lineup opened days later shouldn't be re-litigated against)."""
    validate_saved_lineup(saved)
    by_slot = {s.roster_slot: s for s in saved.slots}
    row: List[str] = []
    for label in _SLOT_LABEL_ORDER:
        slot = by_slot.get(label)
        if slot is None:
            raise LineupExportError(f"Saved lineup {saved.lineup_id} is missing slot {label!r} -- refusing to export an incomplete roster.")
        row.append(format_dk_player_cell(slot.name, slot.draftkings_player_id))
    return row


def export_saved_lineups_to_csv(saved_lineups: List[NflSavedLineup]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(DK_NFL_CSV_HEADER)
    for saved in saved_lineups:
        writer.writerow(saved_lineup_to_dk_row(saved))
    return buffer.getvalue()


def fill_dk_template_csv_from_saved(template_csv_text: str, saved_lineups: List[NflSavedLineup]) -> str:
    """fill_dk_template_csv()'s saved-lineup equivalent -- same real DK
    template-filling behavior, sourced from persisted snapshots instead
    of a live solve's NflLineup/NflOptimizerPlayer pair."""
    reader = csv.reader(io.StringIO(template_csv_text))
    rows = list(reader)
    if not rows:
        raise LineupExportError("Template CSV has no header row.")
    header, data_rows = rows[0], rows[1:]
    column_indices = _find_roster_column_indices(header)

    if len(data_rows) < len(saved_lineups):
        raise LineupExportError(
            f"Template CSV has only {len(data_rows)} data row(s) but {len(saved_lineups)} lineup(s) were requested -- "
            "refusing to guess which entries the extra lineups belong to."
        )

    for saved, row in zip(saved_lineups, data_rows):
        values = saved_lineup_to_dk_row(saved)
        for column_index, value in zip(column_indices, values):
            row[column_index] = value

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(data_rows)
    return buffer.getvalue()


def _find_roster_column_indices(header: List[str]) -> List[int]:
    """DK's real header repeats column names (RB, RB, WR, WR, WR) -- a
    dict-keyed CSV reader/writer (csv.DictReader/DictWriter) cannot
    represent that (duplicate keys collide), so this works positionally
    instead: for each slot in DK_NFL_CSV_HEADER in order, consumes the
    NEXT not-yet-used header index with that exact column name. Returns
    one column index per DK_NFL_CSV_HEADER entry, in the same order."""
    remaining_positions: Dict[str, List[int]] = {}
    for i, name in enumerate(header):
        remaining_positions.setdefault(name, []).append(i)

    indices: List[int] = []
    for label in DK_NFL_CSV_HEADER:
        positions = remaining_positions.get(label)
        if not positions:
            raise LineupExportError(f"Template CSV is missing a required DK roster column: {label!r}.")
        indices.append(positions.pop(0))
    return indices


def fill_dk_template_csv(template_csv_text: str, lineups: List[NflLineup], players_by_key: Dict[str, NflOptimizerPlayer]) -> str:
    """Fills DK_NFL_CSV_HEADER's roster columns into a REAL DK-exported
    template CSV the caller supplies, preserving every other column
    (Entry ID, Contest Name, Contest ID, etc.) exactly as given.
    Positional (list-based), not dict-based -- DK's real header repeats
    column names (RB, RB, WR, WR, WR), which a dict-keyed CSV reader
    cannot represent at all. Raises LineupExportError if the template is
    missing any required roster column, or has fewer data rows than
    lineups to place (never silently drops a lineup or guesses which
    row it belongs to)."""
    reader = csv.reader(io.StringIO(template_csv_text))
    rows = list(reader)
    if not rows:
        raise LineupExportError("Template CSV has no header row.")
    header, data_rows = rows[0], rows[1:]

    column_indices = _find_roster_column_indices(header)

    if len(data_rows) < len(lineups):
        raise LineupExportError(
            f"Template CSV has only {len(data_rows)} data row(s) but {len(lineups)} lineup(s) were requested -- "
            "refusing to guess which entries the extra lineups belong to."
        )

    for lineup, row in zip(lineups, data_rows):
        values = lineup_to_dk_row(lineup, players_by_key)
        for column_index, value in zip(column_indices, values):
            row[column_index] = value

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(data_rows)
    return buffer.getvalue()
