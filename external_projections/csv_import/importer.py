"""Orchestrates one CSV projection import end-to-end (Milestone 18):

    decode -> parse -> detect/apply column mapping -> normalize rows
        -> match against our known slate (validation only)
        -> build ExternalProjectionPlayer records -> baseline document

`analyze_import` does all of this WITHOUT writing anything -- it powers
the wizard's Preview Mapping / Validation Summary steps, and can be
re-run cheaply whenever the user edits the column mapping.
`build_baseline_document` does the same work and returns the document
ready for external_projections/persistence.py::save_baseline_snapshot
(the actual save call, and the immutability discipline it enforces,
stays in that unmodified module).

A row is only ever included in the saved snapshot if it has BOTH a name
and a projection -- the same "no projection, no record" rule
external_projections/mock_provider.py already applies. Every other
field stays None when the CSV didn't supply it; nothing here invents a
salary, ceiling, floor, or ownership value.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from external_projections.csv_import.column_detection import detect_columns
from external_projections.csv_import.mapping import ColumnMapping, apply_mapping, resolve_mapping
from external_projections.csv_import.matcher import known_team_abbreviations, match_rows
from external_projections.csv_import.parser import CsvParseError, decode_csv_bytes, parse_csv_text
from external_projections.csv_import.providers import provider_label
from external_projections.csv_import.validation import ImportValidationSummary, build_validation_summary
from external_projections.models import ExternalProjectionPlayer
from external_projections.validator import validate_external_players

CSV_IMPORT_ENGINE_VERSION = "0.1.0"
PREVIEW_ROW_LIMIT = 20


@dataclass
class ImportAnalysis:
    headers: List[str]
    detected_mapping: ColumnMapping
    resolved_mapping: ColumnMapping
    preview_rows: List[Dict[str, str]]
    parse_warnings: List[str]
    validation: ImportValidationSummary
    importable_player_count: int
    skipped_missing_name: int
    skipped_missing_projection: int

    def to_dict(self) -> dict:
        return {
            "headers": self.headers,
            "detected_mapping": self.detected_mapping,
            "resolved_mapping": self.resolved_mapping,
            "preview_rows": self.preview_rows,
            "parse_warnings": self.parse_warnings,
            "validation": self.validation.to_dict(),
            "importable_player_count": self.importable_player_count,
            "skipped_missing_name": self.skipped_missing_name,
            "skipped_missing_projection": self.skipped_missing_projection,
        }


def _parse_and_map(csv_bytes: bytes, manual_mapping: Optional[ColumnMapping]):
    text = decode_csv_bytes(csv_bytes)
    headers, raw_rows, parse_warnings = parse_csv_text(text)
    detected = detect_columns(headers)
    resolved = resolve_mapping(detected, manual_mapping)
    normalized_rows = apply_mapping(raw_rows, resolved)
    return headers, raw_rows, detected, resolved, normalized_rows, parse_warnings


def _build_external_players(
    normalized_rows: List[Dict[str, object]], retrieved_at: str, provider_key: str, provider_name: str, slate_id: str, slate_name: str,
) -> tuple:
    players: List[ExternalProjectionPlayer] = []
    skipped_missing_name = 0
    skipped_missing_projection = 0

    for i, row in enumerate(normalized_rows):
        name = row.get("name")
        if not name:
            skipped_missing_name += 1
            continue
        projection = row.get("projection")
        if projection is None:
            skipped_missing_projection += 1
            continue

        external_id = str(row.get("player_id")) if row.get("player_id") else f"csv-{provider_key}-row-{i}"
        players.append(ExternalProjectionPlayer(
            external_player_id=external_id,
            name=str(name),
            team=str(row.get("team") or ""),
            position=str(row.get("position") or ""),
            projection=float(projection),
            provider_name=provider_name,
            updated_at=retrieved_at,
            slate_id=slate_id,
            opponent=row.get("opponent"),
            salary=int(row["salary"]) if row.get("salary") is not None else None,
            ceiling=row.get("ceiling"),
            floor=row.get("floor"),
            ownership_projection=row.get("ownership"),
            slate_name=slate_name,
            provider_version=CSV_IMPORT_ENGINE_VERSION,
        ))

    return players, skipped_missing_name, skipped_missing_projection


def analyze_import(
    csv_bytes: bytes, provider_key: str, date: str,
    manual_mapping: Optional[ColumnMapping] = None, research_output_root: str = "research_output",
) -> ImportAnalysis:
    headers, raw_rows, detected, resolved, normalized_rows, parse_warnings = _parse_and_map(csv_bytes, manual_mapping)

    try:
        known_teams = known_team_abbreviations(research_output_root, date)
        matches = match_rows(normalized_rows, research_output_root, date)
    except Exception:
        # No Research Package for this date yet, or it's unreadable -- identity
        # matching simply can't run. Every structural validation check (missing
        # salary/projection/position, duplicates) still works fine without it.
        known_teams = set()
        matches = []

    validation = build_validation_summary(normalized_rows, matches, known_teams)
    provider_name = provider_label(provider_key) or provider_key
    retrieved_at = datetime.now(timezone.utc).isoformat()
    _, skipped_name, skipped_projection = _build_external_players(
        normalized_rows, retrieved_at, provider_key, provider_name,
        slate_id=f"csv-import-{provider_key}-{date}", slate_name=f"{provider_name} CSV Import",
    )

    return ImportAnalysis(
        headers=headers, detected_mapping=detected, resolved_mapping=resolved,
        preview_rows=raw_rows[:PREVIEW_ROW_LIMIT], parse_warnings=parse_warnings,
        validation=validation, importable_player_count=len(normalized_rows) - skipped_name - skipped_projection,
        skipped_missing_name=skipped_name, skipped_missing_projection=skipped_projection,
    )


def build_baseline_document(
    csv_bytes: bytes, provider_key: str, date: str, original_filename: str,
    manual_mapping: Optional[ColumnMapping] = None, research_output_root: str = "research_output",
) -> dict:
    """Full document ready for
    external_projections/persistence.py::save_baseline_snapshot. Raises
    CsvParseError only for a truly undecodable upload; every other bad-CSV
    condition is captured in the returned document's warnings/validation
    instead (callers should still refuse to save a document with zero
    players -- see scripts/save_projection_csv_import.py)."""
    headers, raw_rows, detected, resolved, normalized_rows, parse_warnings = _parse_and_map(csv_bytes, manual_mapping)

    try:
        known_teams = known_team_abbreviations(research_output_root, date)
        matches = match_rows(normalized_rows, research_output_root, date)
    except Exception:
        known_teams = set()
        matches = []

    validation = build_validation_summary(normalized_rows, matches, known_teams)
    provider_name = provider_label(provider_key) or provider_key
    retrieved_at = datetime.now(timezone.utc).isoformat()
    slate_id = f"csv-import-{provider_key}-{date}"
    slate_name = f"{provider_name} CSV Import"

    players, skipped_name, skipped_projection = _build_external_players(
        normalized_rows, retrieved_at, provider_key, provider_name, slate_id, slate_name,
    )
    warnings = parse_warnings + validate_external_players(players)

    return {
        "slate_date": date,
        "provider": provider_key,
        "provider_name": provider_name,
        "provider_version": CSV_IMPORT_ENGINE_VERSION,
        "is_mock": False,
        "slate_id": slate_id,
        "slate_name": slate_name,
        "retrieved_at": retrieved_at,
        "player_count": len(players),
        "players": [p.to_dict() for p in players],
        "warnings": warnings,
        "source": "csv_import",
        "original_filename": original_filename,
        "column_mapping": resolved,
        "csv_engine_version": CSV_IMPORT_ENGINE_VERSION,
        "validation_summary": validation.to_dict(),
        "skipped_missing_name": skipped_name,
        "skipped_missing_projection": skipped_projection,
    }
