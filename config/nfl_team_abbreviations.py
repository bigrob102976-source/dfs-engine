"""Crosswalk between an odds provider's NFL team naming and DraftKings'
own NFL team abbreviations (draftkings_unofficial/structural_
validation.py::VALID_NFL_TEAM_ABBREVIATIONS -- confirmed live against
real DraftGroup 151307).

Mirrors dfs/team_abbreviations.py's exact discipline: a deliberately
small, explicit, testable exception table -- NOT fuzzy matching. If an
odds provider's abbreviation differs from DraftKings' own (e.g. the
JAX/JAC, LA/LAR, WSH/WAS style mismatches common across sports data
vendors), add the specific verified exception here.

DELIBERATELY EMPTY OF REAL EXCEPTIONS as of NFL M5: no odds provider
credentials exist anywhere in this project today (checked both this
local environment and the real MLB production Railway deployment) --
see nfl/odds_matching.py's module docstring. Populating this table from
public knowledge instead of a real inspected payload would violate this
project's "never invent unverified data" discipline (the exact mistake
dfs/team_abbreviations.py's own docstring warns against: "NOT fuzzy
matching... add the new code here rather than trying to infer it").
Populate this once a real provider is configured and its actual event
payloads can be inspected.
"""

from typing import Optional

# Real DraftKings NFL team abbreviations, confirmed live (NFL M1) --
# every one of these is a passthrough target; only genuine, VERIFIED
# provider-side mismatches belong in the exception map below.
DK_NFL_TEAM_ABBREVIATIONS = frozenset({
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
})

# provider_abbr -> DraftKings' own abbreviation. Empty until a real
# odds provider's real payload reveals an actual mismatch -- see this
# module's docstring for why nothing is pre-populated from assumption.
ODDS_PROVIDER_TO_DK_TEAM_ABBR = {}


def normalize_odds_provider_team_abbr(provider_abbr: str) -> str:
    """Maps an odds provider's team abbreviation onto DraftKings' own.
    Unknown/unmapped codes pass through unchanged, exactly like
    dfs/team_abbreviations.py::normalize_dk_team_abbr()."""
    code = (provider_abbr or "").strip().upper()
    return ODDS_PROVIDER_TO_DK_TEAM_ABBR.get(code, code)
