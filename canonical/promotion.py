"""M1N -- the promotion contract.

Documents and enforces (via decide_promotion, a pure decision function)
the required lifecycle:

    FETCHED -> RAW_STORED -> NORMALIZED -> VALIDATED -> PROMOTABLE -> CURRENT

M1 does NOT wire this into any production write path -- no live
DraftKings response is captured into a RAW namespace, no NORMALIZED R2
artifact is written from production, and no Postgres CURRENT row is
promoted by this milestone (see canonical/__init__.py). This module is
the documented contract + a pure, side-effect-free decision function a
later milestone's real promotion pipeline will call before it writes
anything -- the function does not itself touch R2 or Postgres.
"""

from dataclasses import dataclass
from typing import List, Optional

# -- lifecycle stages, in order --
FETCHED = "FETCHED"
RAW_STORED = "RAW_STORED"
NORMALIZED = "NORMALIZED"
VALIDATED = "VALIDATED"
PROMOTABLE = "PROMOTABLE"
CURRENT = "CURRENT"

LIFECYCLE_ORDER = (FETCHED, RAW_STORED, NORMALIZED, VALIDATED, PROMOTABLE, CURRENT)


@dataclass
class PromotionDecision:
    """The result of evaluating whether a normalized artifact may
    advance CURRENT. `may_promote=False` NEVER means "clear CURRENT" --
    it means "leave whatever CURRENT already holds untouched" (rule 5
    below)."""

    may_promote: bool
    reached_stage: str
    reasons: List[str]


def decide_promotion(
    *,
    raw_capture_succeeded: bool,
    normalization_succeeded: bool,
    structural_validation_passed: bool,
    provenance_realism_passed: bool,
) -> PromotionDecision:
    """Pure decision function -- callers pass in the outcomes of each
    stage (already run elsewhere: structural validation reuses
    draftkings_unofficial/structural_validation.py's pattern, provenance/
    realism reuses dfs/providers/source_provenance.py +
    source_realism.py, per the M0 audit's REUSE recommendation) and get
    back whether CURRENT may advance, and how far the artifact actually
    got.

    Rules enforced here (M1N):
      1. HTTP success alone allows RAW capture (raw_capture_succeeded is
         the caller's own signal for that -- this function doesn't make
         HTTP calls).
      2. RAW may exist even if normalization fails -- reflected by
         reached_stage stopping at RAW_STORED without raising.
      3. NORMALIZED only reached if normalization succeeds.
      4. CURRENT (may_promote=True) only when normalization succeeded
         AND both validation layers passed.
      5. Any failure => may_promote=False. This function has no
         reference to any existing CURRENT state and cannot clear it --
         by construction, a caller that only ever writes CURRENT when
         may_promote is True can never silently substitute or erase a
         previously-valid CURRENT row with a failed attempt.
      6. Identity-unresolved players are NOT inputs to this decision at
         all -- see canonical/identity_matching.py; an unresolved
         identity never fails validation and never appears in `reasons`.
    """
    reasons: List[str] = []

    if not raw_capture_succeeded:
        reasons.append("RAW capture did not succeed -- promotion pipeline cannot proceed past FETCHED.")
        return PromotionDecision(may_promote=False, reached_stage=FETCHED, reasons=reasons)

    if not normalization_succeeded:
        reasons.append("Normalization failed -- RAW is preserved, but no NORMALIZED artifact exists.")
        return PromotionDecision(may_promote=False, reached_stage=RAW_STORED, reasons=reasons)

    if not structural_validation_passed:
        reasons.append("Structural validation failed -- NORMALIZED artifact exists but is not VALIDATED.")
        return PromotionDecision(may_promote=False, reached_stage=NORMALIZED, reasons=reasons)

    if not provenance_realism_passed:
        reasons.append("Provenance/realism validation failed -- CURRENT will not be advanced or cleared.")
        return PromotionDecision(may_promote=False, reached_stage=NORMALIZED, reasons=reasons)

    reasons.append("All validation layers passed -- eligible to advance CURRENT.")
    return PromotionDecision(may_promote=True, reached_stage=PROMOTABLE, reasons=reasons)
