"""Pitcher Event Model: regressed per-batters-faced event rates (K/BB/hit
-against/HR-against/HBP) plus a per-inning earned-run rate.

Second pipeline stage for pitchers (Expected Opportunities -> Expected
Baseball Outcomes) -- mirrors native_projections/hitter_rates.py's
methodology exactly (same two-layer empirical-Bayes shrinkage; see that
module's docstring for the general formula and the sabermetric precedent
it follows). native_projections/pitcher_projection.py multiplies these
rates by playing_time.py's expected_batters_faced / expected_innings to
get expected event COUNTS.

--------------------------------------------------------------------------
Real observed counts vs. percentage-only fallback
--------------------------------------------------------------------------
models.pitcher.SeasonStats/RecentStats only carried k_percent/bb_percent
(no raw counts) until Milestone 23 exposed the raw batters_faced/
strikeouts/walks/earned_runs/hits_allowed/home_runs_allowed/hit_by_pitch
fields already being fetched-and-discarded by research/enrichment.py (see
that module's diff). This lets K/BB/hit/HR/HBP rates be regressed against
REAL observed counts rather than reconstructed from a percentage.

Older cached research snapshots predate that change and won't have the raw
counts populated. Rather than treating those pitchers as having zero data
(which would be wrong -- k_percent/bb_percent ARE real), this module falls
back to reconstructing an approximate observed count from the percentage
and an approximate opportunity count (innings * BATTERS_PER_INNING, the
same approximation playing_time.py already uses for workload) -- flagged
in `reasons` as an approximation, never presented as if it were the exact
count.

--------------------------------------------------------------------------
Why hit-rate / home-run-rate / HBP-rate never blend recent form
--------------------------------------------------------------------------
Same reasoning as hitter_rates.py's hit-type rates: these are rare,
high-variance events and RecentStats does not (and, given only ~1-3
recent starts, structurally should not) drive their own shrinkage target
-- three starts of home-run-against data is closer to noise than signal.
Season-only regression is the defensible choice; recent Statcast quality
trends (hard-hit%/barrel% trend) are applied as a separate, explicitly
bounded adjustment in native_projections/matchup.py, not fabricated into
a rate here.

--------------------------------------------------------------------------
Earned-run rate
--------------------------------------------------------------------------
A run "scoring" depends on base-state and sequencing, not a single
categorical batters-faced outcome the way a strikeout or walk does -- so
it's regressed per INNING PITCHED instead, using the pitcher's own real
season earned-run count against real innings pitched, with a league
-average per-inning rate (config.scoring_config's existing
"default_run_rate" / 9) as the shrinkage prior. If the raw earned_runs
count isn't available (older cached snapshot), season ERA / 9 is used as
the observed per-inning rate instead -- ERA is itself a real, already
-computed field, so this is a genuine fallback, not an invented number.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from config import native_projection_config as cfg
from models.pitcher import PitcherInput


@dataclass
class PitcherRates:
    strikeout_rate: float
    walk_rate: float
    hit_rate: float
    home_run_rate: float
    hit_by_pitch_rate: float
    earned_run_rate_per_inning: float
    reasons: List[str] = field(default_factory=list)
    coverage_fields_available: int = 0
    coverage_fields_total: int = 0
    coverage_missing_fields: List[str] = field(default_factory=list)
    # The RESOLVED batters-faced opportunity count actually used for K/BB
    # regression above -- real (season.batters_faced) when available,
    # otherwise the same innings-derived approximation used in the percent
    # -only fallback (see _resolve_count_and_opportunities). Callers (e.g.
    # pitcher_projection.py's confidence/tiny-sample-warning calculations)
    # should use THESE, not raw season.batters_faced directly -- otherwise
    # a pitcher whose rates were genuinely (if approximately) regressed
    # from real k_percent/bb_percent data would incorrectly look like a
    # zero-data player just because the raw count field itself is absent
    # on an older cached snapshot.
    season_opportunities: Optional[float] = None
    recent_opportunities: Optional[float] = None


def _shrink(observed_events: Optional[float], observed_opportunities: Optional[float], k_stat: float, league_avg_rate: float) -> float:
    if observed_events is None or observed_opportunities is None or observed_opportunities <= 0:
        return league_avg_rate
    return (observed_events + k_stat * league_avg_rate) / (observed_opportunities + k_stat)


def _recent_weight(recent_opportunities: Optional[float], k_recent: float, max_weight: float) -> float:
    if recent_opportunities is None or recent_opportunities <= 0:
        return 0.0
    raw_weight = recent_opportunities / (recent_opportunities + k_recent)
    return min(raw_weight, max_weight)


def _approx_batters_faced(innings: Optional[float]) -> Optional[float]:
    if innings is None or innings <= 0:
        return None
    return innings * cfg.BATTERS_PER_INNING


def _resolve_count_and_opportunities(
    raw_count: Optional[int], raw_opportunities: Optional[int], percent: Optional[float], innings: Optional[float]
) -> tuple:
    """Prefer real raw counts; fall back to reconstructing an approximate
    count from a percentage + innings-derived opportunity estimate; return
    (events, opportunities, is_approximate)."""
    if raw_count is not None and raw_opportunities is not None:
        return float(raw_count), float(raw_opportunities), False
    if percent is not None:
        approx_opportunities = _approx_batters_faced(innings)
        if approx_opportunities is not None:
            return (percent / 100.0) * approx_opportunities, approx_opportunities, True
    return None, None, False


def project_pitcher_rates(p: PitcherInput) -> PitcherRates:
    reasons: List[str] = []
    season = p.season
    recent = p.recent
    league = cfg.LEAGUE_AVG_PITCHER_RATES
    k_stats = cfg.PITCHER_STABILIZATION_BF

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

    track("season.batters_faced", season.batters_faced)
    track("season.strikeouts", season.strikeouts)
    track("season.walks", season.walks)
    track("season.hits_allowed", season.hits_allowed)
    track("season.home_runs_allowed", season.home_runs_allowed)
    track("season.hit_by_pitch", season.hit_by_pitch)
    track("season.earned_runs", season.earned_runs)
    track("season.innings", season.innings)
    track("recent.batters_faced", recent.batters_faced)
    track("recent.strikeouts", recent.strikeouts)
    track("recent.walks", recent.walks)

    # ---- K rate: season regression + real/approximate recent-rate blend ----
    season_k_events, season_k_opportunities, k_approx = _resolve_count_and_opportunities(
        season.strikeouts, season.batters_faced, season.k_percent, season.innings
    )
    season_k_rate = _shrink(season_k_events, season_k_opportunities, k_stats["k_rate"], league["k_rate"])
    if k_approx:
        reasons.append("K rate: season count reconstructed from k_percent (no raw batters-faced count on this snapshot)")

    recent_k_events, recent_k_opportunities, recent_k_approx = _resolve_count_and_opportunities(
        recent.strikeouts, recent.batters_faced, recent.k_percent, recent.innings
    )
    k_weight = _recent_weight(recent_k_opportunities, cfg.PITCHER_RECENT_STABILIZATION_BF, cfg.MAX_RECENT_BLEND_WEIGHT)
    if recent_k_opportunities is not None and recent_k_events is not None:
        recent_k_rate = recent_k_events / recent_k_opportunities
        strikeout_rate = (1 - k_weight) * season_k_rate + k_weight * recent_k_rate
        reasons.append(
            f"K rate: season-regressed {season_k_rate:.3f} blended with recent {recent_k_rate:.3f} "
            f"at {k_weight:.0%} recent weight ({recent_k_opportunities:.0f} recent BF"
            f"{', approximated' if recent_k_approx else ''})"
        )
    else:
        strikeout_rate = season_k_rate
        reasons.append(f"K rate: season-only, regressed to {season_k_rate:.3f} (no usable recent data)")

    # ---- BB rate: same pattern ----
    season_bb_events, season_bb_opportunities, bb_approx = _resolve_count_and_opportunities(
        season.walks, season.batters_faced, season.bb_percent, season.innings
    )
    season_bb_rate = _shrink(season_bb_events, season_bb_opportunities, k_stats["bb_rate"], league["bb_rate"])
    if bb_approx:
        reasons.append("BB rate: season count reconstructed from bb_percent (no raw batters-faced count on this snapshot)")

    recent_bb_events, recent_bb_opportunities, recent_bb_approx = _resolve_count_and_opportunities(
        recent.walks, recent.batters_faced, recent.bb_percent, recent.innings
    )
    bb_weight = _recent_weight(recent_bb_opportunities, cfg.PITCHER_RECENT_STABILIZATION_BF, cfg.MAX_RECENT_BLEND_WEIGHT)
    if recent_bb_opportunities is not None and recent_bb_events is not None:
        recent_bb_rate = recent_bb_events / recent_bb_opportunities
        walk_rate = (1 - bb_weight) * season_bb_rate + bb_weight * recent_bb_rate
        reasons.append(
            f"BB rate: season-regressed {season_bb_rate:.3f} blended with recent {recent_bb_rate:.3f} "
            f"at {bb_weight:.0%} recent weight ({recent_bb_opportunities:.0f} recent BF"
            f"{', approximated' if recent_bb_approx else ''})"
        )
    else:
        walk_rate = season_bb_rate
        reasons.append(f"BB rate: season-only, regressed to {season_bb_rate:.3f} (no usable recent data)")

    # ---- Hit / HR / HBP against: season-only count-based regression ----
    hit_rate = _shrink(season.hits_allowed, season.batters_faced, k_stats["hit_rate"], league["hit_rate"])
    home_run_rate = _shrink(season.home_runs_allowed, season.batters_faced, k_stats["home_run_rate"], league["home_run_rate"])
    hit_by_pitch_rate = _shrink(season.hit_by_pitch, season.batters_faced, k_stats["hbp_rate"], league["hbp_rate"])
    reasons.append(
        f"Hit/HR/HBP-against rates: season-only count-based regression -- "
        f"{hit_rate:.3f}/{home_run_rate:.3f}/{hit_by_pitch_rate:.3f} per batter faced"
    )

    # ---- Earned-run rate: per inning pitched ----
    er_league_avg = cfg.LEAGUE_AVG_EARNED_RUNS_PER_INNING
    if season.earned_runs is not None and season.innings is not None:
        earned_run_rate = _shrink(
            season.earned_runs, season.innings, cfg.PITCHER_STABILIZATION_INNINGS["earned_run_rate"], er_league_avg
        )
        reasons.append(f"Earned-run rate: season count-based regression -> {earned_run_rate:.3f} per inning")
    elif season.era is not None and season.innings is not None:
        observed_er_from_era = (season.era / 9.0) * season.innings
        earned_run_rate = _shrink(
            observed_er_from_era, season.innings, cfg.PITCHER_STABILIZATION_INNINGS["earned_run_rate"], er_league_avg
        )
        reasons.append(f"Earned-run rate: reconstructed from season ERA (no raw earned-run count) -> {earned_run_rate:.3f} per inning")
    else:
        earned_run_rate = er_league_avg
        reasons.append(f"Earned-run rate: no ERA or earned-run data available -- using league-average {er_league_avg:.3f} per inning")

    return PitcherRates(
        strikeout_rate=round(strikeout_rate, 4),
        walk_rate=round(walk_rate, 4),
        hit_rate=round(hit_rate, 4),
        home_run_rate=round(home_run_rate, 4),
        hit_by_pitch_rate=round(hit_by_pitch_rate, 4),
        earned_run_rate_per_inning=round(earned_run_rate, 4),
        reasons=reasons,
        coverage_fields_available=fields_available,
        coverage_fields_total=fields_total,
        coverage_missing_fields=missing_fields,
        season_opportunities=season_k_opportunities,
        recent_opportunities=recent_k_opportunities,
    )
