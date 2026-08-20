"""FantasyPros projected (fractional, expected-value) stats -> DraftKings
fantasy points. Reuses config.scoring_config.DK_SCORING and
config.batter_scoring_config.DK_HITTER_SCORING VERBATIM -- the exact same
dicts agents/pitcher_agent.py, agents/batter_agent.py, and
evaluation/dk_actual_scoring.py already use. No point value is invented
or duplicated here; only the WEIGHTS are read, applied to FantasyPros'
own stat field names instead of a real box score.

This is deliberately NOT a call into evaluation/dk_actual_scoring.py's
calculate_actual_dk_points()/calculate_actual_hitter_dk_points(): those
are typed and status-gated for real, already-happened, integer-count
results (ActualPitcherResult/ActualHitterResult, status="appeared" etc.)
-- a genuinely different kind of input than a fractional PROJECTION
(FantasyPros' own numbers are expected values, e.g. "hrs": 0.09, not
integer counts). Reusing those functions on fractional input would be a
type/semantic mismatch even though the arithmetic would happen to work;
this module mirrors their exact formula shape instead, so both stay
readable as "the same weights, applied to two different kinds of input."

FIELD MAPPING (confirmed via live API response, 2026-08-19 --
fantasypros/client.py's docstring):

  Hitters (config.batter_scoring_config.DK_HITTER_SCORING):
    single     (3.0)  <- stats["1b"]
    double     (5.0)  <- stats["2b"]
    triple     (8.0)  <- stats["3b"]
    home_run  (10.0)  <- stats["hrs"]
    rbi        (2.0)  <- stats["rbi"]
    run        (2.0)  <- stats["runs"]
    walk       (2.0)  <- stats["bb"]     (FantasyPros' "bb" already
                                           includes intentional walks --
                                           "ibb" is NOT added separately,
                                           which would double-count)
    hit_by_pitch (2.0) <- stats["hbp"]
    stolen_base  (5.0) <- stats["sb"]

  Pitchers (config.scoring_config.DK_SCORING):
    innings_pitched (2.25) <- stats["ip"]   (FantasyPros gives decimal
                                              innings directly, e.g. 6.13
                                              -- no thirds-of-an-inning
                                              conversion needed, unlike a
                                              real box score's outs count)
    strikeout        (2.0) <- stats["k"]
    earned_run       (-2.0) <- stats["er"]
    walk             (-0.6) <- stats["bbi"]  ("bb issued" -- FantasyPros
                                               distinguishes a PITCHER's
                                               own walk total, "bbi", from
                                               a HITTER's "bb"; using "bb"
                                               here would be wrong)
    hit_against       (-0.6) <- stats["h"]
    hit_batsman        (-0.6) <- stats["hp"]
    win                (4.0) <- stats["w"]   (fractional win probability
                                               -- an expected-value
                                               contribution, same logic
                                               as multiplying fractional
                                               IP by the per-inning rate)
    complete_game      (2.5) <- stats["cg"]
    complete_game_shutout (2.5) <- stats["sho"]

  NOT applied: DK's "no_hitter" (5.0) bonus -- FantasyPros' documented
  response fields (confirmed live) do not include a no-hitter-probability
  stat; inventing one would violate this milestone's explicit "do not
  invent a fantasy-point value" instruction. An extremely rare event in
  any case (near-zero expected-value impact).
"""

from typing import Dict

from config import batter_scoring_config as batter_cfg
from config import scoring_config as pitcher_cfg


def calculate_fantasypros_hitter_dk_points(stats: Dict[str, float]) -> dict:
    """Returns {"dk_points": float, "breakdown": {...}}. Missing stat
    fields are treated as 0.0 contribution (never invented), matching
    dict.get(..., 0.0) throughout -- a FantasyPros response that omits a
    field entirely (rather than reporting a real 0) simply contributes
    nothing for that component, exactly as evaluation/dk_actual_scoring.py's
    (result.field or 0) pattern already does for real results."""
    dk = batter_cfg.DK_HITTER_SCORING
    breakdown = {
        "single_points": round(stats.get("1b", 0.0) * dk["single"], 3),
        "double_points": round(stats.get("2b", 0.0) * dk["double"], 3),
        "triple_points": round(stats.get("3b", 0.0) * dk["triple"], 3),
        "home_run_points": round(stats.get("hrs", 0.0) * dk["home_run"], 3),
        "rbi_points": round(stats.get("rbi", 0.0) * dk["rbi"], 3),
        "run_points": round(stats.get("runs", 0.0) * dk["run"], 3),
        "walk_points": round(stats.get("bb", 0.0) * dk["walk"], 3),
        "hit_by_pitch_points": round(stats.get("hbp", 0.0) * dk["hit_by_pitch"], 3),
        "stolen_base_points": round(stats.get("sb", 0.0) * dk["stolen_base"], 3),
    }
    return {"dk_points": round(sum(breakdown.values()), 2), "breakdown": breakdown}


def calculate_fantasypros_pitcher_dk_points(stats: Dict[str, float]) -> dict:
    dk = pitcher_cfg.DK_SCORING
    breakdown = {
        "innings_points": round(stats.get("ip", 0.0) * dk["innings_pitched"], 3),
        "strikeout_points": round(stats.get("k", 0.0) * dk["strikeout"], 3),
        "earned_run_points": round(stats.get("er", 0.0) * dk["earned_run"], 3),
        "walk_points": round(stats.get("bbi", 0.0) * dk["walk"], 3),
        "hit_against_points": round(stats.get("h", 0.0) * dk["hit_against"], 3),
        "hit_batsman_points": round(stats.get("hp", 0.0) * dk.get("hit_batsman", 0.0), 3),
        "win_points": round(stats.get("w", 0.0) * dk.get("win", 0.0), 3),
        "complete_game_points": round(stats.get("cg", 0.0) * dk.get("complete_game", 0.0), 3),
        "shutout_points": round(stats.get("sho", 0.0) * dk.get("complete_game_shutout", 0.0), 3),
    }
    return {"dk_points": round(sum(breakdown.values()), 2), "breakdown": breakdown}
