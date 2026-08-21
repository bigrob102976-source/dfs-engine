"""actual_dk_points calculation from a historical MLB box score
(Milestone 32.0, Part 8).

This module NEVER redefines DK scoring weights -- it reuses
evaluation.dk_actual_scoring.calculate_actual_dk_points /
calculate_actual_hitter_dk_points VERBATIM, which themselves read
config.scoring_config.DK_SCORING / config.batter_scoring_config.DK_HITTER_SCORING
(the exact same dicts the live pregame projection agents use). If DK's
scoring rules ever change, this module moves with them automatically --
there is no second copy of a point value anywhere in this package.

The existing evaluation/*_enrichment.py modules are prediction-VALIDATION
oriented: parse_hitter_result()/parse_pitcher_result() look up one
SPECIFIC expected/predicted player in a boxscore. The historical
warehouse needs the opposite: every player who appeared in a game, full
stop, regardless of whether we ever "predicted" them. This module
builds ActualPitcherResult/ActualHitterResult objects directly from
historical_mlb.sources.mlb_stats.extract_all_boxscore_players()'s raw
stat blocks (the same MLB Stats API field names those enrichment
modules already parse -- verified field-for-field against
evaluation/results_enrichment.py and evaluation/hitter_results_enrichment.py
so a box score scores identically either way), then calls the existing
calculator on each one.
"""

from typing import List, Tuple

from evaluation.dk_actual_scoring import calculate_actual_dk_points, calculate_actual_hitter_dk_points
from evaluation.hitter_results_enrichment import STATUS_APPEARED, ActualHitterResult
from evaluation.results_enrichment import STATUS_COMPLETED, ActualPitcherResult
from research import innings


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def pitcher_result_from_boxscore_entry(entry: dict, game_id: str, game_date: str) -> ActualPitcherResult:
    """`entry` is one item from extract_all_boxscore_players()'s pitcher
    list: player_id, name, team, stat (MLB Stats API's raw pitching
    stat block). `outs` is derived from the stat block's own
    `inningsPitched` string (e.g. "6.2") via research.innings, the SAME
    helper the live postgame path already uses -- never re-parsed with
    a second implementation."""
    stat = entry["stat"]
    ip_str = stat.get("inningsPitched")
    # MLB Stats API's inningsPitched is baseball notation ("6.2" == 6
    # and 2/3 innings, NOT decimal 6.2) -- innings_notation_to_outs()
    # parses that notation correctly; a naive float() cast here would
    # silently misscore every start with a fractional inning.
    outs = innings.innings_notation_to_outs(ip_str) if ip_str not in (None, "") else 0
    return ActualPitcherResult(
        player_id=str(entry["player_id"]), game_id=str(game_id), game_date=game_date,
        status=STATUS_COMPLETED,  # every entry here DID appear with a real pitching stat block -- "completed" in the sense calculate_actual_dk_points() requires to score at all
        name=entry.get("name"), team=entry.get("team"),
        outs=outs, innings_pitched=ip_str,
        # Bare _safe_int (never `or None`): a real 0 (e.g. 0 home runs
        # allowed) must stay 0, not collapse into "missing" -- `_safe_int`
        # already returns 0 for a genuinely absent field too, so `or None`
        # would make a true zero indistinguishable from missing data
        # instead of fixing that ambiguity.
        batters_faced=_safe_int(stat.get("battersFaced")),
        strikeouts=_safe_int(stat.get("strikeOuts")),
        walks=_safe_int(stat.get("baseOnBalls")),
        hits_allowed=_safe_int(stat.get("hits")),
        earned_runs=_safe_int(stat.get("earnedRuns")),
        home_runs_allowed=_safe_int(stat.get("homeRuns")),
        hit_batsmen=_safe_int(stat.get("hitBatsmen")),
        win=bool(stat.get("wins")),
        loss=bool(stat.get("losses")),
        complete_game=bool(stat.get("completeGames")),
        shutout=bool(stat.get("shutouts")),
        no_hitter=False,  # MLB Stats API's pitching stat block has no explicit no-hitter flag -- never guessed from hits==0 (could be a combined/relief no-hitter misattributed to one pitcher)
        source="mlb_stats_api_historical",
    )


def hitter_result_from_boxscore_entry(entry: dict, game_id: str, game_date: str) -> ActualHitterResult:
    stat = entry["stat"]
    return ActualHitterResult(
        player_id=str(entry["player_id"]), game_id=str(game_id), game_date=game_date,
        status=STATUS_APPEARED,
        name=entry.get("name"), team=entry.get("team"),
        # See pitcher_result_from_boxscore_entry's comment above -- bare
        # _safe_int throughout, never `or None`, so a real 0 PA (e.g. a
        # pinch runner who never batted) stays 0.
        plate_appearances=_safe_int(stat.get("plateAppearances")),
        at_bats=_safe_int(stat.get("atBats")),
        runs=_safe_int(stat.get("runs")),
        hits=_safe_int(stat.get("hits")),
        doubles=_safe_int(stat.get("doubles")),
        triples=_safe_int(stat.get("triples")),
        home_runs=_safe_int(stat.get("homeRuns")),
        rbi=_safe_int(stat.get("rbi")),
        walks=_safe_int(stat.get("baseOnBalls")),
        strikeouts=_safe_int(stat.get("strikeOuts")),
        hit_by_pitch=_safe_int(stat.get("hitByPitch")),
        stolen_bases=_safe_int(stat.get("stolenBases")),
        source="mlb_stats_api_historical",
    )


def score_boxscore(pitchers: List[dict], hitters: List[dict], game_id: str, game_date: str) -> Tuple[List[dict], List[dict]]:
    """Top-level entry point: takes extract_all_boxscore_players()'s
    output, returns (pitcher_rows, hitter_rows) each carrying the
    original identity fields plus actual_dk_points + the full scoring
    breakdown (never just a bare number -- auditable back to the
    underlying counting stats, matching this project's existing
    "distinguish observed data / calculated metrics" discipline)."""
    pitcher_rows = []
    for entry in pitchers:
        result = pitcher_result_from_boxscore_entry(entry, game_id, game_date)
        scored = calculate_actual_dk_points(result)
        pitcher_rows.append({
            "player_id": result.player_id, "name": result.name, "team": result.team,
            "game_id": game_id, "game_date": game_date,
            "actual_ip": innings.outs_to_decimal_innings(result.outs or 0),
            "actual_k": result.strikeouts, "actual_h": result.hits_allowed,
            "actual_bb": result.walks, "actual_er": result.earned_runs,
            "actual_win": result.win, "actual_dk_points": scored["dfs_points"],
            "dk_points_breakdown": scored["breakdown"],
        })

    hitter_rows = []
    for entry in hitters:
        result = hitter_result_from_boxscore_entry(entry, game_id, game_date)
        scored = calculate_actual_hitter_dk_points(result)
        singles = max((result.hits or 0) - (result.doubles or 0) - (result.triples or 0) - (result.home_runs or 0), 0)
        hitter_rows.append({
            "player_id": result.player_id, "name": result.name, "team": result.team,
            "game_id": game_id, "game_date": game_date,
            "actual_pa": result.plate_appearances, "actual_1b": singles,
            "actual_2b": result.doubles, "actual_3b": result.triples, "actual_hr": result.home_runs,
            "actual_bb": result.walks, "actual_hbp": result.hit_by_pitch,
            "actual_r": result.runs, "actual_rbi": result.rbi, "actual_sb": result.stolen_bases,
            "actual_dk_points": scored["dfs_points"], "dk_points_breakdown": scored["breakdown"],
        })

    return pitcher_rows, hitter_rows
