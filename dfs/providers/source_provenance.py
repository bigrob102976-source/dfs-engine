"""Milestone 27.4 -- explicit provenance classification for a DFS salary
source, distinct from and layered on top of dfs/providers/source_realism.py.

A "provenance claim" is what the INGESTION MECHANISM itself can honestly
assert (did this come through the real upload flow? was it produced by
MockProvider? etc). This module never upgrades that claim -- it can only
DOWNGRADE it to SYNTHETIC_VALIDATION when the content itself fails a
BLOCK-level realism check, since no DFS salary CSV carries a
cryptographic signature proving it came from draftkings.com; content
plausibility is the only signal available after the fact. A file that
arrived through the genuine upload endpoint but is structurally
impossible for a real slate (see source_realism.py) must never be
reported as "real DraftKings validation" just because the upload
mechanism itself was legitimate.
"""

from dfs.providers.source_realism import RealismReport

OFFICIAL_USER_UPLOAD = "OFFICIAL_USER_UPLOAD"
AUTHORIZED_PROVIDER = "AUTHORIZED_PROVIDER"
DEVELOPMENT_MOCK = "DEVELOPMENT_MOCK"
SYNTHETIC_VALIDATION = "SYNTHETIC_VALIDATION"
UNKNOWN = "UNKNOWN"

ALL_PROVENANCE_VALUES = (
    OFFICIAL_USER_UPLOAD, AUTHORIZED_PROVIDER, DEVELOPMENT_MOCK, SYNTHETIC_VALIDATION, UNKNOWN,
)

# Provenance values a production/live player pool build may trust without
# an explicit dev-mode override -- see dfs/pool_builder.py's
# require_trusted_source(). Deliberately does NOT include DEVELOPMENT_MOCK:
# mock data is clearly labeled and fine for local dev, but a "production"
# pool build should still require an explicit override to use it.
TRUSTED_FOR_PRODUCTION = frozenset({OFFICIAL_USER_UPLOAD, AUTHORIZED_PROVIDER})


def classify_source_provenance(mechanism_claim: str, realism: RealismReport) -> str:
    """`mechanism_claim` is what the ingestion path itself asserts (e.g.
    OFFICIAL_USER_UPLOAD for anything that came through
    dfs/providers/draftkings_csv_storage.py's real upload flow,
    DEVELOPMENT_MOCK for MockProvider output). Downgraded to
    SYNTHETIC_VALIDATION whenever the content fails a BLOCK-level
    realism check, regardless of how trustworthy the mechanism claim is."""
    if realism.blocked:
        return SYNTHETIC_VALIDATION
    return mechanism_claim
