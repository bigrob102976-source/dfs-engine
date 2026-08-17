"""Single source of truth for the Native Projection Model's (native_projections/)
stabilization points, recency weighting, uncertainty parameters, environment
weights, and validation thresholds.

No magic numbers live in native_projections/*.py -- every tunable constant
is named and documented here, mirroring config/scoring_config.py's and
config/batter_scoring_config.py's existing "single source of truth" pattern
for this project.

IMPORTANT (Milestone 23 "DO NOT AUTO-TUNE"): none of these numbers may be
changed based on evaluation results from a single slate. Weight/threshold
tuning is an explicit future milestone, gated on enough real slates existing.
"""

from config.batter_scoring_config import PROJECTION_MODEL as _BATTER_PROJECTION_MODEL
from config.scoring_config import PROJECTION_MODEL as _PITCHER_PROJECTION_MODEL

# --- Model version -----------------------------------------------------------
# See native_projections/version.py for NATIVE_PROJECTION_MODEL_VERSION --
# kept in its own tiny module (not here) so evaluation/native_component_evaluation.py
# and other lightweight consumers don't have to import this whole config file
# just to know which model version produced a snapshot.


# --- Hitter opportunity model (expected PA) ----------------------------------
# Reuses the EXISTING, already-real expected-PA-by-batting-order table from
# config/batter_scoring_config.py rather than re-deriving a second copy of
# the same 9 numbers -- see that file's own comment for why the shape
# (decreasing down the order) is correct.
EXPECTED_PA_BY_ORDER = _BATTER_PROJECTION_MODEL["expected_pa_by_order"]
DEFAULT_EXPECTED_PA = _BATTER_PROJECTION_MODEL["default_expected_pa"]

# Confidence (0-100) contribution from lineup-confirmation status alone,
# before any sample-size/completeness adjustment. A hitter with no
# confirmed batting order gets PA_CONFIDENCE_UNCONFIRMED -- in practice
# such a hitter is excluded upstream already (BatterInput is only ever
# built for posted-lineup hitters -- research/adapters/batter_input.py),
# but this constant exists so native_projections never has to guess if
# that product rule ever changes.
PA_CONFIDENCE_CONFIRMED = 90.0
PA_CONFIDENCE_UNCONFIRMED = 0.0

# --- Pitcher opportunity model (expected innings / BF / pitch count) --------
# pitches_per_inning / batters_per_inning mirror the same convention already
# established in config/scoring_config.py::PROJECTION_MODEL (kept as a
# separate copy here, not imported, because scoring_config.py is the Pitcher
# Agent's own config namespace and this module intentionally never imports
# from it -- native_projections is a fully separate, parallel package).
PITCHES_PER_INNING = 15.5
BATTERS_PER_INNING = 4.3
DEFAULT_EXPECTED_PITCH_COUNT = 90.0
MIN_EXPECTED_INNINGS = 2.5
MAX_EXPECTED_INNINGS = 7.5

# Workload confidence (0-100) depending on which source produced the
# expected-pitch-count estimate -- highest when a real per-pitcher value is
# available, lowest when nothing but the league-wide default was usable.
WORKLOAD_CONFIDENCE_WITH_REAL_PITCH_COUNT = 90.0
WORKLOAD_CONFIDENCE_WITH_RECENT_AVERAGE_ONLY = 65.0
WORKLOAD_CONFIDENCE_WITH_DEFAULT_ONLY = 30.0
# A pitcher not yet confirmed as the starter gets a flat penalty on top of
# whichever of the above applies.
UNCONFIRMED_STARTER_WORKLOAD_PENALTY = 25.0

# --- Sample-size stabilization (regression toward league mean) --------------
# "Stabilization point" = the sample size (PA for hitters, batters-faced for
# pitchers) at which a rate stat is roughly 50% signal / 50% noise -- a
# standard, published sabermetric concept (see e.g. Russell A. Carleton's
# stabilization-point research, and Tom Tango's public-domain "Marcel the
# Monkey" forecasting system, whose spirit this model deliberately follows:
# a simple, reproducible, fully-documented shrinkage-to-the-mean approach,
# not a fitted/opaque model).
#
#   regressed_rate = (observed_events + K * league_avg_rate) / (observed_n + K)
#
# A player with observed_n == K gets a rate exactly halfway between their
# own observed rate and the league average; observed_n << K pulls almost
# all the way to league average (fixes the confirmed small-sample bug where
# a 10-PA rookie's raw rate got full statistical weight); observed_n >> K
# barely moves from the player's own real rate.
HITTER_STABILIZATION_PA = {
    "k_rate": 60.0,
    "bb_rate": 120.0,
    "single_rate": 290.0,
    "double_rate": 500.0,
    "triple_rate": 550.0,  # rare event -- wide K so a single triple doesn't swing the rate
    "home_run_rate": 170.0,
    "hbp_rate": 240.0,
    "stolen_base_rate": 400.0,
}
PITCHER_STABILIZATION_BF = {
    "k_rate": 70.0,
    "bb_rate": 170.0,
    "hit_rate": 630.0,
    "home_run_rate": 1320.0,
    "hbp_rate": 640.0,
}
# Earned runs don't fit the per-batters-faced categorical shape the other
# pitcher rates use (a run "scores" through base-state/sequencing, not a
# single at-bat outcome) -- they're instead regressed per INNING PITCHED,
# using the pitcher's own real season earned-run count (models.pitcher
# .SeasonStats.earned_runs, exposed in Milestone 23 -- see
# research/enrichment.py) against real innings pitched.
PITCHER_STABILIZATION_INNINGS = {
    "earned_run_rate": 60.0,  # ~9-10 starts' worth of innings
}

