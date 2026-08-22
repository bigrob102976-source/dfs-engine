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
# Milestone 31.2: real (not synthetic/mock) data, but sourced through
# DraftKings' unofficial/undocumented public JSON endpoints rather than
# a credentialed/licensed provider or a user's own CSV export -- see
# draftkings_unofficial/ and dfs/providers/draftkings_unofficial_provider.py.
# Deliberately distinct from DEVELOPMENT_MOCK (that means fabricated
# data; this means real data from an unofficial source) and, like
# DEVELOPMENT_MOCK, deliberately excluded from TRUSTED_FOR_PRODUCTION
# below -- this source is temporary/development-only by explicit design.
UNOFFICIAL_DEVELOPMENT_SOURCE = "UNOFFICIAL_DEVELOPMENT_SOURCE"

# Milestone 32.2B: real DraftKings data from the unofficial endpoints
# that has ADDITIONALLY passed draftkings_unofficial's own structural
# validation (see draftkings_unofficial/structural_validation.py --
# correct DraftGroup/game-type/roster-template/salary-cap shape, no
# unresolved player/team/game inconsistency) AND provider-aware content
# realism (dfs/providers/source_realism.py's PROVIDER_KIND_DRAFTKINGS_
# UNOFFICIAL rules -- which still BLOCK on identity conflation, invalid
# salaries/positions/teams, and any structural inconsistency; only the
# live-proven-legitimate broad pitcher-pool shape is exempted). Distinct
# from the bare UNOFFICIAL_DEVELOPMENT_SOURCE claim above (structural
# validation not yet run/passed) and from SYNTHETIC_VALIDATION (never
# used for data that failed a BLOCK-level check). Still explicitly
# unofficial/undocumented data -- never presented as an official
# DraftKings API -- but per the explicit M32.2B architecture decision
# (DraftKings Unofficial Provider is the sole DK slate source going
# forward, no manual CSV step in the production pipeline), IS trusted
# for production once it has earned that trust through the two
# validation layers above.
DRAFTKINGS_UNOFFICIAL_LIVE = "DRAFTKINGS_UNOFFICIAL_LIVE"

ALL_PROVENANCE_VALUES = (
    OFFICIAL_USER_UPLOAD, AUTHORIZED_PROVIDER, DEVELOPMENT_MOCK, SYNTHETIC_VALIDATION, UNKNOWN,
    UNOFFICIAL_DEVELOPMENT_SOURCE, DRAFTKINGS_UNOFFICIAL_LIVE,
)

# Provenance values a production/live player pool build may trust without
# an explicit dev-mode override -- see dfs/pool_builder.py's
# require_trusted_source(). Deliberately does NOT include DEVELOPMENT_MOCK
# or the bare UNOFFICIAL_DEVELOPMENT_SOURCE (unvalidated) claim: mock/
# unvalidated data is fine for local dev, but a "production" pool build
# should still require an explicit override to use it. DRAFTKINGS_
# UNOFFICIAL_LIVE IS included -- see that constant's own docstring for
# why it has earned production trust.
TRUSTED_FOR_PRODUCTION = frozenset({OFFICIAL_USER_UPLOAD, AUTHORIZED_PROVIDER, DRAFTKINGS_UNOFFICIAL_LIVE})


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
