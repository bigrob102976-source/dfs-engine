"""Builds each hitter's opposing-starter context from ALREADY-ENRICHED
pitcher research -- the same PitcherInput objects the Pitcher Agent
scores, built via research.adapters.pitcher_input + research.enrichment
+ research.statcast_enrichment.

This is deliberately the ONLY bridge between the pitcher and batter
research paths, and it is a one-way, read-only bridge:

  * It imports models.pitcher.PitcherInput (a plain data model) -- never
    agents.pitcher_agent (the scoring module).
  * It exposes RAW/CONTEXTUAL pitcher metrics (K%, BB%, xERA, xwOBA
    allowed, hard-hit allowed, barrel allowed, GB%, velocity, CSW) -- it
    never touches overall_score, projection, tags, or rank. The Batter
    Agent evaluates the matchup itself from shared underlying research,
    it does not copy another agent's conclusion.
  * It performs no network calls -- the pitcher research it reads was
    already collected by the pregame pitcher pipeline.
"""

from dataclasses import replace
from typing import Dict, List, Tuple

from models.batter import BatterInput, OpposingPitcherContext
from models.pitcher import PitcherInput


def _context_from_pitcher_input(p: PitcherInput) -> OpposingPitcherContext:
    # Season CSW is never populated (see research/statcast_enrichment.py's
    # module docstring) -- fall back to recent CSW, same pattern
    # agents/pitcher_agent.py uses internally for its own scoring.
    csw_percent = p.season.csw_percent if p.season.csw_percent is not None else p.recent.csw_percent

    return OpposingPitcherContext(
        player_id=p.player_id,
        name=p.name,
        throwing_hand=p.throwing_hand,
        k_percent=p.season.k_percent,
        bb_percent=p.season.bb_percent,
        xera=p.season.xera,
        xwoba_allowed=p.season.xwoba_allowed,
        hard_hit_percent_allowed=p.season.hard_hit_percent,
        barrel_percent_allowed=p.season.barrel_percent,
        ground_ball_percent=p.season.ground_ball_percent,
        velocity=p.recent.season_velocity,
        csw_percent=csw_percent,
    )


def build_opposing_pitcher_index(pitcher_inputs: List[PitcherInput]) -> Dict[Tuple[str, str], OpposingPitcherContext]:
    """(game_id, pitcher's_own_team_abbr) -> context. A hitter looks
    themselves up via (hitter.game_id, hitter.opponent) -- the opposing
    pitcher pitches FOR the hitter's listed opponent."""
    index: Dict[Tuple[str, str], OpposingPitcherContext] = {}
    for p in pitcher_inputs:
        if not p.game_id or not p.team:
            continue
        index[(p.game_id, p.team)] = _context_from_pitcher_input(p)
    return index


def attach_opposing_pitcher_context(
    batter_inputs: List[BatterInput],
    pitcher_index: Dict[Tuple[str, str], OpposingPitcherContext],
) -> List[BatterInput]:
    enriched = []
    for b in batter_inputs:
        context = pitcher_index.get((b.game_id, b.opponent))
        if context:
            b = replace(b, opposing_pitcher=context)
        enriched.append(b)
    return enriched
