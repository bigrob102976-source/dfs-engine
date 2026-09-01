"""M1A -- canonical slateDate contract tests."""

import pytest

from canonical.slate_date import (
    InvalidGameStartError,
    SlateDateImmutabilityError,
    compute_slate_date,
    compute_slate_date_from_game_starts,
    enforce_slate_date_immutable,
)


def test_ordinary_est_date():
    # Jan 15, 7:05pm ET (EST, UTC-5) = 2026-01-16 00:05 UTC.
    assert compute_slate_date("2026-01-16T00:05:00Z") == "2026-01-15"


def test_ordinary_edt_date():
    # Jul 15, 7:05pm ET (EDT, UTC-4) = 2026-07-15 23:05 UTC.
    assert compute_slate_date("2026-07-15T23:05:00Z") == "2026-07-15"


def test_utc_crossing_midnight_stays_previous_eastern_day():
    # 00:30 UTC is still 7:30-8:30pm the PREVIOUS day in US/Eastern.
    assert compute_slate_date("2026-08-21T00:30:00Z") == "2026-08-20"


def test_eastern_chicago_one_hour_rollover_window():
    # 04:30 UTC = 00:30 ET (already "tomorrow" in Eastern) but 23:30 CT
    # the PREVIOUS day in Chicago -- slateDate must follow Eastern, not
    # Chicago, per the canonical contract.
    assert compute_slate_date("2026-08-21T04:30:00Z") == "2026-08-21"


def test_game_starting_shortly_after_midnight_utc():
    assert compute_slate_date("2026-08-21T00:05:00Z") == "2026-08-20"


def test_dst_spring_forward_boundary():
    # 2026-03-08 07:00 UTC = 2026-03-08 02:00 EST literal instant, but
    # US Eastern springs forward at 2am local on 2026-03-08 -- zoneinfo
    # must resolve this via real tzdata, not a fixed offset.
    assert compute_slate_date("2026-03-08T07:00:00Z") == "2026-03-08"


def test_dst_fall_back_boundary():
    assert compute_slate_date("2026-11-01T05:30:00Z") == "2026-11-01"


def test_explicit_non_utc_offset_accepted():
    assert compute_slate_date("2026-08-20T19:00:00-04:00") == "2026-08-20"


def test_rejects_bare_offsetless_string():
    with pytest.raises(InvalidGameStartError):
        compute_slate_date("2026-08-20T19:00:00")


def test_rejects_empty_string():
    with pytest.raises(InvalidGameStartError):
        compute_slate_date("")


def test_from_game_starts_picks_earliest():
    starts = ["2026-08-20T23:05:00Z", "2026-08-20T19:05:00Z", "2026-08-21T00:10:00Z"]
    assert compute_slate_date_from_game_starts(starts) == "2026-08-20"


def test_from_game_starts_empty_list_raises():
    with pytest.raises(InvalidGameStartError):
        compute_slate_date_from_game_starts([])


def test_stored_slate_date_immutable_on_match():
    assert enforce_slate_date_immutable("2026-08-20", "2026-08-20") == "2026-08-20"


def test_stored_slate_date_first_assignment_always_wins():
    assert enforce_slate_date_immutable(None, "2026-08-20") == "2026-08-20"


def test_stored_slate_date_immutable_rejects_reschedule_drift():
    with pytest.raises(SlateDateImmutabilityError):
        enforce_slate_date_immutable("2026-08-20", "2026-08-21")
