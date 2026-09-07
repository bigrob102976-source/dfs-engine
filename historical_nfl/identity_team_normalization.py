"""NFL M6B Phase 5 -- nflverse team abbreviation -> DraftKings team
abbreviation normalization.

Reuses config/nfl_team_abbreviations.py::DK_NFL_TEAM_ABBREVIATIONS (the
real, confirmed-live DraftKings vocabulary from NFL M1) as the target
space -- everything normalizes TO DraftKings' own abbreviations, same
convention as nfl/odds_matching.py's normalize_odds_provider_team_abbr().

Deliberately a SEPARATE exception table from
config/nfl_team_abbreviations.py::ODDS_PROVIDER_TO_DK_TEAM_ABBR -- that
one is scoped to odds providers (still empty, no odds provider is
configured anywhere in this project) and nflverse is a genuinely
different source with its own independently-observed naming.

The ONE real, confirmed exception (audited live during M6B Phase 1/5,
comparing config/nfl_team_abbreviations.py::DK_NFL_TEAM_ABBREVIATIONS
against nflreadpy.load_rosters(seasons=2026)'s real `team` column):
nflverse uses "LA" for the Los Angeles Rams; DraftKings uses "LAR".
Every other one of the 32 real team codes matched exactly -- no other
exception is added because none was observed."""

from typing import Optional

from config.nfl_team_abbreviations import DK_NFL_TEAM_ABBREVIATIONS

NFLVERSE_TO_DK_TEAM_ABBR = {
    "LA": "LAR",
}


def normalize_nflverse_team_abbr(nflverse_abbr: Optional[str]) -> str:
    """Maps an nflverse team abbreviation onto DraftKings' own. Unknown/
    unmapped codes pass through unchanged (same convention as
    nfl/odds_matching.py's normalize_odds_provider_team_abbr) -- an
    unrecognized code is reported by the caller as a real mismatch, not
    silently swallowed here."""
    code = (nflverse_abbr or "").strip().upper()
    return NFLVERSE_TO_DK_TEAM_ABBR.get(code, code)


def is_known_dk_team(team_abbr: Optional[str]) -> bool:
    return (team_abbr or "").strip().upper() in DK_NFL_TEAM_ABBREVIATIONS
