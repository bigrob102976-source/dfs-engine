"""Single source of truth for the AI Projection Engine (Milestone 20):
every weight, threshold, and point delta the engine uses to combine
already-computed research signals (Pitcher/Batter Agent projection,
Game Environment weather/Vegas/bullpen/park, Ownership leverage,
External/Adjusted projection) into one AI Projection per player.

The AI Projection Engine is NOT an LLM free-form projection generator
and does not recompute anything the Pitcher Agent, Batter Agent, Game
Environment Agent, or Ownership model already produced -- it only reads
their already-computed outputs and combines them with the weights
below. See projection_engine/signals.py.
"""

# --- Model version -----------------------------------------------------------

AI_PROJECTION_ENGINE_VERSION = "0.1.0"

# --- Safety cap ----------------------------------------------------------
# No combination of signals may move the AI Projection further from the
# Independent Projection than this percentage, regardless of how many
# favorable/unfavorable signals fire -- same discipline as
# config/adjustment_config.py's MAX_POSITIVE/NEGATIVE_ADJUSTMENT_PERCENT.

MAX_TOTAL_ADJUSTMENT_PERCENT = 20.0

# --- Signal weights --------------------------------------------------------
# Every signal category's raw point delta (computed in signals.py from
# already-computed upstream fields) is multiplied by its weight here
# before being added to the Independent Projection baseline. A weight
# of 0.0 disables a category without deleting its signal logic.

SIGNAL_WEIGHTS = {
    "weather": 1.0,
    "vegas": 1.0,
    "bullpen": 1.0,
    "park": 1.0,
    "ownership": 0.5,
    "matchup": 0.6,
    "recent_form": 0.5,
    "external": 0.4,
}

# Pitchers already have weather/park partially baked into their own
# sub-scores via GameContext.weather_pitching_factor / park_factor
# (agents/pitcher_agent.py's ENVIRONMENT_DAMPENING) -- hitters do not
# (batter_agent.py hardcodes environment_score=50.0, neutral). To avoid
# double-counting the same signal for pitchers, weather and park deltas
# are additionally scaled by this factor when player_type == "pitcher".
PITCHER_ENVIRONMENT_DAMPENING = 0.4

# --- Weather signal ---------------------------------------------------------
# Reuses research/game_environment/weather.py::analyze_weather's own
# deterministic WeatherConclusion.code / .favors -- never re-derives wind
# direction/threshold math. `points` is the raw (pre-weight,
# pre-dampening) delta applied when `favors` matches the player's role;
# the sign flips automatically for the opposite role.

WEATHER_CONCLUSION_POINTS = {
    "wind_strong_out": 0.45,
    "wind_notable_out": 0.20,
    "wind_strong_in": 0.45,
    "wind_notable_in": 0.20,
    "wind_strong_cross": 0.0,
    "hot_weather": 0.12,
    "cold_weather": 0.12,
    "indoor_game": 0.0,
}
# "risk" conclusions (rain/postponement delay) never move the
# projection -- they raise AI Risk instead. See RISK_WEATHER_BUMP below.
WEATHER_RISK_CODES = ("rain_delay_risk", "postponement_risk")

# --- Vegas signal ------------------------------------------------------------
# Reuses research/game_environment/vegas.py::total_tier (same
# TOTAL_HIGH_THRESHOLD/TOTAL_LOW_THRESHOLD as the Game Environment Engine)
# and the snapshot's own home_implied_runs/away_implied_runs/total_movement
# -- never re-derives implied runs or tier boundaries.

VEGAS_HIGH_TOTAL_POINTS = 0.35
VEGAS_LOW_TOTAL_POINTS = 0.25
VEGAS_MOVEMENT_POINTS_PER_RUN = 0.20   # scaled by |total_movement|, capped below
VEGAS_MOVEMENT_MAX_POINTS = 0.30

# --- Bullpen signal ----------------------------------------------------------
# Reuses research/game_environment/bullpen.py's own 0-100 strength_score
# and estimated_fatigue label. For pitchers this is their OWN team's
# bullpen (an elite, rested bullpen raises hook risk -- fewer innings for
# the starter). For hitters this is the OPPOSING team's bullpen (a weak,
# fatigued opposing bullpen raises late-inning scoring upside).

BULLPEN_STRENGTH_ELITE = 70.0
BULLPEN_STRENGTH_WEAK = 35.0
BULLPEN_PITCHER_ELITE_OWN_BULLPEN_POINTS = -0.20   # hook risk
BULLPEN_PITCHER_WEAK_OWN_BULLPEN_POINTS = 0.15     # longer leash likely
BULLPEN_HITTER_WEAK_OPPONENT_BULLPEN_POINTS = 0.25
BULLPEN_HITTER_ELITE_OPPONENT_BULLPEN_POINTS = -0.15
BULLPEN_FATIGUE_HIGH_HITTER_BONUS_POINTS = 0.15   # opponent bullpen fatigue="high"

