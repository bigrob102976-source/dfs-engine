"""Assembles the unified DFS player pool: DraftKings salary/position
identity (authoritative for salary, position, team, game info) joined
with our own pregame Pitcher/Batter Agent projections (read-only, from
immutable prediction snapshots -- never recomputed or invented here).

Every DKSalaryRow produces exactly one DFSPlayer, whatever its match/
lineup status -- players are never silently dropped, only labeled.
"""

from typing import Dict, List, Optional

from dfs.models import CanonicalPlayer, DFSPlayer, DKSalaryRow, PlayerMatch
from dfs.slate_validation import DKGameMatch, SlateValidation
from dfs.team_abbreviations import normalize_dk_team_abbr


def _team_and_opponent(dk_row: DKSalaryRow, dk_game_match: Optional[DKGameMatch]):
    team = normalize_dk_team_abbr(dk_row.team_abbrev)
    opponent = None
    if dk_game_match and dk_game_match.dk_away and dk_game_match.dk_home:
        away = normalize_dk_team_abbr(dk_game_match.dk_away)
        home = normalize_dk_team_abbr(dk_game_match.dk_home)
        if team == away:
            opponent = home
        elif team == home:
            opponent = away
    return team, opponent


def _determine_lineup_status(match: PlayerMatch, dk_game_match: Optional[DKGameMatch],
                              projection_record: Optional[dict], player_type: str) -> str:
    if not dk_game_match or dk_game_match.status != "matched":
        return "game_not_on_research_slate"
    if match.match_status in ("ambiguous", "unmatched"):
        if match.match_status == "unmatched":
            return "not_in_starting_lineup" if player_type == "pitcher" else "lineup_not_confirmed"
        return "unmatched"
    # match_status == "matched"
    if projection_record is None:
        return "missing_projection"
    return "active"


def build_dfs_players(
    dk_rows: List[DKSalaryRow],
    matches: List[PlayerMatch],
    canonical_by_id: Dict[str, CanonicalPlayer],
    dk_game_matches: Dict[str, DKGameMatch],
    pitcher_raw_by_id: Dict[str, dict],
    pitcher_snapshot: Optional[dict],
    batter_snapshot: Optional[dict],
    pitcher_snapshot_path: Optional[str] = None,
    batter_snapshot_path: Optional[str] = None,
) -> List[DFSPlayer]:
    pitcher_records = {r["player_id"]: r for r in (pitcher_snapshot or {}).get("pitchers", [])}
    batter_records = {r["player_id"]: r for r in (batter_snapshot or {}).get("hitters", [])}

    players: List[DFSPlayer] = []
    for dk_row, match in zip(dk_rows, matches):
        dk_game_match = dk_game_matches.get(dk_row.game_info)
        team, opponent = _team_and_opponent(dk_row, dk_game_match)
        player_type = match.player_type or "hitter"

        game_id = None
        if match.match_status == "matched" and match.mlb_player_id in canonical_by_id:
            game_id = canonical_by_id[match.mlb_player_id].game_id
        elif dk_game_match and dk_game_match.status == "matched":
            game_id = dk_game_match.research_game_id

        projection_record = None
        if match.match_status == "matched":
            projection_record = (pitcher_records if player_type == "pitcher" else batter_records).get(match.mlb_player_id)

        lineup_status = _determine_lineup_status(match, dk_game_match, projection_record, player_type)

        player = DFSPlayer(
            dk_player_id=dk_row.dk_player_id, name=dk_row.name, team=team, player_type=player_type,
            dk_positions=list(dk_row.dk_positions), salary=dk_row.salary,
            mlb_player_id=match.mlb_player_id, opponent=opponent, game_id=game_id,
            match_status=match.match_status, match_confidence=match.match_confidence,
            lineup_status=lineup_status, avg_points_per_game_dk=dk_row.avg_points_per_game,
        )

        if projection_record:
            player.projection = projection_record.get("projection")
            player.ceiling = projection_record.get("ceiling")
            player.floor = projection_record.get("floor")
            player.overall_score = projection_record.get("overall_score")
            player.risk_score = projection_record.get("risk_score")
            player.confidence = projection_record.get("confidence")
            player.tags = list(projection_record.get("tags") or [])
            player.reasons = list(projection_record.get("reasons") or [])
            season_metrics = projection_record.get("season_metrics") or {}
            recent_metrics = projection_record.get("recent_metrics") or {}

            if player_type == "pitcher":
                player.throwing_hand = pitcher_raw_by_id.get(match.mlb_player_id, {}).get("throws")
                player.season_sample_size = season_metrics.get("innings")
                player.recent_sample_size = recent_metrics.get("innings")
                player.source_model_type = "pitcher"
                player.source_model_version = pitcher_snapshot.get("model_version")
                player.prediction_generated_at_utc = pitcher_snapshot.get("generated_at_utc")
                player.prediction_generated_at_local = pitcher_snapshot.get("generated_at_local")
                player.prediction_snapshot_path = pitcher_snapshot_path
            else:
                player.batting_hand = projection_record.get("batting_hand")
                player.batting_order = projection_record.get("batting_order")
                player.season_sample_size = season_metrics.get("plate_appearances")
                player.recent_sample_size = recent_metrics.get("plate_appearances")
                player.source_model_type = "batter"
                player.source_model_version = batter_snapshot.get("model_version")
                player.prediction_generated_at_utc = batter_snapshot.get("generated_at_utc")
                player.prediction_generated_at_local = batter_snapshot.get("generated_at_local")
                player.prediction_snapshot_path = batter_snapshot_path

        players.append(player)

    return players


