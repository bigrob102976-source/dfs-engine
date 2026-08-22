"""Milestone 32.2B -- pregame lock/freeze/no-backfill decision tests.
Pure function, no network, no filesystem."""

from datetime import datetime, timezone

from big_money_ml.lock import FREEZE_EXISTING, GENERATE, NO_VALID_PREGAME, determine_action


def test_generates_when_game_is_scheduled_and_before_start_time():
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    action = determine_action(
        mlb_detailed_state="Scheduled", game_scheduled_start_utc="2026-08-22T23:00:00Z",
        existing_projection_status=None, now_utc=now,
    )
    assert action == GENERATE


def test_freezes_existing_when_game_has_started_and_a_pregame_snapshot_exists():
    now = datetime(2026, 8, 22, 23, 30, tzinfo=timezone.utc)
    action = determine_action(
        mlb_detailed_state="In Progress", game_scheduled_start_utc="2026-08-22T23:00:00Z",
        existing_projection_status="LIVE_PREGAME", now_utc=now,
    )
    assert action == FREEZE_EXISTING


def test_no_valid_pregame_when_game_has_started_and_nothing_was_ever_captured():
    now = datetime(2026, 8, 22, 23, 30, tzinfo=timezone.utc)
    action = determine_action(
        mlb_detailed_state="In Progress", game_scheduled_start_utc="2026-08-22T23:00:00Z",
        existing_projection_status=None, now_utc=now,
    )
    assert action == NO_VALID_PREGAME


def test_never_backfills_a_stale_scheduled_status_past_actual_first_pitch():
    """The exact bug this module was built to prevent: a games.json
    whose status field was cached before first pitch and never refreshed
    must not be trusted once wall-clock time has passed the game's own
    authoritative scheduled start."""
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)  # a full day after the scheduled start
    action = determine_action(
        mlb_detailed_state="Scheduled",  # stale -- the game has definitely already been played
        game_scheduled_start_utc="2026-08-22T23:00:00Z",
        existing_projection_status=None, now_utc=now,
    )
    assert action == NO_VALID_PREGAME


def test_stale_scheduled_status_past_start_time_still_freezes_a_real_prior_pregame_snapshot():
    now = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)
    action = determine_action(
        mlb_detailed_state="Scheduled", game_scheduled_start_utc="2026-08-22T23:00:00Z",
        existing_projection_status="LIVE_PREGAME", now_utc=now,
    )
    assert action == FREEZE_EXISTING


def test_missing_scheduled_start_falls_back_to_mlb_status_alone():
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    action = determine_action(
        mlb_detailed_state="Scheduled", game_scheduled_start_utc=None,
        existing_projection_status=None, now_utc=now,
    )
    assert action == GENERATE


def test_final_game_status_never_generates():
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    action = determine_action(
        mlb_detailed_state="Final", game_scheduled_start_utc="2026-08-21T23:00:00Z",
        existing_projection_status=None, now_utc=now,
    )
    assert action == NO_VALID_PREGAME
