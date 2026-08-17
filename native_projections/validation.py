"""Suspicious-output validation: flags projections that look wrong as
WARNINGS on the snapshot -- never silently clamped, per the milestone's
explicit instruction ("never silently clamp without documenting why").

Checked for every player: absurdly high projection (separate thresholds
for hitters/pitchers), negative projection, ceiling below projection,
floor above projection, a tiny-sample player projecting like an elite
player anyway, and low overall input-data coverage.
"""

from typing import List, Optional

from config import native_projection_config as cfg
from native_projections.models import NativePlayerProjection


def validate_projection(proj: NativePlayerProjection, season_opportunities: Optional[float]) -> List[str]:
    warnings: List[str] = []
    is_hitter = proj.player_type == "hitter"
    suspicious_threshold = cfg.SUSPICIOUS_HITTER_PROJECTION_POINTS if is_hitter else cfg.SUSPICIOUS_PITCHER_PROJECTION_POINTS
    tiny_sample_threshold = cfg.TINY_SAMPLE_HITTER_PA_THRESHOLD if is_hitter else cfg.TINY_SAMPLE_PITCHER_BF_THRESHOLD

    if proj.native_projection > suspicious_threshold:
        warnings.append(
            f"Suspicious: {proj.player_type} projection {proj.native_projection:.2f} exceeds the "
            f"{suspicious_threshold:.1f}-point sanity threshold -- manual review recommended"
        )

    if proj.native_projection < 0:
        warnings.append(f"Negative projection: {proj.native_projection:.2f} -- manual review recommended")

    if proj.native_ceiling < proj.native_projection:
        warnings.append(f"Ceiling ({proj.native_ceiling:.2f}) is below projection ({proj.native_projection:.2f})")

    if proj.native_floor > proj.native_projection:
        warnings.append(f"Floor ({proj.native_floor:.2f}) is above projection ({proj.native_projection:.2f})")

    if season_opportunities is not None and season_opportunities < tiny_sample_threshold:
        elite_cutoff = suspicious_threshold * cfg.TINY_SAMPLE_ELITE_PROJECTION_FRACTION
        if proj.native_projection >= elite_cutoff:
            warnings.append(
                f"Tiny-sample-elite: only {season_opportunities:.0f} season opportunities but projection "
                f"({proj.native_projection:.2f}) is at/above {cfg.TINY_SAMPLE_ELITE_PROJECTION_FRACTION:.0%} of the "
                f"sanity threshold -- verify this isn't residual small-sample noise"
            )

    if proj.input_coverage is not None and proj.input_coverage.fraction < cfg.LOW_INPUT_COVERAGE_WARNING_THRESHOLD:
        warnings.append(
            f"Low input data coverage: only {proj.input_coverage.fraction:.0%} of tracked optional fields available"
        )

    return warnings