# --- Recency weighting -------------------------------------------------------
# The recent-form blend weight is ITSELF sample-size-driven (not a fixed
# 0.7/0.3 split like the existing agents/*.py use) -- a 1-start recent
# sample contributes almost nothing; a full window contributes up to
# MAX_RECENT_BLEND_WEIGHT. recent_weight = recent_n / (recent_n + K_recent).
HITTER_RECENT_STABILIZATION_PA = 40.0  # ~14-day window's typical full sample
PITCHER_RECENT_STABILIZATION_BF = 45.0  # ~3-start window's typical full sample
MAX_RECENT_BLEND_WEIGHT = 0.55

# --- League-average priors ----------------------------------------------------
# Used both as the shrinkage target above AND as the sole fallback when a
# player has literally zero season data (never invented per-player).
LEAGUE_AVG_HITTER_RATES = {
    "k_rate": 0.220,
    "bb_rate": 0.085,
    "single_rate": 0.145,
    "double_rate": 0.045,
    "triple_rate": 0.004,
    "home_run_rate": 0.032,
    "hbp_rate": 0.010,
    "stolen_base_rate": 0.012,
}
LEAGUE_AVG_PITCHER_RATES = {
    "k_rate": 0.220,
    "bb_rate": 0.085,
    "hit_rate": 0.235,
    "home_run_rate": 0.032,
    "hbp_rate": 0.010,
}
# Reuses config.scoring_config.PROJECTION_MODEL["default_run_rate"] (4.20
# runs/9 innings -- the existing Pitcher Agent's own documented league-average
# fallback) rather than defining a second, competing "league average ERA"
# constant. Divided by 9 to get a per-inning rate.
LEAGUE_AVG_EARNED_RUNS_PER_INNING = _PITCHER_PROJECTION_MODEL["default_run_rate"] / 9.0

# --- Matchup adjustment -------------------------------------------------------
# Caps on how many DK points the matchup layer (hitter-vs-pitcher /
# pitcher-vs-lineup) may move the projection, in either direction.
MATCHUP_HITTER_MAX_POINTS = 1.2
MATCHUP_PITCHER_MAX_POINTS = 1.0
# How much extra weight a hitter's own platoon split (vs_rhp/vs_lhp) gets
# relative to their overall season rate, when computing the matchup nudge.
PLATOON_WEIGHT = 0.35
# Need at least this many confirmed-lineup hitters on the opposing team
# before trusting an aggregated "opposing lineup quality" signal for a
# pitcher -- avoids a 2-hitter partial lineup producing a noisy aggregate.
OPPOSING_LINEUP_MIN_HITTERS_FOR_AGGREGATE = 4

# --- Environment (double-counting control) ------------------------------------
# See native_projections/matchup.py's module docstring for the full
# rationale. Park factor is REAL, static data (config/game_environment_config.py
# ::BALLPARKS) and always gets direct weight. Vegas/Weather/Bullpen
# (research/game_environment/*) are backed ONLY by mock providers today
# (confirmed via audit: MockVegasProvider/MockWeatherProvider/
# MockBullpenProvider, is_mock=True) -- their contribution is capped small
# and always flagged synthetic in the output's reasons/input_coverage
# whenever the source snapshot says is_mock=True, rather than being applied
# as if it were three more independent real signals stacked on top of park
# (which would also double-count against whatever a real Vegas total would
# eventually already price in).
PARK_HITTER_POINTS_PER_FACTOR_POINT = 0.010  # points per (park_factor - 100)
PARK_PITCHER_POINTS_PER_FACTOR_POINT = -0.008
MOCK_VEGAS_MAX_POINTS = 0.15
MOCK_WEATHER_MAX_POINTS = 0.10
MOCK_BULLPEN_MAX_POINTS = 0.10
# If a real (non-mock) Vegas provider is ever configured, it becomes the
# PRIMARY run-environment signal and park's own weight above should be
# revisited -- not automatically done here (no auto-tuning), just documented.
REAL_VEGAS_MAX_POINTS = 0.50