# --- Park signal ---------------------------------------------------------
# Reuses research/game_environment/ballpark.py's static hr_factor (100 =
# league-neutral, already publicly-known park data) -- never re-derives
# park factors.

PARK_HR_FACTOR_NEUTRAL = 100
PARK_HITTER_POINTS_PER_HR_FACTOR_POINT = 0.012
PARK_PITCHER_POINTS_PER_HR_FACTOR_POINT = -0.009

# --- Ownership signal --------------------------------------------------------
# Reuses ownership/leverage.py's own leverage_score (quality percentile
# minus ownership percentile) and the model's projected_ownership --
# never re-derives ownership. GPP-context adjustment per CLAUDE.md's
# "identify leverage against the field" mission: a small nudge, not a
# projection override.

OWNERSHIP_CHALK_FADE_THRESHOLD_PERCENT = 30.0
OWNERSHIP_CHALK_FADE_POINTS = -0.14
OWNERSHIP_LEVERAGE_BONUS_THRESHOLD = 15.0   # leverage_score, roughly -100..100
OWNERSHIP_LEVERAGE_BONUS_POINTS = 0.16

# --- Pitcher Matchup signal --------------------------------------------------
# Reuses the Pitcher/Batter Agent's own matchup_score (0-100, 50 =
# neutral) -- never recomputes opponent quality.

MATCHUP_NEUTRAL_SCORE = 50.0
MATCHUP_POINTS_PER_SCORE_POINT = 0.012

# --- Recent Form / Statcast trend signal --------------------------------
# Batters: reuses recent_trend_score (0-100, 50 = neutral). Pitchers have
# no equivalent dedicated sub-score, so this reuses the Pitcher Agent's
# own "positive_trend"/"negative_trend" tags (agents/pitcher_agent.py) --
# never recomputes trend deltas.

RECENT_FORM_NEUTRAL_SCORE = 50.0
RECENT_FORM_POINTS_PER_SCORE_POINT = 0.010
RECENT_FORM_PITCHER_TAG_POINTS = 0.20   # applied when "positive_trend"/"negative_trend" tag present

# --- External Projection gap signal ------------------------------------
# Reuses external_projections/models.py::PlayerProjectionRecord's own
# independent_projection/external_projection (from the latest adjusted
# snapshot) -- never re-fetches or re-matches external data.

EXTERNAL_GAP_MAX_POINTS = 0.60   # cap on the weighted external-gap contribution

# --- AI Confidence blend -----------------------------------------------------
# Blends the Pitcher/Batter Agent's own `confidence` (research sample
# quality) with the Ownership model's `ownership_confidence` and the
# Adjustment Engine's `adjustment_confidence`, when present. Weights
# renormalize over whichever inputs are actually available -- a missing
# input is never treated as 0.

AI_CONFIDENCE_WEIGHTS = {
    "research": 0.7,
    "ownership": 0.15,
    "adjustment": 0.15,
}

# --- AI Risk blend -------------------------------------------------------
# Starts from the Agent's own risk_score, then adds small bumps for
# conditions the AI layer newly observes (weather risk conclusions, a
# large total adjustment magnitude implying more signals disagreed).

RISK_WEATHER_BUMP_POINTS = 8.0     # per WEATHER_RISK_CODES conclusion present
RISK_LARGE_ADJUSTMENT_THRESHOLD_PERCENT = 10.0
RISK_LARGE_ADJUSTMENT_BUMP_POINTS = 5.0

# --- AI Grade ----------------------------------------------------------
# Built from an AI-adjusted overall-quality score: the Agent's own
# overall_score (0-100) nudged by the total adjustment percent, then
# bucketed. Checked high-to-low; the first matching band wins.

AI_GRADE_OVERALL_SCORE_ADJUSTMENT_SCALE = 0.5   # overall_score += total_adjustment_percent * this
AI_GRADE_BANDS = [
    {"min_score": 90.0, "grade": "A+"},
    {"min_score": 80.0, "grade": "A"},
    {"min_score": 70.0, "grade": "B+"},
    {"min_score": 60.0, "grade": "B"},
    {"min_score": 50.0, "grade": "C+"},
    {"min_score": 40.0, "grade": "C"},
    {"min_score": 25.0, "grade": "D"},
    {"min_score": 0.0, "grade": "F"},
]

# --- Reasons ---------------------------------------------------------------
# Same "rank by salience, cap at N" pattern as agents/pitcher_agent.py
# and agents/batter_agent.py's _reasons() functions.

MAX_REASONS_PER_PLAYER = 6
MAX_SIGNALS_IN_AI_SUMMARY = 5
