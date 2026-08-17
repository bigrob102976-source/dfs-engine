"""Uncertainty model: ceiling / floor / variance / confidence.

--------------------------------------------------------------------------
Ceiling / floor: exact per-trial categorical variance, not arbitrary
multipliers
--------------------------------------------------------------------------
Each plate appearance (hitter) / batter faced (pitcher) is modeled as one
categorical trial over the SAME event probabilities the projection itself
uses, each with a known DK point value (the "other" outcome -- an out, or
a strikeout for a hitter -- has value 0 and is never listed explicitly,
since it contributes 0 to every sum below). For one trial:

    mu  = sum(p_i * value_i)
    var = sum(p_i * value_i^2) - mu^2

This is the exact, standard variance of a categorical random variable --
no approximation at this level. Across N independent trials (the
independence-across-PA/BF assumption is the one standard simplification
here, documented below):

    mean_total = N * mu
    var_total  = N * var
    SD = sqrt(var_total)
    ceiling = projection + CEILING_Z * SD
    floor   = max(MIN_FLOOR_POINTS, projection - FLOOR_Z * SD)

Stolen bases (hitters) are modeled as a SEPARATE Bernoulli trial layer
over the same N=expected_pa opportunities (a stolen base is a base
-running event, not a plate-appearance outcome, so it doesn't share the
same categorical trial as 1B/2B/3B/HR/BB/HBP) and its variance is added
independently: var_sb = N * p * (1-p) * value^2.

--------------------------------------------------------------------------
Documented V1 limitations
--------------------------------------------------------------------------
1. Approximate normality: ceiling/floor treat the SUMMED per-PA/BF outcome
   distribution as approximately normal (mean +/- Z*SD). For a large-ish N
   this is a standard, defensible approximation (Lyapunov CLT territory);
   for very small N (e.g. a 2-inning reliever) it's cruder, which is why
   confidence (below) is separately sample-size-aware.
2. Independence across trials: ignores same-game/lineup-protection
   correlation (e.g. a leadoff hitter's HR slightly raises the #2 hitter's
   real-world RBI odds). Full Monte Carlo lineup simulation is explicitly
   out of scope for V1 per the milestone's own guidance to use "the
   simplest statistically defensible approach" when full simulation isn't
   feasible.
3. Runs/RBI (hitters) and innings-pitched/earned-runs (pitchers) are
   DETERMINISTIC linear functions of the same regressed rates (see
   dk_scoring.py), not fresh probabilistic draws with their own derived
   distribution. V1 gives their contribution to variance a bounded SD tied
   to the SAME opportunity-confidence signal already computed upstream
   (HitterOpportunity.pa_confidence / PitcherOpportunity.workload_confidence)
   rather than inventing a second, unfounded probability distribution for
   them -- see config.native_projection_config.DETERMINISTIC_COMPONENT_UNCERTAINTY_COEFFICIENT
   for the exact formula and why it's additive (bounded) rather than a
   mean-ratio scale factor (which is unstable whenever the primary
   categorical-trial mean is small, e.g. a low-strikeout-rate pitcher
   whose K/BB/HBP/hit points nearly cancel to ~0).

--------------------------------------------------------------------------
Confidence
--------------------------------------------------------------------------
A continuous blend of THREE things, each already 0..1 (config.native_projection_config
.CONFIDENCE_*_WEIGHT, summing to 1.0): the SAME season/recent stabilization
ratios (observed_n / (observed_n + K)) used for rate regression, plus a
data-completeness fraction (optional inputs actually available vs.
defaulted). K rate's own stabilization constant is used as the
"representative" sample-size signal for season/recent ratios (K rate is
the most reliably measured, fastest-stabilizing rate for both hitters and
pitchers) -- this is a documented simplification, not a claim that K rate
alone determines confidence; completeness_fraction (from hitter_rates.py/
pitcher_rates.py's own field-availability tracking) covers the rest.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from config import native_projection_config as cfg
from config.batter_scoring_config import DK_HITTER_SCORING
from config.scoring_config import DK_SCORING

from native_projections.hitter_rates import HitterRates
from native_projections.pitcher_rates import PitcherRates
from native_projections.playing_time import PitcherOpportunity


@dataclass
class UncertaintyResult:
    ceiling: float
    floor: float
    confidence: float
    variance: float


def _categorical_trial_stats(probabilities_and_values: List[Tuple[float, float]]) -> Tuple[float, float]:
    mu = sum(p * v for p, v in probabilities_and_values)
    e_v_squared = sum(p * (v ** 2) for p, v in probabilities_and_values)
    var = max(e_v_squared - mu * mu, 0.0)
    return mu, var


def compute_confidence(
    season_opportunities: Optional[float],
    season_k_stat: float,
    recent_opportunities: Optional[float],
    recent_k_stat: float,
    completeness_fraction: float,
) -> float:
    season_ratio = (season_opportunities / (season_opportunities + season_k_stat)) if season_opportunities else 0.0
    recent_ratio = (recent_opportunities / (recent_opportunities + recent_k_stat)) if recent_opportunities else 0.0
    raw = (
        cfg.CONFIDENCE_SEASON_WEIGHT * season_ratio
        + cfg.CONFIDENCE_RECENT_WEIGHT * recent_ratio
        + cfg.CONFIDENCE_COMPLETENESS_WEIGHT * completeness_fraction
    )
    scaled = raw * 100.0
    return round(max(cfg.MIN_CONFIDENCE, min(cfg.MAX_CONFIDENCE, scaled)), 1)


def _deterministic_component_variance(deterministic_points: float, opportunity_confidence: float) -> float:
    sd = abs(deterministic_points) * (1 - opportunity_confidence / 100.0) * cfg.DETERMINISTIC_COMPONENT_UNCERTAINTY_COEFFICIENT
    return sd ** 2


def hitter_uncertainty(
    rates: HitterRates,
    expected_pa: float,
    base_projection: float,
    pa_confidence: float,
    season_pa: Optional[float],
    recent_pa: Optional[float],
    completeness_fraction: float,
) -> UncertaintyResult:
    primary_events = [
        (rates.single_rate, DK_HITTER_SCORING["single"]),
        (rates.double_rate, DK_HITTER_SCORING["double"]),
        (rates.triple_rate, DK_HITTER_SCORING["triple"]),
        (rates.home_run_rate, DK_HITTER_SCORING["home_run"]),
        (rates.walk_rate, DK_HITTER_SCORING["walk"]),
        (rates.hit_by_pitch_rate, DK_HITTER_SCORING["hit_by_pitch"]),
    ]
    mu_pa, var_pa = _categorical_trial_stats(primary_events)
    mean_pa_total = expected_pa * mu_pa
    var_pa_total = expected_pa * var_pa

    p_sb = rates.stolen_base_rate
    value_sb = DK_HITTER_SCORING["stolen_base"]
    mean_sb_total = expected_pa * p_sb * value_sb
    var_sb_total = expected_pa * p_sb * (1 - p_sb) * (value_sb ** 2)

    primary_mean = mean_pa_total + mean_sb_total
    primary_var = var_pa_total + var_sb_total

    deterministic_points = base_projection - primary_mean  # Runs + RBI approximation (dk_scoring.py)
    total_var = primary_var + _deterministic_component_variance(deterministic_points, pa_confidence)
    total_sd = math.sqrt(max(total_var, 0.0))

    ceiling = base_projection + cfg.CEILING_Z * total_sd
    floor = max(cfg.MIN_FLOOR_POINTS, base_projection - cfg.FLOOR_Z * total_sd)

    confidence = compute_confidence(
        season_pa, cfg.HITTER_STABILIZATION_PA["k_rate"], recent_pa, cfg.HITTER_RECENT_STABILIZATION_PA, completeness_fraction
    )

    return UncertaintyResult(
        ceiling=round(ceiling, 3), floor=round(floor, 3), confidence=confidence, variance=round(total_var, 3)
    )


def pitcher_uncertainty(
    rates: PitcherRates,
    opportunity: PitcherOpportunity,
    base_projection: float,
    season_bf: Optional[float],
    recent_bf: Optional[float],
    completeness_fraction: float,
) -> UncertaintyResult:
    primary_events = [
        (rates.strikeout_rate, DK_SCORING["strikeout"]),
        (rates.walk_rate, DK_SCORING["walk"]),
        (rates.hit_by_pitch_rate, DK_SCORING["hit_batsman"]),
        (rates.hit_rate, DK_SCORING["hit_against"]),
    ]
    mu_bf, var_bf = _categorical_trial_stats(primary_events)
    primary_mean = opportunity.expected_batters_faced * mu_bf
    primary_var = opportunity.expected_batters_faced * var_bf

    deterministic_points = base_projection - primary_mean  # Innings-pitched + earned-run points (dk_scoring.py)
    total_var = primary_var + _deterministic_component_variance(deterministic_points, opportunity.workload_confidence)
    total_sd = math.sqrt(max(total_var, 0.0))

    ceiling = base_projection + cfg.CEILING_Z * total_sd
    floor = max(cfg.MIN_FLOOR_POINTS, base_projection - cfg.FLOOR_Z * total_sd)

    confidence = compute_confidence(
        season_bf, cfg.PITCHER_STABILIZATION_BF["k_rate"], recent_bf, cfg.PITCHER_RECENT_STABILIZATION_BF, completeness_fraction
    )

    return UncertaintyResult(
        ceiling=round(ceiling, 3), floor=round(floor, 3), confidence=confidence, variance=round(total_var, 3)
    )
