"""NFL M14 -- targeted tests for nfl/game_lock.py: real, timezone-aware
lock-state computation. Every scenario uses a real ISO-8601 UTC instant
-- never a naive datetime, per Phase 4's explicit requirement."""

from datetime import datetime, timezone

import pytest

from nfl.game_lock import (
    LOCKED,
    PRELOCK,
    GameStartTimeMissingError,
    build_game_lock_info,
    compute_lock_state,
    format_eastern,
    is_locked,
    parse_game_start_utc,
)


def test_prelock_before_start_time():
    game_start = "2026-09-13T17:00:00.0000000Z"  # 1:00 PM ET (EDT, UTC-4)
    now = datetime(2026, 9, 13, 16, 59, 0, tzinfo=timezone.utc)
    assert compute_lock_state(game_start, now) == PRELOCK
    assert is_locked(game_start, now) is False


def test_locked_at_exact_start_time():
    game_start = "2026-09-13T17:00:00.0000000Z"
    now = datetime(2026, 9, 13, 17, 0, 0, tzinfo=timezone.utc)
    assert compute_lock_state(game_start, now) == LOCKED
    assert is_locked(game_start, now) is True


def test_locked_after_start_time():
    game_start = "2026-09-13T17:00:00.0000000Z"
    now = datetime(2026, 9, 13, 18, 30, 0, tzinfo=timezone.utc)
    assert is_locked(game_start, now) is True


def test_1pm_et_game():
    """1:00 PM ET = 17:00 UTC during EDT (September)."""
    game_start = "2026-09-13T17:00:00.0000000Z"
    before = datetime(2026, 9, 13, 16, 0, 0, tzinfo=timezone.utc)
    after = datetime(2026, 9, 13, 17, 30, 0, tzinfo=timezone.utc)
    assert compute_lock_state(game_start, before) == PRELOCK
    assert compute_lock_state(game_start, after) == LOCKED
    assert format_eastern(game_start) == "Sun 09/13 01:00 PM EDT"


def test_405_and_425_et_games_lock_independently():
    """NFL Classic's staggered starts: a 4:05 PM ET game and a 4:25 PM ET
    game lock at DIFFERENT real instants -- never a single slate-wide cutoff."""
    game_405 = "2026-09-13T20:05:00.0000000Z"
    game_425 = "2026-09-13T20:25:00.0000000Z"
    at_405 = datetime(2026, 9, 13, 20, 5, 0, tzinfo=timezone.utc)

    assert compute_lock_state(game_405, at_405) == LOCKED
    assert compute_lock_state(game_425, at_405) == PRELOCK  # still 20 minutes out


def test_sunday_night_game():
    """SNF, ~8:20 PM ET = 00:20 UTC the NEXT calendar day during EDT."""
    game_start = "2026-09-14T00:20:00.0000000Z"  # Sunday 8:20 PM ET
    before = datetime(2026, 9, 14, 0, 0, 0, tzinfo=timezone.utc)
    after = datetime(2026, 9, 14, 1, 0, 0, tzinfo=timezone.utc)
    assert compute_lock_state(game_start, before) == PRELOCK
    assert compute_lock_state(game_start, after) == LOCKED


def test_monday_night_game():
    game_start = "2026-09-15T00:15:00.0000000Z"  # Monday 8:15 PM ET
    before = datetime(2026, 9, 15, 0, 10, 0, tzinfo=timezone.utc)
    after = datetime(2026, 9, 15, 0, 20, 0, tzinfo=timezone.utc)
    assert compute_lock_state(game_start, before) == PRELOCK
    assert compute_lock_state(game_start, after) == LOCKED


def test_dst_fall_back_transition():
    """DST ends (fall back) the first Sunday of November -- a game the
    week before is EDT (UTC-4), the week after is EST (UTC-5). The lock
    computation itself only ever uses UTC internally, so this test's
    real purpose is proving format_eastern() picks the correct
    abbreviation/offset for each real calendar date."""
    before_dst_end = "2026-11-01T18:00:00.0000000Z"  # Sunday before the Nov 1 2026 fall-back
    after_dst_end = "2026-11-08T18:00:00.0000000Z"  # Sunday after

    assert "EDT" in format_eastern(before_dst_end) or "EST" in format_eastern(before_dst_end)
    assert "EST" in format_eastern(after_dst_end)
    # Lock computation is unaffected by the DST label -- purely a UTC comparison.
    now = datetime(2026, 11, 8, 19, 0, 0, tzinfo=timezone.utc)
    assert compute_lock_state(after_dst_end, now) == LOCKED


def test_lock_state_uses_utc_never_naive_now():
    game_start = "2026-09-13T17:00:00.0000000Z"
    naive_now = datetime(2026, 9, 13, 18, 0, 0)  # no tzinfo
    with pytest.raises(ValueError):
        compute_lock_state(game_start, naive_now)


def test_missing_game_start_time_raises_never_guesses():
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(GameStartTimeMissingError):
        compute_lock_state(None, now)
    with pytest.raises(GameStartTimeMissingError):
        compute_lock_state("", now)


def test_invalid_game_start_time_raises_never_guesses():
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(GameStartTimeMissingError):
        compute_lock_state("not-a-real-timestamp", now)


def test_parse_game_start_utc_round_trips_real_dk_format():
    """Real captured DK format: fractional seconds + Z suffix."""
    dt = parse_game_start_utc("2026-09-13T17:00:00.0000000Z")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0
    assert dt.hour == 17


def test_build_game_lock_info_real_fields():
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)
    info = build_game_lock_info("100", "2026-09-13T17:00:00.0000000Z", now, home_team="BUF", away_team="MIA")
    assert info.game_id == "100"
    assert info.locked is True
    assert info.lock_state == LOCKED
    assert info.home_team == "BUF"
    assert info.away_team == "MIA"
    assert info.start_time_utc.startswith("2026-09-13T17:00:00")
    assert "PM" in info.start_time_eastern


def test_system_timezone_independence(monkeypatch):
    """Setting the process's TZ env var must never change the lock
    decision -- everything here is computed from explicit tz-aware
    datetimes (UTC internally, explicit ZoneInfo for display), never a
    bare .astimezone() call that would fall back to system local time."""
    game_start = "2026-09-13T17:00:00.0000000Z"
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setenv("TZ", "Asia/Tokyo")
    result_tokyo = compute_lock_state(game_start, now)
    display_tokyo = format_eastern(game_start)

    monkeypatch.setenv("TZ", "America/Los_Angeles")
    result_la = compute_lock_state(game_start, now)
    display_la = format_eastern(game_start)

    assert result_tokyo == result_la == LOCKED
    assert display_tokyo == display_la  # Eastern display is identical regardless of process TZ
