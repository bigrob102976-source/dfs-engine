import math

from projection_engine.models import AIPlayerProjection
from projection_engine.validator import validate_ai_player, validate_ai_projection_slate


def _player(**overrides) -> AIPlayerProjection:
    base = dict(player_id="p1", name="Test Player", team="NYY", player_type="hitter", ai_projection=10.0, ai_ceiling=15.0, ai_floor=5.0)
    base.update(overrides)
    return AIPlayerProjection(**base)


def test_valid_player_has_no_errors():
    assert validate_ai_player(_player()) == []


def test_missing_player_id_rejected():
    errors = validate_ai_player(_player(player_id=""))
    assert any("player_id" in e for e in errors)


def test_missing_name_rejected():
    errors = validate_ai_player(_player(name=""))
    assert any("name" in e for e in errors)


def test_missing_ai_projection_rejected():
    errors = validate_ai_player(_player(ai_projection=None))
    assert any("missing AI Projection" in e for e in errors)


def test_nan_ai_projection_rejected():
    errors = validate_ai_player(_player(ai_projection=float("nan")))
    assert any("finite" in e for e in errors)


def test_infinite_ai_projection_rejected():
    errors = validate_ai_player(_player(ai_projection=float("inf")))
    assert any("finite" in e for e in errors)


def test_negative_ai_projection_rejected():
    errors = validate_ai_player(_player(ai_projection=-5.0))
    assert any("negative" in e for e in errors)


def test_negative_ceiling_rejected():
    errors = validate_ai_player(_player(ai_ceiling=-1.0))
    assert any("ai_ceiling" in e and "negative" in e for e in errors)


def test_none_ceiling_floor_are_allowed():
    assert validate_ai_player(_player(ai_ceiling=None, ai_floor=None)) == []


def test_zero_projection_is_valid():
    assert validate_ai_player(_player(ai_projection=0.0)) == []


# ----------------------------------------------------------------------------
# validate_ai_projection_slate
# ----------------------------------------------------------------------------


def test_slate_splits_valid_and_invalid():
    good = _player(player_id="p1", name="Good Player")
    bad = _player(player_id="p2", name="Bad Player", ai_projection=math.nan)
    valid, warnings = validate_ai_projection_slate([good, bad])
    assert valid == [good]
    assert len(warnings) == 1
    assert "Bad Player" in warnings[0]


def test_slate_all_valid_no_warnings():
    players = [_player(player_id="p1"), _player(player_id="p2", name="Other")]
    valid, warnings = validate_ai_projection_slate(players)
    assert len(valid) == 2
    assert warnings == []


def test_slate_empty_input():
    valid, warnings = validate_ai_projection_slate([])
    assert valid == []
    assert warnings == []
