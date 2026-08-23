"""WEATHER RISK (Milestone 32.6 Part 5/6): a single 0-100 percentage
answering "how likely is weather to disrupt this game" (delay or
postponement) -- deliberately distinct from "is this a good hitting/
pitching environment" (temperature/wind stay separate baseball-
environment signals, scored elsewhere; see weather.py's
analyze_weather()). A hot, sunny, windy day scores LOW weather risk
here even though it may score high or low as an offensive environment.

Methodology: for every hourly forecast point in the game window
(scheduled start through approximately +4 hours -- a single bad hour is
enough to threaten a delay, so this uses the WORST hour observed, never
an average that would dilute a real signal), compute four independent
0-100 sub-scores and blend them with WEATHER_RISK_WEIGHTS
(config/game_environment_config.py, renormalized if a sub-score is
unavailable for every hour):

  - precipitation_probability: the forecast probability itself (already
    0-100).
  - precipitation_amount: linear 0mm=0 -> WEATHER_RISK_PRECIP_AMOUNT_CEILING_MM=100.
  - weather_code_severity: WEATHER_CODE_SEVERITY[code], 0 for any code
    not in that table (clear/cloudy/fog carry no delay risk).
  - wind_gusts: linear WEATHER_RISK_WIND_GUST_FLOOR_MPH=0 ->
    WEATHER_RISK_WIND_GUST_CEILING_MPH=100.

The "worst hour" is chosen independently per sub-score input (worst
precip probability hour need not be the same hour as worst wind-gust
hour) -- each is itself the max across the window, then the four maxima
are blended. This is a documented, deliberately simple methodology, not
a meteorological delay-probability model.

A closed dome/roof reports 0% risk unconditionally (see
OpenMeteoWeatherProvider.get_weather -- indoor games never hit this
module at all)."""

from typing import Dict, List, Optional, Tuple

from config.game_environment_config import (
    WEATHER_CODE_SEVERITY,
    WEATHER_RISK_GREEN_MAX,
    WEATHER_RISK_PRECIP_AMOUNT_CEILING_MM,
    WEATHER_RISK_WEIGHTS,
    WEATHER_RISK_WIND_GUST_CEILING_MPH,
    WEATHER_RISK_WIND_GUST_FLOOR_MPH,
    WEATHER_RISK_YELLOW_MAX,
)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _linear_subscore(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return _clamp((value - floor) / (ceiling - floor) * 100.0)


def weather_risk_status(risk_percent: float) -> str:
    """Short, honest label matching this percentage's GREEN/YELLOW/RED
    band -- centralized here (not duplicated in the dashboard) so the
    Python-computed value and its label can never disagree."""
    if risk_percent <= WEATHER_RISK_GREEN_MAX:
        return "Low disruption risk"
    if risk_percent <= WEATHER_RISK_YELLOW_MAX:
        return "Rain possible" if risk_percent > 0 else "Low disruption risk"
    return "High delay/postponement risk"


def compute_weather_risk(hourly_window: List[Dict[str, Optional[float]]]) -> Tuple[Optional[float], Optional[str]]:
    """`hourly_window`: one dict per forecast hour in the game window,
    each with any of the keys `precipitation_probability` (0-100),
    `precipitation` (mm), `weather_code` (WMO int), `wind_gusts_mph`.
    Missing keys/None values are simply excluded from that hour's
    contribution. Returns (None, None) when the window is empty or
    every value in it is missing -- never invents a risk score from no
    data."""
    if not hourly_window:
        return None, None

    worst: Dict[str, float] = {}

    precip_probs = [h.get("precipitation_probability") for h in hourly_window if h.get("precipitation_probability") is not None]
    if precip_probs:
        worst["precipitation_probability"] = _clamp(max(precip_probs))

    precip_amounts = [h.get("precipitation") for h in hourly_window if h.get("precipitation") is not None]
    if precip_amounts:
        worst["precipitation_amount"] = _linear_subscore(max(precip_amounts), 0.0, WEATHER_RISK_PRECIP_AMOUNT_CEILING_MM)

    codes = [h.get("weather_code") for h in hourly_window if h.get("weather_code") is not None]
    if codes:
        worst["weather_code_severity"] = max(WEATHER_CODE_SEVERITY.get(int(c), 0) for c in codes)

    gusts = [h.get("wind_gusts_mph") for h in hourly_window if h.get("wind_gusts_mph") is not None]
    if gusts:
        worst["wind_gusts"] = _linear_subscore(max(gusts), WEATHER_RISK_WIND_GUST_FLOOR_MPH, WEATHER_RISK_WIND_GUST_CEILING_MPH)

    if not worst:
        return None, None

    total_weight = sum(WEATHER_RISK_WEIGHTS[key] for key in worst)
    blended = sum(WEATHER_RISK_WEIGHTS[key] * score for key, score in worst.items()) / total_weight
    risk_percent = round(_clamp(blended), 1)
    return risk_percent, weather_risk_status(risk_percent)
