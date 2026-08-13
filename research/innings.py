"""Baseball innings-pitched <-> outs conversion.

MLB's "innings pitched" notation is NOT decimal. The fractional part
counts outs within the current inning, not tenths of an inning:

    6.0 IP = 18 outs  (exactly 6 innings)
    6.1 IP = 19 outs  (6 innings + 1 out)
    6.2 IP = 20 outs  (6 innings + 2 outs)

Treating "6.1" or "6.2" as an ordinary decimal (adding/averaging it like
6.1 or 6.2) silently corrupts any innings-pitched arithmetic. Anywhere
this codebase needs to add up or average innings pitched, it must go
through outs (an ordinary integer) and only convert back to baseball
notation for display.
"""

from typing import Union

_VALID_FRACTIONS = ("0", "1", "2")


def innings_notation_to_outs(innings_notation: Union[str, int, float]) -> int:
    """Convert baseball-notation innings pitched (e.g. "6.2", 6.2, or 6)
    to total outs recorded (20).

    Raises ValueError if the fractional part isn't .0, .1, or .2 -- MLB
    innings-pitched notation has no other valid fractional values.
    """
    text = str(innings_notation).strip()
    if "." in text:
        whole_part, frac_part = text.split(".", 1)
    else:
        whole_part, frac_part = text, "0"

    if frac_part not in _VALID_FRACTIONS:
        raise ValueError(
            f"invalid baseball innings-pitched notation: {innings_notation!r} "
            f"(fractional part must be .0, .1, or .2)"
        )

    return int(whole_part) * 3 + int(frac_part)


def outs_to_decimal_innings(outs: int) -> float:
    """Convert total outs to a TRUE decimal innings value (20 outs ->
    6.666...), safe for arithmetic (averaging, summing across starts,
    range-scaling). This is deliberately NOT baseball notation -- use
    `outs_to_innings_notation` for display."""
    return outs / 3.0


def outs_to_innings_notation(outs: int) -> str:
    """Convert total outs to MLB's own display notation (20 -> "6.2")."""
    whole, partial = divmod(int(outs), 3)
    return f"{whole}.{partial}"


def decimal_innings_to_notation(decimal_innings: float) -> str:
    """Round-trip a true-decimal innings value (e.g. from
    `outs_to_decimal_innings`) back to baseball display notation.
    Rounds to the nearest whole out to absorb floating-point noise from
    the outs / 3.0 division."""
    return outs_to_innings_notation(round(decimal_innings * 3))
