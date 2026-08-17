"""Hitter Event Model: regressed per-PA event rates (1B/2B/3B/HR/BB/HBP/K/SB).

This is the SECOND stage of the pipeline (Expected Opportunities ->
Expected Baseball Outcomes). Everything here operates on RATES (events per
plate appearance); native_projections/hitter_projection.py multiplies these
rates by playing_time.py's expected_pa to get expected event COUNTS.

--------------------------------------------------------------------------
Why regression/shrinkage exists (the documented Andrew Pinckney case)
--------------------------------------------------------------------------
Before this module, the existing Independent Projection (agents/batter_agent.py)
used a rate stat (e.g. a rookie's 1-HR-in-10-PA -> 10% HR rate) at close to
full weight, only discounting it through a capped CONFIDENCE penalty --
the point estimate itself never moved. A hitter with 10 season PA and 1 HR
would therefore project like a real 10%-HR-rate slugger, not like a league
-average hitter who got lucky once.

This module fixes that with two-layer, published-methodology empirical-Bayes
shrinkage (the same family of technique as Tom Tango's public-domain Marcel
forecasting system and Russell Carleton's stabilization-point research):

1. SEASON RATE REGRESSION -- every observed rate is pulled toward a
   league-average prior in proportion to how little data backs it:

       regressed_rate = (observed_events + K_stat * league_avg_rate)
                         / (observed_opportunities + K_stat)

   K_stat ("stabilization point", config.native_projection_config.HITTER_STABILIZATION_PA)
   is the PA sample size at which a rate is roughly half signal / half
   noise for that specific stat (rarer, higher-variance events like HR need
   a smaller K than common events like strikeouts get a smaller K too --
   see the config file's per-stat commentary). A 10-PA sample with
   K_stat=170 for home runs gets pulled about 94% of the way to the league
   -average HR rate; a 550-PA regular barely moves.

2. RECENT-FORM BLEND WEIGHT IS ITSELF SAMPLE-SIZE-DRIVEN (K/BB rate only
   -- see the "why recent form is limited to K/BB" note below):

       recent_weight = recent_opportunities / (recent_opportunities + K_recent)

   capped at MAX_RECENT_BLEND_WEIGHT so recent form can meaningfully move
   the projection without ever fully overriding the season-regressed rate.

--------------------------------------------------------------------------
Why recent-form blending is limited to K rate and BB rate
--------------------------------------------------------------------------
models.batter.RecentBattingStats carries real recent RATES for K% and BB%
(directly comparable to the season rate), but does NOT carry raw recent
hit-type counts (1B/2B/3B/HR) -- only season-level counts exist for those.
Blending a hit-type rate against a *rate that doesn't exist* would mean
either fabricating one or improvising an unfounded Statcast-to-rate
conversion formula, which this project's AI Rules explicitly forbid
("AI should NOT invent statistics"). Recent Statcast QUALITY signals
(barrel%, hard-hit%, xwOBA trend) are real and meaningful, but they are
applied as a separate, explicitly bounded adjustment downstream in
native_projections/matchup.py -- not fabricated into a hit-type rate here.
This keeps hitter_rates.py's job narrow and honest: regress what is
actually a rate, using only real observed counts.

Hit-by-pitch: models.batter.SeasonBattingStats has no raw HBP count at all
(not collected upstream) -- hit_by_pitch_rate is always the documented
league-average constant, flagged in `reasons` and reflected in input
coverage. Stolen bases: only a season count exists (no recent SB data) --
season-only regression, same honesty pattern.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from config import native_projection_config as cfg
from models.batter import BatterInput


@dataclass
class HitterRates:
    single_rate: float
    double_rate: float
    triple_rate: float
    home_run_rate: float
    walk_rate: float
    hit_by_pitch_rate: float
    strikeout_rate: float
    stolen_base_rate: float
    reasons: List[str] = field(default_factory=list)
    coverage_fields_available: int = 0
    coverage_fields_total: int = 0
    coverage_missing_fields: List[str] = field(default_factory=list)


def _shrink(observed_events: Optional[float], observed_opportunities: Optional[float], k_stat: float, league_avg_rate: float) -> float:
    """Marcel-style empirical-Bayes shrinkage toward a league-average prior.
    See this module's docstring for the general formula."""
    if observed_events is None or observed_opportunities is None or observed_opportunities <= 0:
        return league_avg_rate
    return (observed_events + k_stat * league_avg_rate) / (observed_opportunities + k_stat)


def _recent_weight(recent_opportunities: Optional[float], k_recent: float, max_weight: float) -> float:
    if recent_opportunities is None or recent_opportunities <= 0:
        return 0.0
    raw_weight = recent_opportunities / (recent_opportunities + k_recent)
    return min(raw_weight, max_weight)


