"""Conservative name normalization for matching a DraftKings player name
against our Research Engine's MLB player names.

Only handles genuine FORMATTING differences (accents, suffixes, hyphens,
apostrophes, periods, whitespace) -- never fuzzy/edit-distance matching.
Two different players with similar names must never collapse to the same
normalized string; if that ever happens in practice it should surface as
an ambiguous match, not a silent wrong pick.
"""

import re
import unicodedata

_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(name: str) -> str:
    """'Ronald Acuña Jr.' -> 'ronald acuna'; 'Pete Crow-Armstrong' ->
    'pete crow armstrong'; "T.J. Friedl" -> 'tj friedl'."""
    if not name:
        return ""

    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))

    lowered = without_accents.lower()
    for char in (".", "'", "’", ","):
        lowered = lowered.replace(char, "")
    lowered = lowered.replace("-", " ")

    tokens = [t for t in re.split(r"\s+", lowered.strip()) if t]
    if len(tokens) > 1 and tokens[-1] in _SUFFIXES:
        tokens = tokens[:-1]

    return " ".join(tokens)
