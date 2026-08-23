"""Single source of truth for the Game Environment Engine (Milestone
DS2): static ballpark/team-location reference data, and every threshold
or weight the weather/vegas analysis and scoring modules use.

Nothing in research/game_environment/ fetches this data over the
network on every refresh -- ballpark and team-location facts are
static, versioned constants here (see ballpark.py's module docstring
for why). Weather/Vegas/Umpire/Bullpen live data instead comes from a
ProviderProvider abstraction (see weather.py/vegas.py/umpires.py/
bullpen.py) with only a clearly-labeled MOCK implementation registered
today -- no real weather/odds API is configured or credentialed in
this environment (same discipline as external_projections/
bluecollar_provider.py: never guess an endpoint, never invent network
behavior).
"""

# --- Model version -----------------------------------------------------------

GAME_ENVIRONMENT_ENGINE_VERSION = "0.1.0"

# --- Static ballpark reference data ------------------------------------------
# Approximate, publicly-known park factors (100 = league average; >100
# favors hitters, <100 favors pitchers) and physical characteristics.
# Keyed by the HOME team's research-package abbreviation (see
# dfs/team_abbreviations.py for the DK<->research abbreviation crosswalk).
# `orientation_degrees` is the compass bearing from home plate through
# center field -- used by weather.py to classify wind as blowing out to
# a specific field vs. blowing in. Sourced from widely-published
# multi-year park-factor reference tables, not live-fetched; treat as
# approximate, not authoritative for a specific season.