def project_hitter_rates(b: BatterInput) -> HitterRates:
    reasons: List[str] = []
    season = b.season
    recent = b.recent
    pa = season.plate_appearances
    league = cfg.LEAGUE_AVG_HITTER_RATES
    k_stats = cfg.HITTER_STABILIZATION_PA

    fields_available = 0
    fields_total = 0
    missing_fields: List[str] = []

    def track(field_name: str, value) -> None:
        nonlocal fields_available, fields_total
        fields_total += 1
        if value is not None:
            fields_available += 1
        else:
            missing_fields.append(field_name)

    track("season.plate_appearances", pa)
    track("season.strikeouts", season.strikeouts)
    track("season.walks", season.walks)
    track("season.hits", season.hits)
    track("season.doubles", season.doubles)
    track("season.triples", season.triples)
    track("season.home_runs", season.home_runs)
    track("season.stolen_bases", season.stolen_bases)
    track("season.hit_by_pitch", None)  # never collected upstream -- always missing, tracked honestly
    track("recent.plate_appearances", recent.plate_appearances)
    track("recent.k_percent", recent.k_percent)
    track("recent.bb_percent", recent.bb_percent)

    # ---- Strikeout rate: season regression + real recent-rate blend ----
    season_k_rate = _shrink(season.strikeouts, pa, k_stats["k_rate"], league["k_rate"])
    recent_k_rate = (recent.k_percent / 100.0) if recent.k_percent is not None else None
    k_weight = _recent_weight(recent.plate_appearances, cfg.HITTER_RECENT_STABILIZATION_PA, cfg.MAX_RECENT_BLEND_WEIGHT)
    if recent_k_rate is not None:
        strikeout_rate = (1 - k_weight) * season_k_rate + k_weight * recent_k_rate
        reasons.append(
            f"K rate: season-regressed {season_k_rate:.3f} blended with recent {recent_k_rate:.3f} "
            f"at {k_weight:.0%} recent weight ({recent.plate_appearances:.0f} recent PA)"
        )
    else:
        strikeout_rate = season_k_rate
        reasons.append(f"K rate: season-only, regressed to {season_k_rate:.3f} (no recent K% available)")

    # ---- Walk rate: season regression + real recent-rate blend ----
    season_bb_rate = _shrink(season.walks, pa, k_stats["bb_rate"], league["bb_rate"])
    recent_bb_rate = (recent.bb_percent / 100.0) if recent.bb_percent is not None else None
    bb_weight = _recent_weight(recent.plate_appearances, cfg.HITTER_RECENT_STABILIZATION_PA, cfg.MAX_RECENT_BLEND_WEIGHT)
    if recent_bb_rate is not None:
        walk_rate = (1 - bb_weight) * season_bb_rate + bb_weight * recent_bb_rate
        reasons.append(
            f"BB rate: season-regressed {season_bb_rate:.3f} blended with recent {recent_bb_rate:.3f} "
            f"at {bb_weight:.0%} recent weight ({recent.plate_appearances:.0f} recent PA)"
        )
    else:
        walk_rate = season_bb_rate
        reasons.append(f"BB rate: season-only, regressed to {season_bb_rate:.3f} (no recent BB% available)")

    # ---- Hit-type rates: season-only count-based regression (this is the
    # exact fix for the Pinckney case -- a lone HR in a tiny PA sample gets
    # pulled hard toward league-average home_run_rate rather than standing
    # as a fully-weighted observed rate) ----
    home_run_rate = _shrink(season.home_runs, pa, k_stats["home_run_rate"], league["home_run_rate"])
    double_rate = _shrink(season.doubles, pa, k_stats["double_rate"], league["double_rate"])
    triple_rate = _shrink(season.triples, pa, k_stats["triple_rate"], league["triple_rate"])

    observed_singles = None
    if season.hits is not None and season.doubles is not None and season.triples is not None and season.home_runs is not None:
        observed_singles = max(season.hits - season.doubles - season.triples - season.home_runs, 0)
    single_rate = _shrink(observed_singles, pa, k_stats["single_rate"], league["single_rate"])

    reasons.append(
        f"Hit-type rates (1B/2B/3B/HR): season-only count-based regression -- "
        f"{single_rate:.3f}/{double_rate:.3f}/{triple_rate:.3f}/{home_run_rate:.3f} per PA "
        f"({pa:.0f} season PA)" if pa is not None else
        "Hit-type rates (1B/2B/3B/HR): no season PA available -- using league-average rates"
    )

    # ---- Stolen base rate: season-only regression (no recent SB data exists) ----
    stolen_base_rate = _shrink(season.stolen_bases, pa, k_stats["stolen_base_rate"], league["stolen_base_rate"])

    # ---- Hit-by-pitch rate: always league average (never collected) ----
    hit_by_pitch_rate = league["hbp_rate"]
    reasons.append(f"HBP rate: not tracked by the season stats collector -- using league-average rate {hit_by_pitch_rate:.3f}")

    return HitterRates(
        single_rate=round(single_rate, 4),
        double_rate=round(double_rate, 4),
        triple_rate=round(triple_rate, 4),
        home_run_rate=round(home_run_rate, 4),
        walk_rate=round(walk_rate, 4),
        hit_by_pitch_rate=round(hit_by_pitch_rate, 4),
        strikeout_rate=round(strikeout_rate, 4),
        stolen_base_rate=round(stolen_base_rate, 4),
        reasons=reasons,
        coverage_fields_available=fields_available,
        coverage_fields_total=fields_total,
        coverage_missing_fields=missing_fields,
    )
