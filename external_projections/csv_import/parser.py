"""Robust CSV decoding/parsing for an imported projection file
(Milestone 18). Never raises for the "normal" family of bad-CSV cases a
user-supplied export can hit (unknown encoding, duplicate columns, empty
file, ragged rows) -- each is reported as a warning string instead, so
the importer can always return a graceful validation summary rather than
crash. Only a truly unreadable/non-text upload raises CsvParseError,
which the caller turns into a clean error response.
"""

import csv
import io
from typing import Dict, List, Tuple


class CsvParseError(RuntimeError):
    """The uploaded file could not be treated as CSV text at all (e.g.
    binary/corrupted data no fallback encoding can decode)."""


_ENCODINGS_TO_TRY = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def decode_csv_bytes(raw: bytes) -> str:
    """Tries a fixed, ordered list of encodings. latin-1 never raises
    (every byte value is a valid latin-1 code point), so this is
    guaranteed to return SOME text for any non-empty byte string -- it is
    the deliberate last-resort fallback for "unknown encoding" rather
    than a guess at the real one."""
    if not raw:
        return ""
    for encoding in _ENCODINGS_TO_TRY:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    raise CsvParseError("Could not decode the uploaded file as text with any supported encoding.")


def _dedupe_headers(fieldnames: List[str]) -> Tuple[List[str], List[str]]:
    """DraftKings-style DictReader silently keeps only the LAST column's
    values for a duplicate header name, dropping data with no warning --
    unacceptable for an import tool. Renames every duplicate occurrence
    after the first to `<name> (2)`, `<name> (3)`, ... so no column's
    data is ever silently discarded, and reports the collision."""
    seen: Dict[str, int] = {}
    deduped: List[str] = []
    warnings: List[str] = []
    for name in fieldnames:
        clean = (name or "").strip() or "(blank)"
        count = seen.get(clean, 0) + 1
        seen[clean] = count
        if count == 1:
            deduped.append(clean)
        else:
            renamed = f"{clean} ({count})"
            deduped.append(renamed)
            warnings.append(f"Duplicate column header {clean!r} -- second occurrence renamed to {renamed!r}.")
    return deduped, warnings


def parse_csv_text(text: str) -> Tuple[List[str], List[Dict[str, str]], List[str]]:
    """Returns (headers, rows, warnings). `rows` are plain dicts keyed by
    the (deduped) header names, values always strings (possibly empty).
    Never raises: an empty file or a headers-only file simply produces
    zero rows, with a warning explaining why."""
    warnings: List[str] = []
    stripped = text.strip("﻿ \t\r\n")
    if not stripped:
        return [], [], ["The file is empty."]

    reader = csv.reader(io.StringIO(text))
    try:
        raw_rows = list(reader)
    except csv.Error as e:
        raise CsvParseError(f"The file could not be parsed as CSV: {e}") from e

    if not raw_rows:
        return [], [], ["The file is empty."]

    raw_header = raw_rows[0]
    if not any((cell or "").strip() for cell in raw_header):
        return [], [], ["The file has no header row."]

    headers, dedupe_warnings = _dedupe_headers(raw_header)
    warnings.extend(dedupe_warnings)

    rows: List[Dict[str, str]] = []
    ragged_count = 0
    for raw_row in raw_rows[1:]:
        if not any((cell or "").strip() for cell in raw_row):
            continue  # a fully blank line -- common trailing-newline artifact, not a data row
        if len(raw_row) != len(headers):
            ragged_count += 1
        row = {}
        for i, header in enumerate(headers):
            row[header] = raw_row[i].strip() if i < len(raw_row) else ""
        rows.append(row)

    if ragged_count:
        warnings.append(f"{ragged_count} row(s) had a different number of columns than the header and were padded/truncated to fit.")
    if not rows:
        warnings.append("The file has a header row but no data rows.")

    return headers, rows, warnings
