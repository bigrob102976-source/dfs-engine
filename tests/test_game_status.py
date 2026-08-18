from research.game_environment.game_status import (
    FINAL,
    IN_PLAY,
    PREGAME,
    UNKNOWN,
    classify_mlb_game_status,
    classify_sportsgameodds_status,
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
