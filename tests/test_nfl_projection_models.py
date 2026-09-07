"""NFL M4 -- targeted tests for nfl/projection_models.py. The core
guarantee under test: a real projected value of 0.0 must stay
distinguishable from a missing (None) projection everywhere -- nothing
here ever coerces one into the other."""

from nfl.projection_models import BIG_MONEY_NATIVE, NflProjectionRecord


def _record(**overrides):
    base = dict(
        sport="NFL", draft_group_id=151307, canonical_player_id="1", draftkings_player_id="1",
        draftable_ids=["10"], name="Test Player", position="QB", team="BUF", opponent="HOU",
        projection=None,
    )
    base.update(overrides)
    return NflProjectionRecord(**base)


def test_missing_projection_is_none_not_zero():
    record = _record(projection=None)
    assert record.projection is None
    assert record.projection != 0.0  # None must never be confused with "projected zero"


def test_real_zero_projection_stays_zero_not_dropped():
    record = _record(projection=0.0)
    assert record.projection == 0.0
    assert record.projection is not None


def test_default_source_and_provenance_are_big_money_native():
    record = _record()
    assert record.source == BIG_MONEY_NATIVE
    assert record.source_provenance == BIG_MONEY_NATIVE


def test_floor_and_ceiling_stay_none_when_not_supplied():
    record = _record(projection=12.5)
    assert record.floor is None
    assert record.ceiling is None


def test_to_dict_round_trips_none_correctly():
    record = _record(projection=None)
    d = record.to_dict()
    assert d["projection"] is None
    assert "projection" in d  # explicit key present, not omitted
