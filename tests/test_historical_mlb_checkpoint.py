"""Milestone 32.1 -- historical_mlb/checkpoint.py. No network calls."""

from historical_mlb import checkpoint


def test_is_date_complete_false_when_no_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert checkpoint.is_date_complete("2025-06-15") is False


def test_mark_and_read_checkpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint.mark_date_complete("2025-06-15", {"games": 15, "hitter_rows": 317})
    assert checkpoint.is_date_complete("2025-06-15") is True
    data = checkpoint.read_checkpoint("2025-06-15")
    assert data["games"] == 15
    assert data["date"] == "2025-06-15"


def test_list_completed_dates_sorted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint.mark_date_complete("2025-06-17", {})
    checkpoint.mark_date_complete("2025-06-15", {})
    checkpoint.mark_date_complete("2025-06-16", {})
    assert checkpoint.list_completed_dates() == ["2025-06-15", "2025-06-16", "2025-06-17"]


def test_last_completed_date(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert checkpoint.last_completed_date() is None
    checkpoint.mark_date_complete("2025-06-15", {})
    checkpoint.mark_date_complete("2025-06-17", {})
    assert checkpoint.last_completed_date() == "2025-06-17"


def test_resolve_effective_start_without_resume_uses_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint.mark_date_complete("2025-06-16", {})
    assert checkpoint.resolve_effective_start("2025-06-15", resume=False) == "2025-06-15"


def test_resolve_effective_start_with_resume_never_skips_ahead_of_requested_start(tmp_path, monkeypatch):
    """Regression guard for a real bug caught live during this
    milestone's own full-build attempt: a checkpoint from an unrelated,
    LATER date range (e.g. the small integration build's 2025-06-xx
    dates, run before the full 2024-03-28.. build) must NEVER cause
    --resume to jump ahead and skip the real, earlier requested range.
    Safe resumability comes entirely from warehouse_builder.py's
    per-date checkpoint.is_date_complete() check in its main loop, not
    from this function -- so resolve_effective_start always returns
    requested_start unchanged, regardless of what's checkpointed."""
    monkeypatch.chdir(tmp_path)
    checkpoint.mark_date_complete("2025-07-19", {})
    assert checkpoint.resolve_effective_start("2024-03-28", resume=True) == "2024-03-28"


def test_resolve_effective_start_resume_with_earlier_checkpoint_still_uses_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    checkpoint.mark_date_complete("2025-06-10", {})
    assert checkpoint.resolve_effective_start("2025-06-20", resume=True) == "2025-06-20"


def test_resolve_effective_start_resume_with_no_checkpoints_uses_requested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert checkpoint.resolve_effective_start("2025-06-15", resume=True) == "2025-06-15"
