import pytest

from research.innings import (
    decimal_innings_to_notation,
    innings_notation_to_outs,
    outs_to_decimal_innings,
    outs_to_innings_notation,
)


@pytest.mark.parametrize("notation,expected_outs", [
    ("6.0", 18),
    ("6.1", 19),
    ("6.2", 20),
    ("0.0", 0),
    ("0.1", 1),
    ("0.2", 2),
    (6, 18),      # bare int, no fractional part
    (6.0, 18),    # bare float that happens to be a whole number
    ("138.0", 414),
])
def test_innings_notation_to_outs(notation, expected_outs):
    assert innings_notation_to_outs(notation) == expected_outs


@pytest.mark.parametrize("bad_notation", ["6.3", "6.5", "6.9", "6.10"])
def test_innings_notation_to_outs_rejects_invalid_fraction(bad_notation):
    with pytest.raises(ValueError):
        innings_notation_to_outs(bad_notation)


def test_outs_to_decimal_innings_is_true_decimal_not_notation():
    # 20 outs = 6 innings + 2 outs = 6.6666..., NOT the notation "6.2".
    assert outs_to_decimal_innings(20) == pytest.approx(6.6666666, rel=1e-6)
    assert outs_to_decimal_innings(18) == 6.0


def test_outs_to_innings_notation():
    assert outs_to_innings_notation(18) == "6.0"
    assert outs_to_innings_notation(19) == "6.1"
    assert outs_to_innings_notation(20) == "6.2"
    assert outs_to_innings_notation(414) == "138.0"


def test_decimal_innings_to_notation_round_trips():
    for outs in (0, 1, 2, 3, 17, 18, 19, 20, 22, 414):
        decimal = outs_to_decimal_innings(outs)
        assert decimal_innings_to_notation(decimal) == outs_to_innings_notation(outs)


def test_naive_decimal_summation_would_be_wrong_demonstration():
    """Documents exactly the bug this module exists to prevent: summing
    baseball notation as if it were decimal gives a different (wrong)
    answer than summing via outs."""
    starts = ["6.2", "6.0", "5.2"]  # 20 + 18 + 17 = 55 outs = 18.333... true innings

    naive_wrong_sum = sum(float(s) for s in starts)  # 6.2 + 6.0 + 5.2 = 17.4 (WRONG)
    correct_outs = sum(innings_notation_to_outs(s) for s in starts)
    correct_decimal = outs_to_decimal_innings(correct_outs)

    assert correct_outs == 55
    assert correct_decimal == pytest.approx(18.3333, rel=1e-4)
    assert naive_wrong_sum != pytest.approx(correct_decimal, rel=1e-2)
