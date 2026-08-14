"""Applies a resolved column mapping (canonical field -> CSV header) to
raw parsed rows, producing typed rows. A field left unmapped (None)
simply stays None on every row -- never invented, never defaulted to
zero. Numeric coercion failures are dropped to None rather than raising,
so one bad cell never fails an entire import (see validation.py for how
that's counted and surfaced).
"""

from typing import Dict, List, Optional

from external_projections.csv_import.column_detection import CANONICAL_FIELDS

ColumnMapping = Dict[str, Optional[str]]

_NUMERIC_FIELDS = {"salary", "projection", "ceiling", "floor", "ownership"}


def _clean_numeric(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    cleaned = raw.strip().replace("$", "").replace(",", "").replace("%", "")
    return cleaned or None


def _to_float(raw: Optional[str]) -> Optional[float]:
    cleaned = _clean_numeric(raw)
    if cleaned is None:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _to_int(raw: Optional[str]) -> Optional[int]:
    value = _to_float(raw)
    return int(round(value)) if value is not None else None


def resolve_mapping(detected: ColumnMapping, manual_overrides: Optional[ColumnMapping]) -> ColumnMapping:
    """Manual overrides win over auto-detection field-by-field. A manual
    override of "" or None explicitly UNMAPS a field (the user removed a
    bad auto-detection) rather than falling back to the detected guess."""
    resolved: ColumnMapping = dict(detected)
    if manual_overrides:
        for field, header in manual_overrides.items():
            if field not in CANONICAL_FIELDS:
                continue
            resolved[field] = header or None
    return resolved


def apply_mapping(raw_rows: List[Dict[str, str]], mapping: ColumnMapping) -> List[Dict[str, object]]:
    """Returns one normalized dict per input row with every canonical
    field present (None when unmapped or unparseable). `name`, `team`,
    `opponent`, `position`, `slate`, `player_id` stay as (stripped)
    strings; salary/projection/ceiling/floor/ownership are floats
    (salary rounded to an int-valued float by the caller if needed)."""
    normalized: List[Dict[str, object]] = []
    for raw in raw_rows:
        row: Dict[str, object] = {}
        for field in CANONICAL_FIELDS:
            header = mapping.get(field)
            value = raw.get(header) if header else None
            if field in _NUMERIC_FIELDS:
                row[field] = _to_int(value) if field == "salary" else _to_float(value)
            else:
                row[field] = value.strip() if isinstance(value, str) and value.strip() else None
        normalized.append(row)
    return normalized
