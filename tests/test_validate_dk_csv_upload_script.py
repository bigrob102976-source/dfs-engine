"""BREAK-GLASS ADMIN CSV UPLOAD Phase 2/12 -- scripts/validate_dk_csv_upload.py.

Invoked via subprocess exactly like dashboard/lib/adminCsvImport.ts calls
it in production, so this proves the actual CLI contract (stdout JSON),
not just an importable function's return value."""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_dk_csv_upload.py"

HEADER = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n"


def _run(csv_text: str, tmp_path: Path) -> dict:
    csv_path = tmp_path / "upload.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "--csv-path", str(csv_path)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_valid_real_shaped_csv(tmp_path):
    csv_text = HEADER + (
        "OF,Player One (1),Player One,1,OF,4500,TOR@BOS,BOS,10.0\n"
        "SP,Player Two (2),Player Two,2,SP,8000,TOR@BOS,TOR,15.0\n"
    )
    doc = _run(csv_text, tmp_path)
    assert doc["status"] == "valid"
    assert doc["sport"] == "MLB"
    assert doc["player_count"] == 2
    assert doc["salary_min"] == 4500
    assert doc["salary_max"] == 8000
    assert set(doc["teams"]) == {"BOS", "TOR"}
    assert set(doc["positions"]) == {"OF", "SP"}
    assert doc["duplicate_player_ids"] == []
    assert doc["warnings"] == []


def test_missing_required_columns_rejected_loudly(tmp_path):
    doc = _run("Name,Salary\nPlayer One,4500\n", tmp_path)
    assert doc["status"] == "invalid"
    assert "missing column" in doc["reason"] or "missing a" in doc["reason"]


def test_zero_player_rows_rejected(tmp_path):
    doc = _run(HEADER, tmp_path)
    assert doc["status"] == "invalid"
    assert "zero player rows" in doc["reason"]


def test_invalid_salary_rejected_loudly(tmp_path):
    csv_text = HEADER + "OF,Player One (1),Player One,1,OF,not-a-number,TOR@BOS,BOS,10.0\n"
    doc = _run(csv_text, tmp_path)
    assert doc["status"] == "invalid"
    assert "Salary" in doc["reason"]


def test_duplicate_dk_player_ids_flagged_in_preview_not_silently_deduped(tmp_path):
    csv_text = HEADER + (
        "OF,Player One (1),Player One,1,OF,4500,TOR@BOS,BOS,10.0\n"
        "OF,Player One Dup (1),Player One,1,OF,4600,TOR@BOS,BOS,10.0\n"
    )
    doc = _run(csv_text, tmp_path)
    assert doc["status"] == "valid"  # structurally parseable -- duplicates are a WARNING, not a hard reject
    assert doc["player_count"] == 2
    assert doc["duplicate_player_ids"] == ["1"]
    assert any("duplicate" in w.lower() for w in doc["warnings"])


def test_wrong_sport_csv_missing_dk_columns_rejected(tmp_path):
    # A non-DK CSV (e.g. an NFL/other-site export) never has DraftKings'
    # exact required columns -- proves this never silently accepts
    # something that merely looks vaguely CSV-shaped.
    doc = _run("player,team,points\nA,BOS,10\n", tmp_path)
    assert doc["status"] == "invalid"


def test_empty_file_rejected(tmp_path):
    doc = _run("", tmp_path)
    assert doc["status"] == "invalid"


def test_binary_file_rejected_not_crashed(tmp_path):
    csv_path = tmp_path / "upload.csv"
    csv_path.write_bytes(bytes(range(0, 256)))
    result = subprocess.run([sys.executable, str(SCRIPT), "--csv-path", str(csv_path)], capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0
    doc = json.loads(result.stdout.strip().splitlines()[-1])
    assert doc["status"] == "invalid"
    assert "binary" in doc["reason"].lower() or "not readable" in doc["reason"].lower()


def test_missing_team_and_position_counted(tmp_path):
    csv_text = HEADER + ",Player One (1),Player One,1,,4500,TOR@BOS,,10.0\n"
    doc = _run(csv_text, tmp_path)
    assert doc["status"] == "valid"
    assert doc["missing_team_count"] == 1
    assert doc["missing_position_count"] == 1