BALLPARKS = {
    "ARI": {"venue_name": "Chase Field", "hr_factor": 103, "run_factor": 101, "park_factor": 101, "altitude_ft": 1086, "roof": "retractable", "surface": "turf", "orientation_degrees": 116},
    "AZ": {"venue_name": "Chase Field", "hr_factor": 103, "run_factor": 101, "park_factor": 101, "altitude_ft": 1086, "roof": "retractable", "surface": "turf", "orientation_degrees": 116},
    "ATL": {"venue_name": "Truist Park", "hr_factor": 104, "run_factor": 102, "park_factor": 102, "altitude_ft": 1050, "roof": "open", "surface": "grass", "orientation_degrees": 78},
    "BAL": {"venue_name": "Oriole Park at Camden Yards", "hr_factor": 97, "run_factor": 98, "park_factor": 98, "altitude_ft": 20, "roof": "open", "surface": "grass", "orientation_degrees": 30},
    "BOS": {"venue_name": "Fenway Park", "hr_factor": 96, "run_factor": 104, "park_factor": 103, "altitude_ft": 21, "roof": "open", "surface": "grass", "orientation_degrees": 55},
    "CHC": {"venue_name": "Wrigley Field", "hr_factor": 101, "run_factor": 100, "park_factor": 100, "altitude_ft": 600, "roof": "open", "surface": "grass", "orientation_degrees": 34},
    "CWS": {"venue_name": "Rate Field", "hr_factor": 104, "run_factor": 101, "park_factor": 101, "altitude_ft": 595, "roof": "open", "surface": "grass", "orientation_degrees": 135},
    "CIN": {"venue_name": "Great American Ball Park", "hr_factor": 112, "run_factor": 105, "park_factor": 106, "altitude_ft": 490, "roof": "open", "surface": "grass", "orientation_degrees": 100},
    "CLE": {"venue_name": "Progressive Field", "hr_factor": 97, "run_factor": 97, "park_factor": 97, "altitude_ft": 660, "roof": "open", "surface": "grass", "orientation_degrees": 0},
    "COL": {"venue_name": "Coors Field", "hr_factor": 118, "run_factor": 115, "park_factor": 116, "altitude_ft": 5280, "roof": "open", "surface": "grass", "orientation_degrees": 0},
    "DET": {"venue_name": "Comerica Park", "hr_factor": 92, "run_factor": 96, "park_factor": 95, "altitude_ft": 585, "roof": "open", "surface": "grass", "orientation_degrees": 145},
    "HOU": {"venue_name": "Daikin Park", "hr_factor": 100, "run_factor": 98, "park_factor": 98, "altitude_ft": 50, "roof": "retractable", "surface": "turf", "orientation_degrees": 71},
    "KC": {"venue_name": "Kauffman Stadium", "hr_factor": 91, "run_factor": 97, "park_factor": 96, "altitude_ft": 750, "roof": "open", "surface": "grass", "orientation_degrees": 45},
    "LAA": {"venue_name": "Angel Stadium", "hr_factor": 98, "run_factor": 98, "park_factor": 98, "altitude_ft": 150, "roof": "open", "surface": "grass", "orientation_degrees": 20},
    "LAD": {"venue_name": "Dodger Stadium", "hr_factor": 95, "run_factor": 95, "park_factor": 95, "altitude_ft": 340, "roof": "open", "surface": "grass", "orientation_degrees": 25},
    "MIA": {"venue_name": "loanDepot Park", "hr_factor": 89, "run_factor": 92, "park_factor": 91, "altitude_ft": 8, "roof": "retractable", "surface": "grass", "orientation_degrees": 38},
    "MIL": {"venue_name": "American Family Field", "hr_factor": 103, "run_factor": 100, "park_factor": 101, "altitude_ft": 635, "roof": "retractable", "surface": "grass", "orientation_degrees": 130},
    "MIN": {"venue_name": "Target Field", "hr_factor": 98, "run_factor": 97, "park_factor": 97, "altitude_ft": 815, "roof": "open", "surface": "grass", "orientation_degrees": 96},
    "NYM": {"venue_name": "Citi Field", "hr_factor": 94, "run_factor": 96, "park_factor": 95, "altitude_ft": 20, "roof": "open", "surface": "grass", "orientation_degrees": 30},
    "NYY": {"venue_name": "Yankee Stadium", "hr_factor": 111, "run_factor": 103, "park_factor": 104, "altitude_ft": 55, "roof": "open", "surface": "grass", "orientation_degrees": 75},
    "ATH": {"venue_name": "Sutter Health Park", "hr_factor": 97, "run_factor": 96, "park_factor": 96, "altitude_ft": 25, "roof": "open", "surface": "grass", "orientation_degrees": 45},
    "OAK": {"venue_name": "Sutter Health Park", "hr_factor": 97, "run_factor": 96, "park_factor": 96, "altitude_ft": 25, "roof": "open", "surface": "grass", "orientation_degrees": 45},
    "PHI": {"venue_name": "Citizens Bank Park", "hr_factor": 110, "run_factor": 104, "park_factor": 105, "altitude_ft": 20, "roof": "open", "surface": "grass", "orientation_degrees": 20},
    "PIT": {"venue_name": "PNC Park", "hr_factor": 89, "run_factor": 93, "park_factor": 92, "altitude_ft": 730, "roof": "open", "surface": "grass", "orientation_degrees": 90},
    "SD": {"venue_name": "Petco Park", "hr_factor": 92, "run_factor": 94, "park_factor": 93, "altitude_ft": 62, "roof": "open", "surface": "grass", "orientation_degrees": 40},
    "SF": {"venue_name": "Oracle Park", "hr_factor": 85, "run_factor": 93, "park_factor": 91, "altitude_ft": 12, "roof": "open", "surface": "grass", "orientation_degrees": 95},
    "SEA": {"venue_name": "T-Mobile Park", "hr_factor": 92, "run_factor": 94, "park_factor": 93, "altitude_ft": 10, "roof": "retractable", "surface": "grass", "orientation_degrees": 45},
    "STL": {"venue_name": "Busch Stadium", "hr_factor": 94, "run_factor": 96, "park_factor": 95, "altitude_ft": 465, "roof": "open", "surface": "grass", "orientation_degrees": 90},
    "TB": {"venue_name": "George M. Steinbrenner Field", "hr_factor": 98, "run_factor": 98, "park_factor": 98, "altitude_ft": 10, "roof": "open", "surface": "grass", "orientation_degrees": 45},
    "TEX": {"venue_name": "Globe Life Field", "hr_factor": 101, "run_factor": 99, "park_factor": 100, "altitude_ft": 550, "roof": "retractable", "surface": "turf", "orientation_degrees": 90},
    "TOR": {"venue_name": "Rogers Centre", "hr_factor": 103, "run_factor": 101, "park_factor": 101, "altitude_ft": 250, "roof": "retractable", "surface": "turf", "orientation_degrees": 75},
    "WSH": {"venue_name": "Nationals Park", "hr_factor": 100, "run_factor": 99, "park_factor": 99, "altitude_ft": 12, "roof": "open", "surface": "grass", "orientation_degrees": 30},
}

# --- Static team location/timezone reference data (for travel.py) -----------
# Approximate home-city coordinates and IANA timezone per team -- enough
# to compute straight-line distance and timezones-crossed deterministically.
# Not a substitute for a real schedule feed: back-to-back/getaway-day
# detection needs game-by-game schedule history this project doesn't
# collect yet, so those two fields always report UNKNOWN (see travel.py).

