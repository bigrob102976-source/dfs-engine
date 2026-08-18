from datetime import datetime, timezone

from research.game_environment.game_status import (
    FINAL,
    IN_PLAY,
    PREGAME,
    UNKNOWN,
    classify_mlb_game_status,
    classify_sportsgameodds_status,
    game_has_not_started_yet,
    resolve_game_status,
)


def test_classifies_known_pregame_states():
    assert classify_mlb_game_status("Scheduled") == PREGAME
    assert classify_mlb_game_status("Pre-Game") == PREGAME
    assert classify_mlb_game_status("Warmup") == PREGAME


def test_classifies_known_in_play_states():
    assert classify_mlb_game_status("In Progress") == IN_PLAY
    assert classify_mlb_game_status("Delayed") == IN_PLAY
    assert classify_mlb_game_status("Suspended") == IN_PLAY


def test_classifies_known_final_states():
    assert classify_mlb_game_status("Final") == FINAL
    assert classify_mlb_game_status("Game Over") == FINAL


def test_case_insensitive_matching():
    assert classify_mlb_game_status("SCHEDULED") == PREGAME
    assert classify_mlb_game_status("final") == FINAL


def test_postponed_and_cancelled_are_unknown_not_pregame():
    # Explicit per Milestone 25: a postponed game hasn't started, but must
    # NOT be treated as PREGAME -- otherwise a fresh fetch during the
    # postponement window could silently become "the last valid pregame
    # snapshot" even though market context (probable pitchers, weather
    # day) may have completely reset for whatever new date it's
    # rescheduled to.
    assert classify_mlb_game_status("Postponed") == UNKNOWN
    assert classify_mlb_game_status("Cancelled") == UNKNOWN


def test_missing_or_unrecognized_status_is_unknown():
    assert classify_mlb_game_status(None) == UNKNOWN
    assert classify_mlb_game_status("") == UNKNOWN
    assert classify_mlb_game_status("Some Future MLB Status Nobody Has Seen Yet") == UNKNOWN


def test_sportsgameodds_status_fallback_pregame():
    assert classify_sportsgameodds_status({"started": False}) == PREGAME


def test_sportsgameodds_status_fallback_in_play():
    assert classify_sportsgameodds_status({"started": True, "live": True, "ended": False, "completed": False}) == IN_PLAY


def test_sportsgameodds_status_fallback_final():
    assert classify_sportsgameodds_status({"started": True, "ended": True, "completed": True}) == FINAL


def test_sportsgameodds_status_fallback_cancelled_is_unknown():
    assert classify_sportsgameodds_status({"cancelled": True}) == UNKNOWN


def test_sportsgameodds_status_fallback_missing_is_unknown():
    assert classify_sportsgameodds_status(None) == UNKNOWN
    assert classify_sportsgameodds_status({}) == UNKNOWN


def test_resolve_prefers_mlb_status_over_sportsgameodds():
    # MLB says Final, SportsGameOdds status object (if it disagreed) must
    # never override the authoritative source.
    assert resolve_game_status("Final", {"started": True, "live": True, "ended": False}) == FINAL


def test_resolve_falls_back_to_sportsgameodds_when_mlb_status_missing():
    assert resolve_game_status(None, {"started": False}) == PREGAME
    assert resolve_game_status(None, {"started": True, "live": True}) == IN_PLAY


def test_resolve_unknown_when_both_sources_unavailable():
    assert resolve_game_status(None, None) == UNKNOWN
    assert resolve_game_status("Postponed", None) == UNKNOWN


def test_stale_mlb_pregame_status_is_overridden_by_fresh_sportsgameodds_in_play():
    # Confirmed real bug (Milestone 25 live validation, 2026-08-17: LAD @
    # COL): research_output/<date>/games.json's MLB status is only as
    # fresh as the last research-package build and can still read
    # "Pre-Game" hours after the game actually started. SportsGameOdds'
    # own event status is fetched fresh every pull -- it must win here,
    # or genuinely live/in-play odds get misclassified (and used) as a
    # valid pregame snapshot.
    stale_mlb_pregame = "Pre-Game"
    fresh_sgo_in_play = {"started": True, "live": True, "ended": False, "completed": False}
    assert resolve_game_status(stale_mlb_pregame, fresh_sgo_in_play) == IN_PLAY


def test_stale_mlb_pregame_status_is_overridden_by_fresh_sportsgameodds_final():
    stale_mlb_pregame = "Scheduled"
    fresh_sgo_final = {"started": True, "ended": True, "completed": True}
    assert resolve_game_status(stale_mlb_pregame, fresh_sgo_final) == FINAL