# --- Runs / RBI approximation --------------------------------------------------
# Milestone 23 explicitly fills a gap the existing Independent Projection
# leaves unmodeled. This is a DOCUMENTED, simple linear-weights-style
# approximation from the hitter's own on-base/power profile and lineup
# slot -- NOT a full lineup base-state simulation (that's out of scope for
# V1; see native_projections/hitter_rates.py's docstring for the explicit
# limitation this creates).
RUNS_PER_PA_OBP_COEFFICIENT = 0.28
RBI_PER_PA_ISO_COEFFICIENT = 0.22
RUNS_RBI_LINEUP_SLOT_MULTIPLIER = {
    1: 1.05, 2: 1.05, 3: 1.10, 4: 1.15, 5: 1.05, 6: 0.95, 7: 0.90, 8: 0.85, 9: 0.80,
}
DEFAULT_RUNS_RBI_LINEUP_SLOT_MULTIPLIER = 0.90  # used only if batting_order is somehow missing

# --- Uncertainty model (ceiling / floor / variance) ---------------------------
# See native_projections/uncertainty.py for the exact math and its
# documented V1 limitations (approximate normality, independence across
# plate-appearances/batters-faced).
CEILING_Z = 1.6  # DK scoring is right-skewed (HR upside) -- ceiling pulled a bit further than floor
FLOOR_Z = 1.3
MIN_FLOOR_POINTS = 0.0

# The "deterministic" components (hitter Runs/RBI, pitcher innings-pitched
# + earned-runs -- see dk_scoring.py's module docstring) are linear
# functions of the same regressed rates rather than a fresh per-trial
# categorical draw, so they don't get their OWN exact variance formula.
# Their contribution to total variance is instead a bounded function of
# the SAME opportunity-confidence signal already computed upstream
# (HitterOpportunity.pa_confidence / PitcherOpportunity.workload_confidence):
#   deterministic_sd = |deterministic_points| * (1 - opportunity_confidence/100) * this coefficient
# At full opportunity confidence (confirmed lineup slot / confirmed starter
# with a real pitch-count target), the deterministic component is treated
# as having ~0 extra uncertainty; at zero confidence, its SD equals this
# fraction of its own point magnitude. Deliberately NOT derived by scaling
# the primary-events SD by a ratio of means -- that formula is unstable
# whenever the primary (categorical-trial) mean is small (e.g. a low
# strikeout-rate pitcher, where K/BB/HBP/hit points nearly cancel), which
# would blow up the resulting SD disproportionately.
DETERMINISTIC_COMPONENT_UNCERTAINTY_COEFFICIENT = 0.5

# --- Confidence model ----------------------------------------------------------
# Confidence blends THREE things, each 0-1 before weighting: season-sample
# stabilization ratio, recent-sample stabilization ratio, and a data-
# completeness fraction (how many optional inputs were actually available
# vs. defaulted). This is a continuous function of the SAME stabilization
# ratios used for regression above -- not a separate threshold-penalty
# ladder like the existing agents/*.py use.
CONFIDENCE_SEASON_WEIGHT = 0.5
CONFIDENCE_RECENT_WEIGHT = 0.2
CONFIDENCE_COMPLETENESS_WEIGHT = 0.3
MIN_CONFIDENCE = 5.0
MAX_CONFIDENCE = 99.0

# --- Validation thresholds (suspicious-output flags) ---------------------------
# Per the milestone's explicit instruction, values crossing these are
# surfaced as WARNINGS in the snapshot, never silently clamped.
SUSPICIOUS_HITTER_PROJECTION_POINTS = 25.0
SUSPICIOUS_PITCHER_PROJECTION_POINTS = 45.0
TINY_SAMPLE_HITTER_PA_THRESHOLD = 20.0
TINY_SAMPLE_PITCHER_BF_THRESHOLD = 20.0
# A "tiny sample" player whose projection still lands at/above this
# percentile-equivalent point level relative to the suspicious thresholds
# above gets an explicit tiny-sample-elite warning.
TINY_SAMPLE_ELITE_PROJECTION_FRACTION = 0.60
# A player whose tracked optional inputs (native_projections.models.InputCoverage
# .fraction) are mostly missing gets a low-coverage warning -- surfaced,
# never silently suppressed.
LOW_INPUT_COVERAGE_WARNING_THRESHOLD = 0.30