TEAM_LOCATIONS = {
    "ARI": {"lat": 33.4453, "lon": -112.0667, "timezone": "America/Phoenix"},
    "AZ": {"lat": 33.4453, "lon": -112.0667, "timezone": "America/Phoenix"},
    "ATL": {"lat": 33.8908, "lon": -84.4678, "timezone": "America/New_York"},
    "BAL": {"lat": 39.2839, "lon": -76.6217, "timezone": "America/New_York"},
    "BOS": {"lat": 42.3467, "lon": -71.0972, "timezone": "America/New_York"},
    "CHC": {"lat": 41.9484, "lon": -87.6553, "timezone": "America/Chicago"},
    "CWS": {"lat": 41.8300, "lon": -87.6338, "timezone": "America/Chicago"},
    "CIN": {"lat": 39.0979, "lon": -84.5063, "timezone": "America/New_York"},
    "CLE": {"lat": 41.4962, "lon": -81.6852, "timezone": "America/New_York"},
    "COL": {"lat": 39.7559, "lon": -104.9942, "timezone": "America/Denver"},
    "DET": {"lat": 42.3390, "lon": -83.0485, "timezone": "America/New_York"},
    "HOU": {"lat": 29.7573, "lon": -95.3555, "timezone": "America/Chicago"},
    "KC": {"lat": 39.0517, "lon": -94.4803, "timezone": "America/Chicago"},
    "LAA": {"lat": 33.8003, "lon": -117.8827, "timezone": "America/Los_Angeles"},
    "LAD": {"lat": 34.0739, "lon": -118.2400, "timezone": "America/Los_Angeles"},
    "MIA": {"lat": 25.7781, "lon": -80.2196, "timezone": "America/New_York"},
    "MIL": {"lat": 43.0280, "lon": -87.9712, "timezone": "America/Chicago"},
    "MIN": {"lat": 44.9817, "lon": -93.2777, "timezone": "America/Chicago"},
    "NYM": {"lat": 40.7571, "lon": -73.8458, "timezone": "America/New_York"},
    "NYY": {"lat": 40.8296, "lon": -73.9262, "timezone": "America/New_York"},
    "ATH": {"lat": 38.5802, "lon": -121.5162, "timezone": "America/Los_Angeles"},
    "OAK": {"lat": 38.5802, "lon": -121.5162, "timezone": "America/Los_Angeles"},
    "PHI": {"lat": 39.9061, "lon": -75.1665, "timezone": "America/New_York"},
    "PIT": {"lat": 40.4469, "lon": -80.0057, "timezone": "America/New_York"},
    "SD": {"lat": 32.7073, "lon": -117.1566, "timezone": "America/Los_Angeles"},
    "SF": {"lat": 37.7786, "lon": -122.3893, "timezone": "America/Los_Angeles"},
    "SEA": {"lat": 47.5914, "lon": -122.3325, "timezone": "America/Los_Angeles"},
    "STL": {"lat": 38.6226, "lon": -90.1928, "timezone": "America/Chicago"},
    "TB": {"lat": 27.9759, "lon": -82.5333, "timezone": "America/New_York"},
    "TEX": {"lat": 32.7473, "lon": -97.0842, "timezone": "America/Chicago"},
    "TOR": {"lat": 43.6414, "lon": -79.3894, "timezone": "America/Toronto"},
    "WSH": {"lat": 38.8730, "lon": -77.0074, "timezone": "America/New_York"},
}

# --- Weather analysis thresholds ---------------------------------------------

WIND_STRONG_MPH = 12.0
WIND_NOTABLE_MPH = 7.0
# Wind direction is stored as "the direction the wind is blowing TOWARD",
# in degrees, compass bearing (0=N, 90=E, 180=S, 270=W) -- same convention
# as BALLPARKS' orientation_degrees. A wind direction within this many
# degrees of the park's CF orientation is "blowing out"; within the same
# tolerance of the opposite bearing is "blowing in".
WIND_DIRECTION_TOLERANCE_DEGREES = 45.0

TEMP_HOT_F = 85.0
TEMP_COLD_F = 50.0

RAIN_DELAY_RISK_HIGH_PERCENT = 50.0
POSTPONEMENT_RISK_HIGH_PERCENT = 25.0

