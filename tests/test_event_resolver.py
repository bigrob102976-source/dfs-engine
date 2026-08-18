"""Milestone 27.1 -- deterministic provider-event resolution.

Regression fixture modeled EXACTLY after the confirmed real bug
(2026-08-18): SportsGameOdds returned THREE LAD @ COL events across a
real 3-game series (yesterday, already in-play; today, upcoming; tomorrow,
upcoming) -- team-name-only matching picked yesterday's, wrongly reporting
today's game as already started."""

from research.game_environment.providers.event_resolver import (
    AMBIGUOUS,
    MATCHED,
    NOT_MATCHED,
    resolve_provider_event,
)
from research.game_environment.providers.models import NormalizedGameOdds


def make_event(event_id: str, home: str, away: str, game_time_utc: str, **overrides) -> NormalizedGameOdds:
    return NormalizedGameOdds(
        provider="sportsgameodds", event_id=event_id, league="MLB", home_team=home, away_team=away,
        game_time_utc=game_time_utc, retrieved_at="2026-08-18T18:00:00+00:00", **overrides,
    )


# ----------------------------------------------------------------------------
# The exact real LAD/COL 3-day series regression fixture
# ----------------------------------------------------------------------------

GAME_A_YESTERDAY = make_event("evt_yesterday", "COL", "LAD", "2026-08-18T00:40:00.000Z")  # already in-play, wrong day
GAME_B_TODAY = make_event("evt_today", "COL", "LAD", "2026-08-19T00:40:00.000Z")  # the real target
GAME_C_TOMORROW = make_event("evt_tomorrow", "COL", "LAD", "2026-08-20T00:40:00.000Z")

MLB_SCHEDULED_START_TODAY = "2026-08-19T00:40:00Z"  # authoritative MLB games.json value for today's actual game


def test_lad_col_regression_resolver_selects_todays_game_not_yesterdays():
    events = [GAME_A_YESTERDAY, GAME_B_TODAY, GAME_C_TOMORROW]
    resolution = resolve_provider_event(events, "COL", "LAD", MLB_SCHEDULED_START_TODAY)
    assert resolution.status == MATCHED
    assert resolution.event.event_id == "evt_today"
    assert resolution.candidates_considered == 3


def test_lad_col_regression_wrong_day_event_is_rejected_even_though_teams_match():
    # Explicit negative assertion: the OLD naive matcher (team-name-only,
    # first-in-list) would have picked evt_yesterday here.
    events = [GAME_A_YESTERDAY, GAME_B_TODAY, GAME_C_TOMORROW]
    resolution = resolve_provider_event(events, "COL", "LAD", MLB_SCHEDULED_START_TODAY)
    assert resolution.event.event_id != "evt_yesterday"


# ----------------------------------------------------------------------------
# Same teams on consecutive days / series disambiguation (general case)
# ----------------------------------------------------------------------------


def test_same_teams_consecutive_days_disambiguated_by_time():
    day1 = make_event("evt1", "NYY", "BOS", "2026-08-17T23:05:00Z")
    day2 = make_event("evt2", "NYY", "BOS", "2026-08-18T23:05:00Z")
    resolution = resolve_provider_event([day1, day2], "NYY", "BOS", "2026-08-18T23:05:00Z")
    assert resolution.status == MATCHED
    assert resolution.event.event_id == "evt2"


def test_provider_event_start_time_matching_within_tolerance():
    # A legitimate small scheduling discrepancy (rain delay, provider
    # rounding) must still match -- within the configured tolerance.
    mlb_start = "2026-08-18T23:05:00Z"
    slightly_off = make_event("evt1", "NYY", "BOS", "2026-08-18T22:00:00Z")  # 1h5m off
    resolution = resolve_provider_event([slightly_off], "NYY", "BOS", mlb_start)
    assert resolution.status == MATCHED


