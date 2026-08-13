"""Parses a DraftKings contest-results/standings CSV export to derive
actual player ownership.

DraftKings does not publish one single results schema. This parser
inspects the header row rather than assuming a shape, and supports the
two known real export shapes:

1. DIRECT: the export includes an ownership sub-table (columns
   containing "Player" and "%Drafted"/"Ownership"/"Own%") -- DraftKings'
   own contest-standings CSVs commonly embed this as a second table,
   column-offset to the right of the per-entry lineup table, in the SAME
   file (a well-known DK export quirk, not a documented schema).
2. DERIVED: no direct ownership column exists, but a "Lineup" column
   (one string per contest entry, e.g. "P Dylan Cease P Paul Skenes C
   Drake Baldwin ...") is present. Ownership is derived by counting how
   often each player name appears across every entry's lineup string,
   divided by the total number of entries.

If neither is present, this raises DKResultsFormatError explaining
exactly what's missing -- ownership is never invented.
"""

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.dk_roster_config import DK_CLASSIC_ROSTER_SLOTS
from evaluation.actual_ownership_models import ContestMetadata

_SLOT_LABELS = {slot["slot"] for slot in DK_CLASSIC_ROSTER_SLOTS}  # {"P","C","1B","2B","3B","SS","OF"}
_OWNERSHIP_HEADER_MARKERS = {"drafted", "ownership", "own"}


class DKResultsFormatError(ValueError):
    """The CSV doesn't contain enough information to derive actual
    ownership -- fail loudly rather than invent it."""


@dataclass
class RawActualOwnershipRow:
    name: str
    actual_ownership: float
    dk_player_id: Optional[str] = None


def compute_file_hash(path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_header_cell(cell: str) -> str:
    return cell.strip().lower().replace(" ", "").replace("%", "")


def _extract_id_from_name_plus_id(value: str) -> Optional[str]:
    value = value.strip()
    if "(" in value and value.endswith(")"):
        return value.rsplit("(", 1)[1].rstrip(")").strip() or None
    return None


def _parse_percent(raw: str) -> Optional[float]:
    cleaned = raw.strip().replace("%", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _contest_id_from_filename(filename: str) -> Optional[str]:
    match = re.search(r"(\d{5,})", filename)
    return match.group(1) if match else None


def _find_direct_ownership_columns(header: List[str]) -> Optional[Tuple[int, int]]:
    """Returns (player_col_index, ownership_col_index) if a direct
    ownership sub-table is present in the header row, else None."""
    normalized = [_normalize_header_cell(c) for c in header]
    player_idx = next((i for i, c in enumerate(normalized) if c == "player"), None)
    ownership_idx = next((i for i, c in enumerate(normalized) if c in _OWNERSHIP_HEADER_MARKERS), None)
    if player_idx is None or ownership_idx is None:
        return None
    return player_idx, ownership_idx


def _find_lineup_column(header: List[str]) -> Optional[int]:
    normalized = [_normalize_header_cell(c) for c in header]
    return next((i for i, c in enumerate(normalized) if c == "lineup"), None)


def _parse_lineup_string(lineup: str) -> List[str]:
    """'P Dylan Cease P Paul Skenes C Drake Baldwin ...' -> ['Dylan Cease',
    'Paul Skenes', 'Drake Baldwin', ...]. Splits on DK roster-slot labels
    (reused from config.dk_roster_config, not duplicated) rather than a
    hardcoded position list."""
    tokens = lineup.split()
    names: List[str] = []
    current: List[str] = []
    for tok in tokens:
        if tok in _SLOT_LABELS:
            if current:
                names.append(" ".join(current))
                current = []
        else:
            current.append(tok)
    if current:
        names.append(" ".join(current))
    return names


def parse_dk_results_csv(path) -> Tuple[List[RawActualOwnershipRow], ContestMetadata, str, List[str]]:
    """Returns (raw_rows, contest_metadata, format_used, warnings).
    format_used is "direct_ownership_table" or "derived_from_lineups".
    Malformed individual rows are skipped and reported in `warnings` --
    never silently clamped, never abort the whole file over one bad row."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DraftKings results file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise DKResultsFormatError(f"{path} is empty.")

    header = rows[0]
    data_rows = rows[1:]
    warnings: List[str] = []

    direct = _find_direct_ownership_columns(header)
    if direct:
        player_idx, ownership_idx = direct
        raw_rows: List[RawActualOwnershipRow] = []
        for row in data_rows:
            if len(row) <= max(player_idx, ownership_idx):
                continue
            name = row[player_idx].strip()
            pct_raw = row[ownership_idx].strip()
            if not name or not pct_raw:
                continue
            pct = _parse_percent(pct_raw)
            if pct is None:
                warnings.append(f"Could not parse ownership value {pct_raw!r} for player {name!r} -- row skipped.")
                continue
            if pct < 0 or pct > 100:
                warnings.append(f"{name!r} has an out-of-range ownership value {pct} -- row skipped, not clamped.")
                continue
            dk_id = _extract_id_from_name_plus_id(name)
            raw_rows.append(RawActualOwnershipRow(name=name, actual_ownership=pct, dk_player_id=dk_id))
        entries = len(raw_rows) if raw_rows else None
        format_used = "direct_ownership_table"
    else:
        lineup_idx = _find_lineup_column(header)
        if lineup_idx is None:
            raise DKResultsFormatError(
                f"{path} doesn't look like a DraftKings contest-results export: no ownership column "
                f"(Player + %Drafted/Ownership) and no 'Lineup' column found. Columns present: {header}. "
                f"Actual ownership cannot be derived from this file."
            )
        name_counts: Dict[str, int] = {}
        total_entries = 0
        for row in data_rows:
            if len(row) <= lineup_idx or not row[lineup_idx].strip():
                continue
            names = _parse_lineup_string(row[lineup_idx])
            if not names:
                continue
            total_entries += 1
            for name in names:
                name_counts[name] = name_counts.get(name, 0) + 1
        if total_entries == 0:
            raise DKResultsFormatError(f"{path} has a 'Lineup' column but no parseable entry rows were found.")
        raw_rows = [
            RawActualOwnershipRow(name=name, actual_ownership=round(100.0 * count / total_entries, 4))
            for name, count in name_counts.items()
        ]
        entries = total_entries
        format_used = "derived_from_lineups"
        warnings.append(
            f"No direct ownership column found -- ownership derived from {total_entries} entries' Lineup strings. "
            f"Team is not derivable from this format; matching relies on player name only."
        )

    metadata = ContestMetadata(
        contest_id=_contest_id_from_filename(path.name),
        contest_name=None,
        contest_type=None,
        entries=entries,
        max_entries=None,
        results_filename=path.name,
        source_file_hash=compute_file_hash(path),
        retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    return raw_rows, metadata, format_used, warnings