# --- WEATHER RISK (Milestone 32.6 Part 5/6) -----------------------------------
# WEATHER RISK is a single 0-100 percentage answering "how likely is
# weather to disrupt this game" (delay/postponement) -- deliberately
# NOT the same question as "is this a good hitting/pitching
# environment" (that stays a separate, un-related signal: hot weather
# favors hitters and is NOT weather risk; see weather.py's
# analyze_weather()). Computed from four independent 0-100 sub-scores,
# blended by the weights below (renormalized if a sub-score is
# unavailable, same discipline as HITTER_SCORE_WEIGHTS elsewhere in this
# file) using the first-pitch-through-late-game window's WORST hourly
# reading for precipitation probability/amount/weather-code severity
# (a single bad hour is enough to threaten a delay -- averaging across
# the window would dilute a real signal), and the single highest gust
# reading in that same window for wind.
WEATHER_RISK_WEIGHTS = {
    "precipitation_probability": 0.40,
    "precipitation_amount": 0.25,
    "weather_code_severity": 0.25,
    "wind_gusts": 0.10,
}
# precipitation_amount_mm/hour -> 0-100 sub-score: linear from 0mm=0 to
# this ceiling=100 (clamped above it) -- a genuine downpour, not a
# passing drizzle, is what actually threatens a delay.
WEATHER_RISK_PRECIP_AMOUNT_CEILING_MM = 6.0
# wind_gusts_mph -> 0-100 sub-score: linear from this floor=0 up to the
# ceiling=100 (clamped both ends) -- ordinary gusty conditions (well
# below the ceiling) contribute little; a genuinely dangerous gust does.
WEATHER_RISK_WIND_GUST_FLOOR_MPH = 20.0
WEATHER_RISK_WIND_GUST_CEILING_MPH = 45.0
# WMO weather-code (Open-Meteo's documented vocabulary) -> 0-100
# disruption-severity sub-score. Codes not listed default to 0 (clear/
# cloudy/fog carry no delay risk of their own -- fog is a visibility,
# not a play-stoppage, concern for MLB).
WEATHER_CODE_SEVERITY = {
    51: 15, 53: 25, 55: 35,  # drizzle: light/moderate/dense
    56: 20, 57: 35,  # freezing drizzle: light/dense
    61: 30, 63: 55, 65: 80,  # rain: slight/moderate/heavy
    66: 40, 67: 70,  # freezing rain: light/heavy
    71: 25, 73: 40, 75: 60, 77: 30,  # snow: slight/moderate/heavy/grains
    80: 40, 81: 65, 82: 90,  # rain showers: slight/moderate/violent
    85: 35, 86: 55,  # snow showers: slight/heavy
    95: 85, 96: 95, 99: 100,  # thunderstorm: plain/slight hail/heavy hail
}
# Centralized GREEN/YELLOW/RED thresholds for the Weather Risk badge
# (Part 7's "never bury a threshold inside a component" rule) --
# LOW_GOOD direction (0=no concern, 100=severe concern). Initial bands
# per the milestone spec; change here only, never in a component.
WEATHER_RISK_GREEN_MAX = 29.99
WEATHER_RISK_YELLOW_MAX = 59.99

# --- Vegas analysis thresholds ------------------------------------------------

TOTAL_HIGH_THRESHOLD = 9.5
TOTAL_LOW_THRESHOLD = 7.5
LINE_MOVEMENT_SHARP_RUNS = 1.0  # total-line movement (open -> current) at/above this is "sharp"
MONEYLINE_BIG_FAVORITE = -170
MONEYLINE_BIG_UNDERDOG = 150

# --- Vegas sanity-check bounds (Milestone 24) ----------------------------------
# A REAL MLB game total outside this range almost certainly indicates a
# parsing/consensus bug, not a genuine market price -- real 9-inning MLB
# totals have not been observed outside roughly 6.5-12.5 even at Coors
# Field in extreme weather; this range is deliberately wider than that
# observed band so a real, unusual-but-genuine total is never falsely
# rejected, while still catching a clearly broken value (e.g. a
# mis-parsed spread or moneyline landing in the total field).
VEGAS_TOTAL_MIN_PLAUSIBLE = 4.0
VEGAS_TOTAL_MAX_PLAUSIBLE = 16.0

# --- Bullpen scoring ----------------------------------------------------------

BULLPEN_ERA_STRONG = 3.50
BULLPEN_ERA_WEAK = 4.50
FATIGUE_HIGH_RELIEVERS_USED = 3  # relievers used in the last 3 days at/above this = high fatigue

# --- Overall/Pitcher/Hitter/Stack Environment Score weights -----------------
# Each sub-score blends whichever of these signals are actually available
# (missing inputs are dropped and the rest renormalized -- same discipline
# as config/scoring_config.py's COMPONENT_WEIGHTS). All scores are 0-100,
# where higher always means "more favorable for the HITTER" (Pitcher
# Environment Score is intentionally the complement -- see scoring.py).

HITTER_SCORE_WEIGHTS = {
    "park_factor": 0.30,
    "weather": 0.25,
    "vegas_total": 0.30,
    "bullpen_weakness": 0.15,
}

STACK_SCORE_WEIGHTS = {
    "park_factor": 0.25,
    "weather": 0.20,
    "vegas_total": 0.35,
    "bullpen_weakness": 0.20,
}

# --- Settings: which sections are enabled by default -------------------------
# Purely a display preference (see dashboard Settings page) -- disabling a
# section here/in Settings never stops the engine from collecting or
# scoring that signal, it only hides it from the UI.

DEFAULT_ENABLED_SECTIONS = {
    "weather": True,
    "vegas": True,
    "bullpen": True,
    "park": True,
    "travel": True,
}
