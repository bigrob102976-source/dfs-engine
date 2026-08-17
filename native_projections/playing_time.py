"""Playing-time / opportunity models: expected plate appearances for
hitters, expected innings/batters-faced/pitch-count for pitchers.

This is the FIRST stage of the pipeline (Baseball Data -> Expected
Opportunities in the milestone's architecture diagram) -- everything
downstream (hitter_rates.py/pitcher_rates.py, matchup.py, dk_scoring.py)
multiplies a per-opportunity rate by the counts computed here.

No network calls, no invented data: every number here comes directly from
an already-collected models.batter.BatterInput / models.pitcher.PitcherInput
field, or an explicit, documented league-average fallback flagged in
`reasons` and reflected in a lower confidence.
"""

from typing import List

from config import native_projection_config as cfg
from models.batter import BatterInput
from models.pitcher import PitcherInput

from native_projections.models import HitterOpportunity, PitcherOpportunity


def project_hitter_opportunity(b: BatterInput) -> HitterOpportunity:
    """Batting order materially drives expected PA (a #1 hitter gets
    meaningfully more expected PA than a #9 hitter) -- see
    config.native_projection_config.EXPECTED_PA_BY_ORDER, which reuses the
    project's existing, already-real expected-PA-by-order table rather
    than re-deriving a second copy.

    A hitter with no confirmed batting order gets the league-average
    fallback PA at zero confidence -- in practice this should not happen
    for a real slate (BatterInput is only ever built for hitters in a
    POSTED starting lineup, per research/adapters/batter_input.py), but
    this function does not assume that invariant holds forever."""
    reasons: List[str] = []

    if b.batting_order is None:
        reasons.append(
            "No confirmed batting order -- lineup not yet posted; using league-average PA fallback at zero confidence"
        )
        return HitterOpportunity(
            expected_pa=cfg.DEFAULT_EXPECTED_PA,
            pa_confidence=cfg.PA_CONFIDENCE_UNCONFIRMED,
            reasons=reasons,
        )

    expected_pa = cfg.EXPECTED_PA_BY_ORDER.get(b.batting_order, cfg.DEFAULT_EXPECTED_PA)
    reasons.append(f"Batting order {b.batting_order} (confirmed lineup) -> {expected_pa:.1f} expected PA")
    return HitterOpportunity(
        expected_pa=expected_pa,
        pa_confidence=cfg.PA_CONFIDENCE_CONFIRMED,
        reasons=reasons,
    )


def project_pitcher_opportunity(p: PitcherInput) -> PitcherOpportunity:
    """Expected innings/batters-faced/pitch-count workload. Prefers, in
    order: a real per-pitcher expected pitch count (Availability.expected_pitch_count
    -- confirmed by audit to never actually be populated by any current
    collector, but this function does not hardcode that assumption away),
    then the pitcher's own recent-starts pitch-count average, then a
    documented league-wide default -- each tier explicitly lowers
    workload_confidence rather than pretending the estimate is equally
    trustworthy either way."""
    reasons: List[str] = []

    if p.availability.expected_pitch_count is not None:
        expected_pitch_count = p.availability.expected_pitch_count
        confidence = cfg.WORKLOAD_CONFIDENCE_WITH_REAL_PITCH_COUNT
        reasons.append(f"Expected pitch count from availability data: {expected_pitch_count:.0f}")
    elif p.recent.pitch_count_average is not None:
        expected_pitch_count = p.recent.pitch_count_average
        confidence = cfg.WORKLOAD_CONFIDENCE_WITH_RECENT_AVERAGE_ONLY
        reasons.append(f"No confirmed pitch-count target -- using recent-starts average: {expected_pitch_count:.0f}")
    else:
        expected_pitch_count = cfg.DEFAULT_EXPECTED_PITCH_COUNT
        confidence = cfg.WORKLOAD_CONFIDENCE_WITH_DEFAULT_ONLY
        reasons.append(f"No pitch-count data available -- using league-average default: {expected_pitch_count:.0f}")

    if p.availability.confirmed_starter is False:
        confidence = max(0.0, confidence - cfg.UNCONFIRMED_STARTER_WORKLOAD_PENALTY)
        reasons.append("Not confirmed as the starter -- workload confidence reduced")
    elif p.availability.confirmed_starter is None:
        confidence = max(0.0, confidence - cfg.UNCONFIRMED_STARTER_WORKLOAD_PENALTY)
        reasons.append("Starter confirmation status unknown -- workload confidence reduced")

    expected_innings = expected_pitch_count / cfg.PITCHES_PER_INNING
    expected_innings = min(max(expected_innings, cfg.MIN_EXPECTED_INNINGS), cfg.MAX_EXPECTED_INNINGS)
    expected_batters_faced = expected_innings * cfg.BATTERS_PER_INNING

    return PitcherOpportunity(
        expected_innings=round(expected_innings, 3),
        expected_batters_faced=round(expected_batters_faced, 3),
        expected_pitch_count=round(expected_pitch_count, 1),
        workload_confidence=round(confidence, 1),
        reasons=reasons,
    )
