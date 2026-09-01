"""M1M -- sport-neutral serving-state foundation.

Documents the three valid states a customer-facing read of "the current
slate for (sport, slateDate)" can be in. M1 does NOT replace the
existing fresh/stale logic already live in
dashboard/lib/optimizerWorkspace/poolCache.ts (see that file's
PROVIDER_SLATE_STALE_MAX_MS-based freshness tiers, shipped separately)
-- this is foundation/documentation for a later milestone that reads
from the new canonical Postgres tables (M1I) instead of R2-listing.
"""

FRESH = "FRESH"
STALE = "STALE"
ABSENT = "ABSENT"

ALL_SERVING_STATES = frozenset({FRESH, STALE, ABSENT})

# -- semantics, for the record (see this module's own docstring) --
#
# FRESH  A CURRENT slate exists for the requested (sport, slateDate) and
#        was promoted within the freshness window a future milestone
#        will define (mirroring poolCache.ts's existing
#        PROVIDER_SLATE_STALE_MAX_MS concept, generalized).
#
# STALE  A CURRENT slate exists but is older than that freshness window.
#        Still real, still servable (never replaced by mock/synthetic
#        data) -- the customer sees real, just possibly outdated, data
#        with that fact disclosed, exactly as poolCache.ts's shipped
#        stale-but-usable tier already does for the live production path.
#
# ABSENT No valid CURRENT slate has ever been promoted for the requested
#        (sport, slateDate). ABSENT is a valid, honest, first-class
#        state -- it is NEVER represented by:
#          - an error/exception bubbling to the customer unexplained
#          - mock or synthetic data
#          - a fabricated/empty optimizer that looks like a real,
#            empty result
#        A consumer of this state must render an explicit "no slate
#        available" experience, distinguishable from both FRESH and
#        STALE and from a genuine system error.


def describe(state: str) -> str:
    """Returns the semantics paragraph for one state -- used by
    documentation/tests to keep the human-readable description in sync
    with the constant it describes."""
    if state == FRESH:
        return "A CURRENT slate exists and is within the freshness window."
    if state == STALE:
        return "A CURRENT slate exists but is older than the freshness window; still real, still served, disclosed as stale."
    if state == ABSENT:
        return "No CURRENT slate has ever been promoted for this (sport, slateDate); never mock/synthetic/fabricated."
    raise ValueError(f"Unknown serving state '{state}' -- must be one of {sorted(ALL_SERVING_STATES)}")