def test_mlb_pregame_status_still_wins_when_sportsgameodds_agrees():
    assert resolve_game_status("Pre-Game", {"started": False}) == PREGAME


def test_mlb_postponed_status_still_wins_over_sportsgameodds():
    # Postponed/Suspended nuance only MLB status models -- SportsGameOdds
    # confirming "not started" doesn't override it into PREGAME.
    assert resolve_game_status("Postponed", {"started": False}) == UNKNOWN


# ----------------------------------------------------------------------------
# Milestone 27.1 -- impossible-state guard (confirmed real bug, 2026-08-18:
# LAD @ COL, real SportsGameOdds IN_PLAY claim ~3.6 hours before the
# authoritative MLB scheduled first pitch -- see providers/event_resolver.py
# for the root cause of WHY the wrong event's status was fed in here; this
# is the second, independent line of defense at the status layer itself.)
# ----------------------------------------------------------------------------


def test_game_has_not_started_yet_true_when_now_before_scheduled_start():
    now = datetime(2026, 8, 18, 21, 0, 0, tzinfo=timezone.utc)
    assert game_has_not_started_yet("2026-08-19T00:40:00Z", now_utc=now) is True


def test_game_has_not_started_yet_false_when_now_after_scheduled_start():
    now = datetime(2026, 8, 19, 1, 0, 0, tzinfo=timezone.utc)
    assert game_has_not_started_yet("2026-08-19T00:40:00Z", now_utc=now) is False


def test_game_has_not_started_yet_false_when_no_scheduled_start_available():
    # Never blocks anything when we have no authoritative time to compare --
    # only ever a guard, never itself a source of a wrong answer.
    assert game_has_not_started_yet(None) is False


def test_game_has_not_started_yet_false_for_unparseable_timestamp():
    assert game_has_not_started_yet("not-a-real-timestamp") is False


def test_game_has_not_started_yet_handles_z_suffix_and_milliseconds():
    now = datetime(2026, 8, 18, 21, 0, 0, tzinfo=timezone.utc)
    assert game_has_not_started_yet("2026-08-19T00:40:00.000Z", now_utc=now) is True


def test_impossible_state_guard_blocks_in_play_before_scheduled_start():
    # THE confirmed real regression: MLB says Pre-Game, SportsGameOdds
    # (from the WRONG matched event) says in-play, but the authoritative
    # scheduled start is still ~3.6 hours in the future -- PREGAME must
    # be preserved, not overridden.
    now = datetime(2026, 8, 18, 21, 0, 0, tzinfo=timezone.utc)
    result = resolve_game_status(
        "Scheduled",
        {"started": True, "live": True, "ended": False, "completed": False},
        mlb_scheduled_start_utc="2026-08-19T00:40:00Z",
        now_utc=now,
    )
    assert result == PREGAME


def test_status_override_still_applies_after_scheduled_start_has_passed():
    # The guard must never block a GENUINE override once the game's own
    # scheduled start has actually arrived.
    now = datetime(2026, 8, 19, 1, 30, 0, tzinfo=timezone.utc)
    result = resolve_game_status(
        "Scheduled",
        {"started": True, "live": True, "ended": False, "completed": False},
        mlb_scheduled_start_utc="2026-08-19T00:40:00Z",
        now_utc=now,
    )
    assert result == IN_PLAY


def test_final_override_also_blocked_before_scheduled_start():
    now = datetime(2026, 8, 18, 21, 0, 0, tzinfo=timezone.utc)
    result = resolve_game_status(
        "Scheduled",
        {"started": True, "ended": True, "completed": True},
        mlb_scheduled_start_utc="2026-08-19T00:40:00Z",
        now_utc=now,
    )
    assert result == PREGAME


def test_guard_inapplicable_without_scheduled_start_preserves_old_behavior():
    # Backward compatibility: every pre-Milestone-27.1 caller that never
    # passes mlb_scheduled_start_utc gets EXACTLY the old unconditional
    # override behavior.
    assert resolve_game_status("Pre-Game", {"started": True, "live": True, "ended": False}) == IN_PLAY


def test_guard_does_not_affect_mlb_authoritative_states():
    # The guard only ever gates the PREGAME->override branch -- an
    # explicit MLB Final/In Progress is untouched regardless of scheduled
    # start comparisons.
    now = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)
    assert resolve_game_status("Final", None, mlb_scheduled_start_utc="2026-08-19T00:40:00Z", now_utc=now) == FINAL
