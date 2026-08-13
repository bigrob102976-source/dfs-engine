"""Crosswalk between DraftKings team abbreviations and the abbreviations
our Research Engine uses (which follow the MLB Stats API directly -- see
research/collector.py / research/normalizer.py).

Verified mismatches (research_output/*/teams.json abbreviations vs.
DraftKings' commonly used ones): Arizona is "AZ" in our research package
but DraftKings has historically used "ARI"; the Athletics are "ATH" in
our research package (current MLB Stats API franchise code) but older
DraftKings exports use "OAK". Every other team abbreviation observed in
our research package matches DraftKings' convention directly, so this
map only needs to carry the known exceptions -- everything else passes
through unchanged.

This is a deliberately small, explicit, testable table -- NOT fuzzy
matching. If DraftKings ever renames one of these, add the new code here
rather than trying to infer it.
"""

DK_TO_RESEARCH_TEAM_ABBR = {
    "ARI": "AZ",
    "OAK": "ATH",
}


def normalize_dk_team_abbr(dk_abbrev: str) -> str:
    """Map a DraftKings team abbreviation onto our research package's
    abbreviation. Unknown/unmapped codes pass through unchanged (most do)."""
    code = (dk_abbrev or "").strip().upper()
    return DK_TO_RESEARCH_TEAM_ABBR.get(code, code)
