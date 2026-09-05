"""NFL M14 -- targeted tests for nfl/saved_lineup_models.py."""

import pytest

from nfl.saved_lineup_models import NflSavedLineup, NflSavedLineupSlot, SavedLineupCorruptionError, validate_saved_lineup

DG_ID = 151307
DATE = "2026-09-13"


def _slot(roster_slot, pid, game_start="2026-09-13T17:00:00+00:00"):
    return NflSavedLineupSlot(
        roster_slot=roster_slot, draftkings_player_id=pid, name=f"Player {pid}", team="BUF", opponent="MIA",
        game_id="100", game_start_utc=game_start, position="WR" if roster_slot != "QB" else "QB", salary=6000,
    )


def _lineup(slots):
    return NflSavedLineup(
        lineup_id="l1", sport="NFL", site="DraftKings", draft_group_id=DG_ID, slate_date=DATE,
        created_at="2026-09-10T00:00:00+00:00", updated_at="2026-09-10T00:00:00+00:00",
        mode="projection", stack_config={"qbStackMode": "off"}, slots=slots,
    )


def test_round_trip_to_dict_from_dict():
    lineup = _lineup([_slot("QB", "1")])
    restored = NflSavedLineup.from_dict(lineup.to_dict())
    assert restored.lineup_id == lineup.lineup_id
    assert restored.slots[0].draftkings_player_id == "1"


def test_player_keys():
    lineup = _lineup([_slot("QB", "1"), _slot("WR1", "2")])
    assert lineup.player_keys() == ["1", "2"]


def test_validate_rejects_duplicate_player():
    lineup = _lineup([_slot("QB", "1"), _slot("WR1", "1")])
    with pytest.raises(SavedLineupCorruptionError):
        validate_saved_lineup(lineup)


def test_validate_rejects_duplicate_slot():
    lineup = _lineup([_slot("QB", "1"), _slot("QB", "2")])
    with pytest.raises(SavedLineupCorruptionError):
        validate_saved_lineup(lineup)


def test_validate_passes_clean_lineup():
    lineup = _lineup([_slot("QB", "1"), _slot("WR1", "2")])
    validate_saved_lineup(lineup)  # must not raise


def test_from_dict_rejects_slot_missing_required_field():
    bad = _lineup([_slot("QB", "1")]).to_dict()
    del bad["slots"][0]["salary"]
    with pytest.raises(SavedLineupCorruptionError):
        NflSavedLineup.from_dict(bad)


def test_replace_slots_returns_new_lineup_unchanged_metadata():
    lineup = _lineup([_slot("QB", "1")])
    new_slots = [_slot("QB", "2")]
    updated = lineup.replace_slots(new_slots)
    assert updated.lineup_id == lineup.lineup_id
    assert updated.created_at == lineup.created_at
    assert updated.slots[0].draftkings_player_id == "2"
    assert lineup.slots[0].draftkings_player_id == "1"  # original untouched