def build_match_report(dk_rows: List[DKSalaryRow], matches: List[PlayerMatch],
                        players: List[DFSPlayer], slate_validation: SlateValidation) -> dict:
    matched = [m for m in matches if m.match_status == "matched"]
    ambiguous = [m for m in matches if m.match_status == "ambiguous"]
    unmatched = [m for m in matches if m.match_status == "unmatched"]

    pitchers = [p for p in players if p.player_type == "pitcher"]
    hitters = [p for p in players if p.player_type == "hitter"]

    game_matches = slate_validation.dk_game_matches
    games_matched = sum(1 for m in game_matches.values() if m.status == "matched")
    salaries = [p.salary for p in players]

    return {
        "dk_entries": len(dk_rows),
        "matched_to_mlb": len(matched),
        "pitchers_total": len(pitchers),
        "pitchers_active": sum(1 for p in pitchers if p.lineup_status == "active"),
        "hitters_total": len(hitters),
        "hitters_active": sum(1 for p in hitters if p.lineup_status == "active"),
        "hitters_excluded_lineup_not_posted": sum(1 for p in hitters if p.lineup_status == "lineup_not_confirmed"),
        "missing_projection": sum(1 for p in players if p.lineup_status == "missing_projection"),
        "unmatched_count": len(unmatched),
        "ambiguous_count": len(ambiguous),
        "unmatched": [m.to_dict() for m in unmatched],
        "ambiguous": [m.to_dict() for m in ambiguous],
        "dk_games_total": len(game_matches),
        "dk_games_matched_to_research": games_matched,
        "dk_game_matches": {
            info: {"status": m.status, "research_game_id": m.research_game_id, "dk_away": m.dk_away, "dk_home": m.dk_home}
            for info, m in game_matches.items()
        },
        "research_games_not_on_dk_slate": slate_validation.research_games_not_on_dk_slate,
        "salary_coverage_percent": round(100.0 * sum(1 for s in salaries if s) / len(salaries), 1) if salaries else 0.0,
        "position_coverage_percent": round(100.0 * sum(1 for p in players if p.dk_positions) / len(players), 1) if players else 0.0,
        "salary_min": min(salaries) if salaries else None,
        "salary_max": max(salaries) if salaries else None,
    }
