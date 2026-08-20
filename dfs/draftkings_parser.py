"""Parses a DraftKings MLB Classic salary-export CSV.

Deliberately inspects the actual header row rather than assuming a fixed
schema: DraftKings exports commonly include Position, "Name + ID", Name,
ID, "Roster Position", Salary, "Game Info", TeamAbbrev, and
AvgPointsPerGame, but this parser only requires the columns it actually
needs and fails loudly (DraftKingsCSVFormatError) if a genuinely
required one is missing, rather than silently producing empty/garbage
rows.

AvgPointsPerGame is parsed and preserved (it's real DraftKings data) but
is explicitly NEVER used to influence our own projection -- see
dfs/player_pool.py, which only ever attaches it as external metadata.

Status and Starting (Milestone 31.1) are optional columns some DK
exports include beyond the classic 9 -- parsed when present, left None
when the file's header doesn't have them at all (never guessed/
defaulted to a blank string, which would be indistinguishable from a
genuinely blank value in a file that DOES have the column). See
dfs/availability_filter.py for how Status feeds exclusion.
"""

import csv
import hashlib
from pathlib import Path
from typing import List, Optional

from dfs.models import DKSalaryRow

# At least one of these must be present to identify the DK ID column.
_ID_COLUMNS = ("ID",)
_NAME_ID_COLUMN = "Name + ID"
_REQUIRED_ANY_POSITION_COLUMNS = ("Position", "Roster Position")
_REQUIRED_COLUMNS = ("Name", "Salary", "TeamAbbrev", "Game Info")


class DraftKingsCSVFormatError(ValueError):
    """Raised when the CSV is missing columns this parser genuinely needs.
    Better to fail loudly here than silently emit rows with invented or
    empty identity/salary/position data."""


def _extract_id_from_name_plus_id(value: str) -> str:
    # DraftKings' "Name + ID" column looks like "Aaron Judge (12345678)".
    if "(" in value and value.strip().endswith(")"):
        return value.strip().rsplit("(", 1)[1].rstrip(")").strip()
    return ""


def _parse_salary(raw: str) -> int:
    cleaned = (raw or "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        raise DraftKingsCSVFormatError(f"Row has an empty/unparseable Salary value: {raw!r}")
    return int(float(cleaned))


def _parse_avg_points(raw: Optional[str]) -> Optional[float]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_starting(raw: Optional[str]) -> Optional[bool]:
    # Milestone 31.1: DK's "Starting" column, when present, is either "1"
    # (posted in today's confirmed lineup) or blank -- never any other
    # value observed. `raw is None` means the column doesn't exist in
    # this file's header at all (a normal 9-column Classic export);
    # that's distinct from the column existing with an empty value.
    if raw is None:
        return None
    return raw.strip() == "1"


def _validate_header(fieldnames: List[str]) -> None:
    fieldnames = fieldnames or []
    missing_required = [c for c in _REQUIRED_COLUMNS if c not in fieldnames]
    has_id_column = any(c in fieldnames for c in _ID_COLUMNS) or _NAME_ID_COLUMN in fieldnames
    has_position_column = any(c in fieldnames for c in _REQUIRED_ANY_POSITION_COLUMNS)

    problems = []
    if missing_required:
        problems.append(f"missing column(s): {missing_required}")
    if not has_id_column:
        problems.append(f"missing a player-ID column (expected one of {_ID_COLUMNS} or {_NAME_ID_COLUMN!r})")
    if not has_position_column:
        problems.append(f"missing a position column (expected one of {_REQUIRED_ANY_POSITION_COLUMNS})")

    if problems:
        raise DraftKingsCSVFormatError(
            f"DraftKings CSV does not look like a Classic MLB salary export: {'; '.join(problems)}. "
            f"Columns found: {fieldnames}"
        )


def parse_salary_csv(path) -> List[DKSalaryRow]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DraftKings salary CSV not found: {path}")

    csv_bytes = path.read_bytes()
    sha256 = hashlib.sha256(csv_bytes).hexdigest()

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        _validate_header(reader.fieldnames or [])
        # Milestone 27.4: row 1 is the header, so the first data row is
        # line 2 on disk -- matches what a human opens the CSV and counts.
        rows = [_parse_row(raw, source_row_number=i, source_filename=path.name, source_sha256=sha256)
                for i, raw in enumerate(reader, start=2)]
    return rows


def _parse_row(
    raw: dict, source_row_number: Optional[int] = None,
    source_filename: Optional[str] = None, source_sha256: Optional[str] = None,
) -> DKSalaryRow:
    dk_id = (raw.get("ID") or "").strip()
    if not dk_id and raw.get("Name + ID"):
        dk_id = _extract_id_from_name_plus_id(raw["Name + ID"])
    if not dk_id:
        raise DraftKingsCSVFormatError(f"Could not determine a DraftKings player ID for row: {raw}")

    position_field = raw.get("Position") or raw.get("Roster Position") or ""
    dk_positions = [p.strip() for p in position_field.split("/") if p.strip()]

    # Milestone 31.1: Status/Starting are optional columns -- absent
    # entirely from a classic 9-column DK export, present in some others.
    # raw.get() returns None (not "") when the column itself is missing
    # from this file's header, preserving the None-vs-blank distinction
    # DKSalaryRow's dk_status/dk_starting fields document.
    dk_status = raw.get("Status")
    dk_status = dk_status.strip() if dk_status is not None else None

    return DKSalaryRow(
        dk_player_id=dk_id,
        name=(raw.get("Name") or "").strip(),
        team_abbrev=(raw.get("TeamAbbrev") or "").strip(),
        dk_positions=dk_positions,
        salary=_parse_salary(raw.get("Salary")),
        game_info=(raw.get("Game Info") or "").strip(),
        avg_points_per_game=_parse_avg_points(raw.get("AvgPointsPerGame")),
        roster_position_raw=raw.get("Roster Position"),
        dk_status=dk_status,
        dk_starting=_parse_starting(raw.get("Starting")),
        source_row_number=source_row_number, source_filename=source_filename, source_sha256=source_sha256,
    )
