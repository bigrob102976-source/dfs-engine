"""Milestone 32.1 -- Statcast-derived features beyond M32.0's basic
per-player hard-hit/barrel/xwOBA aggregation (historical_mlb.rolling.
aggregate_statcast_rates, still used for Parts 14/15's individual
hitter/pitcher-allowed rates).

This module adds platoon splits (Part 16) and opponent-offense
aggregates (Part 18), BOTH derived from the same pitch-level Statcast
rows already being fetched/cached for the rolling windows -- no new
network calls.

DOCUMENTED LIMITATION (reported honestly in M32.1's final report, not
hidden): platoon splits and opponent-offense features here reflect
whatever date window the caller passes in (this build uses the same
trailing-30-day buffer as the other Statcast features), NOT a true
full-season-to-date split. A full-season Statcast accumulation was
judged too memory-heavy to build/verify within this milestone's budget
(a full MLB season is ~700K+ pitch rows); the trailing-30-day window is
a real, leakage-safe, but shallower proxy. This is called out explicitly
in the feature manifest's descriptions.

PA outcomes are derived from Statcast's own `events` column (non-null
only on the pitch that ends a plate appearance) -- this is standing in
for what a dedicated platoon-split endpoint would give directly, using
data already on hand.
"""

from typing import Dict, List, Optional

_HIT_EVENTS = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
_OUT_OF_PLAY_PA_EVENTS = {
    "single", "double", "triple", "home_run", "field_out", "grounded_into_double_play", "double_play",
    "force_out", "fielders_choice", "fielders_choice_out", "sac_fly", "sac_fly_double_play",
    "field_error", "triple_play",
}
_WALK_EVENTS = {"walk", "intent_walk"}
_HBP_EVENTS = {"hit_by_pitch"}
_STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
_SAC_FLY_EVENTS = {"sac_fly", "sac_fly_double_play"}

# All events that end a plate appearance (used to count PA -- a superset
# of the specific outcome buckets above, e.g. also includes sac bunts).
_PA_ENDING_EVENTS = _OUT_OF_PLAY_PA_EVENTS | _WALK_EVENTS | _HBP_EVENTS | _STRIKEOUT_EVENTS | {
    "sac_bunt", "sac_bunt_double_play", "catcher_interf", "batter_interference",
}


def _f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pa_stat_line(events: List[str]) -> Dict[str, Optional[float]]:
    pa = len(events)
    if pa == 0:
        return {"pa": 0, "avg": None, "obp": None, "slg": None, "woba": None}
    hits = sum(1 for e in events if e in _HIT_EVENTS)
    walks = sum(1 for e in events if e in _WALK_EVENTS)
    hbp = sum(1 for e in events if e in _HBP_EVENTS)
    sac_fly = sum(1 for e in events if e in _SAC_FLY_EVENTS)
    total_bases = sum(_HIT_EVENTS[e] for e in events if e in _HIT_EVENTS)
    ab = pa - walks - hbp - sac_fly
    avg = round(hits / ab, 4) if ab else None
    obp_denom = ab + walks + hbp + sac_fly
    obp = round((hits + walks + hbp) / obp_denom, 4) if obp_denom else None
    slg = round(total_bases / ab, 4) if ab else None
    woba_denom = ab + walks + hbp + sac_fly
    singles = hits - sum(1 for e in events if e in ("double", "triple", "home_run"))
    woba = None
    if woba_denom:
        doubles = sum(1 for e in events if e == "double")
        triples = sum(1 for e in events if e == "triple")
        home_runs = sum(1 for e in events if e == "home_run")
        woba = round((0.69 * walks + 0.72 * hbp + 0.89 * singles + 1.27 * doubles + 1.62 * triples + 2.10 * home_runs) / woba_denom, 4)
    return {"pa": pa, "avg": avg, "obp": obp, "slg": slg, "woba": woba}


def hitter_platoon_splits(pitch_rows: List[dict], batter_id: str) -> Dict[str, Dict[str, Optional[float]]]:
    """Returns {"vs_lhp": {...}, "vs_rhp": {...}} -- each a _pa_stat_line
    dict, computed from PA-ending events only, split by the PITCHER's
    throwing hand (`p_throws` from the batter's perspective)."""
    my_rows = [r for r in pitch_rows if r.get("batter") == str(batter_id) and (r.get("events") or "") in _PA_ENDING_EVENTS]
    vs_lhp = [r["events"] for r in my_rows if r.get("p_throws") == "L"]
    vs_rhp = [r["events"] for r in my_rows if r.get("p_throws") == "R"]
    return {"vs_lhp": _pa_stat_line(vs_lhp), "vs_rhp": _pa_stat_line(vs_rhp)}


def pitcher_platoon_splits_allowed(pitch_rows: List[dict], pitcher_id: str) -> Dict[str, Dict[str, Optional[float]]]:
    """Returns {"vs_lhb": {...}, "vs_rhb": {...}} -- split by the
    BATTER's stand, from the pitcher's perspective (what they allowed)."""
    my_rows = [r for r in pitch_rows if r.get("pitcher") == str(pitcher_id) and (r.get("events") or "") in _PA_ENDING_EVENTS]
    vs_lhb = [r["events"] for r in my_rows if r.get("stand") == "L"]
    vs_rhb = [r["events"] for r in my_rows if r.get("stand") == "R"]
    return {"vs_lhb": _pa_stat_line(vs_lhb), "vs_rhb": _pa_stat_line(vs_rhb)}


def _batting_team(row: dict) -> Optional[str]:
    """Statcast's inning_topbot: 'Top' -> away team bats, 'Bot' -> home team bats."""
    if row.get("inning_topbot") == "Top":
        return row.get("away_team")
    if row.get("inning_topbot") == "Bot":
        return row.get("home_team")
    return None


def opponent_offense_aggregate(pitch_rows: List[dict], opponent_team: str) -> Dict[str, Optional[float]]:
    """Part 18: opponent historical K%/BB%/HR rate/offensive production
    rate, aggregated from every PA-ending event where the BATTING team
    (derived from inning_topbot + home_team/away_team) is the opponent."""
    team_rows = [r for r in pitch_rows if (r.get("events") or "") in _PA_ENDING_EVENTS and _batting_team(r) == opponent_team]
    pa = len(team_rows)
    if pa == 0:
        return {"k_pct": None, "bb_pct": None, "hr_rate": None, "woba": None, "sample_games": 0, "sample_pa": 0}
    events = [r["events"] for r in team_rows]
    stat_line = _pa_stat_line(events)
    strikeouts = sum(1 for e in events if e in _STRIKEOUT_EVENTS)
    walks = sum(1 for e in events if e in _WALK_EVENTS)
    home_runs = sum(1 for e in events if e == "home_run")
    sample_games = len({r.get("game_pk") for r in team_rows if r.get("game_pk")})
    return {
        "k_pct": round(strikeouts / pa, 4), "bb_pct": round(walks / pa, 4),
        "hr_rate": round(home_runs / pa, 4), "woba": stat_line["woba"],
        "sample_games": sample_games, "sample_pa": pa,
    }
