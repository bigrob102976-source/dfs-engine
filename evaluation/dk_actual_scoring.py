"""Actual DraftKings fantasy points from a REAL (postgame) stat line.

Reuses config.scoring_config.DK_SCORING -- the exact same dict
agents/pitcher_agent.py's `_projection` reads for the PREGAME estimate.
Nothing here duplicates a point value; if DK_SCORING changes, both the
projection and the actual-scoring calculation move together.

Only "completed_start" and "did_not_start" results have a real stat line
to score (a pitcher who did appear, just not as the starter, still
racked up real DK points). Every other status (scratched, postponed,
game_incomplete, missing_result) has nothing to score -- this function
says so explicitly (`scored: False`) rather than silently returning 0,
which would be indistinguishable from "a legitimately bad start."
"""

from typing import Optional

from config import batter_scoring_config as batter_cfg
from config import scoring_config as cfg
from evaluation.hitter_results_enrichment import STATUS_APPEARED as HITTER_STATUS_APPEARED
from evaluation.hitter_results_enrichment import ActualHitterResult
from evaluation.results_enrichment import (
    STATUS_COMPLETED,
    STATUS_DID_NOT_START,
    ActualPitcherResult,
)
from research import innings

_SCOREABLE_STATUSES = {STATUS_COMPLETED, STATUS_DID_NOT_START}
_HITTER_SCOREABLE_STATUSES = {HITTER_STATUS_APPEARED}


def calculate_actual_dk_points(result: ActualPitcherResult, dk_scoring: Optional[dict] = None) -> dict:
    """Returns {"scored": bool, "dfs_points": Optional[float], "breakdown": dict}."""
    dk = dk_scoring if dk_scoring is not None else cfg.DK_SCORING

    if result.status not in _SCOREABLE_STATUSES:
        return {"scored": False, "dfs_points": None, "breakdown": {}}

    decimal_innings = innings.outs_to_decimal_innings(result.outs or 0)

    breakdown = {
        "innings_points": round(decimal_innings * dk["innings_pitched"], 2),
        "strikeout_points": round((result.strikeouts or 0) * dk["strikeout"], 2),
        "earned_run_points": round((result.earned_runs or 0) * dk["earned_run"], 2),
        "walk_points": round((result.walks or 0) * dk["walk"], 2),
        "hit_points": round((result.hits_allowed or 0) * dk["hit_against"], 2),
        "hit_batsman_points": round((result.hit_batsmen or 0) * dk.get("hit_batsman", 0.0), 2),
        "win_points": round(dk.get("win", 0.0), 2) if result.win else 0.0,
    }

    complete_game_bonus = 0.0
    if result.complete_game:
        complete_game_bonus += dk.get("complete_game", 0.0)
        if result.shutout:
            complete_game_bonus += dk.get("complete_game_shutout", 0.0)
        if result.no_hitter:
            complete_game_bonus += dk.get("no_hitter", 0.0)
    breakdown["complete_game_bonus_points"] = round(complete_game_bonus, 2)

    dfs_points = round(sum(breakdown.values()), 2)
    return {"scored": True, "dfs_points": dfs_points, "breakdown": breakdown}


def calculate_actual_hitter_dk_points(result: ActualHitterResult, dk_scoring: Optional[dict] = None) -> dict:
    """Returns {"scored": bool, "dfs_points": Optional[float], "breakdown": dict}.
    Mirrors calculate_actual_dk_points() above -- same "explicit not-scored
    rather than silent zero" discipline. No cycle bonus (DraftKings Classic
    doesn't award one, and it's rare enough that config.batter_scoring_config
    .DK_HITTER_SCORING's own docstring already documents skipping it)."""
    dk = dk_scoring if dk_scoring is not None else batter_cfg.DK_HITTER_SCORING

    if result.status not in _HITTER_SCOREABLE_STATUSES:
        return {"scored": False, "dfs_points": None, "breakdown": {}}

    hits = result.hits or 0
    doubles = result.doubles or 0
    triples = result.triples or 0
    home_runs = result.home_runs or 0
    singles = max(hits - doubles - triples - home_runs, 0)

    breakdown = {
        "single_points": round(singles * dk["single"], 2),
        "double_points": round(doubles * dk["double"], 2),
        "triple_points": round(triples * dk["triple"], 2),
        "home_run_points": round(home_runs * dk["home_run"], 2),
        "rbi_points": round((result.rbi or 0) * dk["rbi"], 2),
        "run_points": round((result.runs or 0) * dk["run"], 2),
        "walk_points": round((result.walks or 0) * dk["walk"], 2),
        "hit_by_pitch_points": round((result.hit_by_pitch or 0) * dk["hit_by_pitch"], 2),
        "stolen_base_points": round((result.stolen_bases or 0) * dk["stolen_base"], 2),
    }

    dfs_points = round(sum(breakdown.values()), 2)
    return {"scored": True, "dfs_points": dfs_points, "breakdown": breakdown}
