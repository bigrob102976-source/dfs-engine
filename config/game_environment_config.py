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

# --- Vegas analysis thresholds ------------------------------------------------

TOTAL_HIGH_THRESHOLD = 9.5
TOTAL_LOW_THRESHOLD = 7.5
LINE_MOVEMENT_SHARP_RUNS = 1.0  # total-line movement (open -> current) at/above this is "sharp"
MONEYLINE_BIG_FAVORITE = -170
MONEYLINE_BIG_UNDERDOG = 150

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