def test_provider_event_far_outside_tolerance_is_not_matched():
    mlb_start = "2026-08-18T23:05:00Z"
    wrong_day = make_event("evt1", "NYY", "BOS", "2026-08-19T23:05:00Z")  # 24h off
    resolution = resolve_provider_event([wrong_day], "NYY", "BOS", mlb_start)
    assert resolution.status == NOT_MATCHED
    assert resolution.event is None


# ----------------------------------------------------------------------------
# Doubleheaders
# ----------------------------------------------------------------------------


def test_doubleheader_two_games_same_day_disambiguated_by_time():
    game1 = make_event("evt_g1", "CHC", "STL", "2026-08-18T18:05:00Z")
    game2 = make_event("evt_g2", "CHC", "STL", "2026-08-18T22:35:00Z")
    # Game 2's authoritative MLB start should resolve to evt_g2, not evt_g1.
    resolution = resolve_provider_event([game1, game2], "CHC", "STL", "2026-08-18T22:35:00Z")
    assert resolution.status == MATCHED
    assert resolution.event.event_id == "evt_g2"


def test_doubleheader_games_close_together_within_tolerance_are_ambiguous():
    # Two games only ~3 hours apart (inside the 4h tolerance) can't be
    # told apart by time alone -- never guess, report AMBIGUOUS.
    game1 = make_event("evt_g1", "CHC", "STL", "2026-08-18T18:05:00Z")
    game2 = make_event("evt_g2", "CHC", "STL", "2026-08-18T21:00:00Z")
    resolution = resolve_provider_event([game1, game2], "CHC", "STL", "2026-08-18T19:30:00Z")
    assert resolution.status == AMBIGUOUS
    assert resolution.event is None


# ----------------------------------------------------------------------------
# Ambiguity / no-authoritative-time fallback behavior
# ----------------------------------------------------------------------------


def test_multiple_candidates_no_mlb_time_available_is_ambiguous_never_guessed():
    events = [GAME_A_YESTERDAY, GAME_B_TODAY]
    resolution = resolve_provider_event(events, "COL", "LAD", None)
    assert resolution.status == AMBIGUOUS
    assert resolution.event is None


def test_single_candidate_no_mlb_time_available_still_matches_unambiguous_case():
    # Backward compatible: when there is truly only one candidate and no
    # time to compare, using it is not a guess.
    resolution = resolve_provider_event([GAME_B_TODAY], "COL", "LAD", None)
    assert resolution.status == MATCHED
    assert resolution.event.event_id == "evt_today"


def test_zero_team_matches_is_not_matched():
    resolution = resolve_provider_event([GAME_B_TODAY], "NYY", "BOS", "2026-08-18T23:05:00Z")
    assert resolution.status == NOT_MATCHED
    assert resolution.candidates_considered == 0


def test_unparseable_mlb_timestamp_with_single_candidate_still_matches():
    resolution = resolve_provider_event([GAME_B_TODAY], "COL", "LAD", "not-a-real-timestamp")
    assert resolution.status == MATCHED


def test_unparseable_mlb_timestamp_with_multiple_candidates_is_ambiguous():
    events = [GAME_A_YESTERDAY, GAME_B_TODAY]
    resolution = resolve_provider_event(events, "COL", "LAD", "not-a-real-timestamp")
    assert resolution.status == AMBIGUOUS


# ----------------------------------------------------------------------------
# Timezone / UTC parsing correctness
# ----------------------------------------------------------------------------


def test_z_suffix_and_offset_notation_parse_to_the_same_instant():
    # "...Z" and "...+00:00" must be treated as identical instants.
    event_z = make_event("evt_z", "LAD", "SD", "2026-08-18T23:05:00Z")
    resolution = resolve_provider_event([event_z], "LAD", "SD", "2026-08-18T23:05:00+00:00")
    assert resolution.status == MATCHED


def test_milliseconds_in_provider_timestamp_do_not_break_matching():
    event_ms = make_event("evt_ms", "LAD", "SD", "2026-08-18T23:05:00.000Z")
    resolution = resolve_provider_event([event_ms], "LAD", "SD", "2026-08-18T23:05:00Z")
    assert resolution.status == MATCHED
