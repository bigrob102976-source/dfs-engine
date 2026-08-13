"""Normalization stage: turn raw MLB Stats API JSON into the typed
schemas in research/models.py.

This is the only place that understands the shape of the raw source
payload. Nothing downstream (validator, storage, engine, and eventually
the agents) needs to know anything about MLB Stats API response fields.
"""

from typing import Dict, List, Tuple

from research.collector import RawSlateData
from research.models import BatterRecord, Game, NormalizedPackage, PitcherRecord, Team


def _team_from_block(team_block: dict) -> Team:
    return Team(
        team_id=str(team_block["id"]),
        abbreviation=team_block.get("abbreviation", ""),
        name=team_block.get("name", ""),
        league=(team_block.get("league") or {}).get("name"),
        division=(team_block.get("division") or {}).get("name"),
    )


def normalize_games(schedule: dict, warnings: List[str]) -> Tuple[List[Game], Dict[str, Team]]:
    games: List[Game] = []
    teams_by_id: Dict[str, Team] = {}

    for date_block in schedule.get("dates", []):
        for raw_game in date_block.get("games", []):
            game_pk = raw_game.get("gamePk")
            if game_pk is None:
                warnings.append("[normalizer] skipped a game entry with no gamePk")
                continue
            game_id = str(game_pk)

            teams = raw_game.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})
            away_team_block = away.get("team", {})
            home_team_block = home.get("team", {})

            if not away_team_block.get("id") or not home_team_block.get("id"):
                warnings.append(f"[normalizer] game {game_id}: missing home/away team id, skipped")
                continue

            teams_by_id[str(away_team_block["id"])] = _team_from_block(away_team_block)
            teams_by_id[str(home_team_block["id"])] = _team_from_block(home_team_block)

            venue = raw_game.get("venue") or {}
            away_pitcher = away.get("probablePitcher")
            home_pitcher = home.get("probablePitcher")

            game = Game(
                game_id=game_id,
                date=raw_game.get("officialDate", ""),
                game_datetime_utc=raw_game.get("gameDate"),
                status=(raw_game.get("status") or {}).get("detailedState", "unknown"),
                home_team_id=str(home_team_block["id"]),
                home_team_abbr=home_team_block.get("abbreviation", ""),
                away_team_id=str(away_team_block["id"]),
                away_team_abbr=away_team_block.get("abbreviation", ""),
                venue_id=str(venue["id"]) if venue.get("id") is not None else None,
                venue_name=venue.get("name"),
                home_probable_pitcher_id=str(home_pitcher["id"]) if home_pitcher and home_pitcher.get("id") else None,
                away_probable_pitcher_id=str(away_pitcher["id"]) if away_pitcher and away_pitcher.get("id") else None,
                game_number=raw_game.get("gameNumber"),
            )

            if not game.home_probable_pitcher_id:
                warnings.append(f"[normalizer] game {game_id}: home probable pitcher not yet announced")
            if not game.away_probable_pitcher_id:
                warnings.append(f"[normalizer] game {game_id}: away probable pitcher not yet announced")

            games.append(game)

    return games, teams_by_id


def normalize_pitchers(schedule: dict, people: Dict[str, dict], warnings: List[str]) -> List[PitcherRecord]:
    pitchers: List[PitcherRecord] = []

    for date_block in schedule.get("dates", []):
        for raw_game in date_block.get("games", []):
            game_pk = raw_game.get("gamePk")
            if game_pk is None:
                continue
            game_id = str(game_pk)

            teams = raw_game.get("teams", {})
            sides = {
                "home": teams.get("home", {}),
                "away": teams.get("away", {}),
            }

            for side, opposite in (("home", "away"), ("away", "home")):
                block = sides[side]
                pitcher = block.get("probablePitcher")
                if not pitcher or not pitcher.get("id"):
                    continue

                team_block = block.get("team", {})
                opponent_block = sides[opposite].get("team", {})
                if not team_block.get("id") or not opponent_block.get("id"):
                    warnings.append(f"[normalizer] game {game_id}: pitcher {pitcher.get('id')} missing team/opponent id")
                    continue

                player_id = str(pitcher["id"])
                person = people.get(player_id)
                throws = None
                if person:
                    throws = (person.get("pitchHand") or {}).get("code")
                else:
                    warnings.append(f"[normalizer] pitcher {player_id} ({pitcher.get('fullName')}): no bio info available, throws unknown")

                pitchers.append(PitcherRecord(
                    player_id=player_id,
                    name=pitcher.get("fullName", ""),
                    team_id=str(team_block["id"]),
                    team_abbr=team_block.get("abbreviation", ""),
                    opponent_team_id=str(opponent_block["id"]),
                    opponent_abbr=opponent_block.get("abbreviation", ""),
                    game_id=game_id,
                    throws=throws,
                ))

    return pitchers


def normalize_batters(schedule: dict, warnings: List[str]) -> List[BatterRecord]:
    batters: List[BatterRecord] = []

    for date_block in schedule.get("dates", []):
        for raw_game in date_block.get("games", []):
            game_pk = raw_game.get("gamePk")
            if game_pk is None:
                continue
            game_id = str(game_pk)

            teams = raw_game.get("teams", {})
            home_team = teams.get("home", {}).get("team", {})
            away_team = teams.get("away", {}).get("team", {})
            lineups = raw_game.get("lineups") or {}
            home_players = lineups.get("homePlayers") or []
            away_players = lineups.get("awayPlayers") or []

            if not home_players and not away_players:
                warnings.append(f"[normalizer] game {game_id}: starting lineups not yet available")
                continue

            for side_players, team_block, opponent_block in (
                (home_players, home_team, away_team),
                (away_players, away_team, home_team),
            ):
                if not team_block.get("id") or not opponent_block.get("id"):
                    warnings.append(f"[normalizer] game {game_id}: lineup present but missing team/opponent id")
                    continue
                for order, player in enumerate(side_players, start=1):
                    if not player.get("id"):
                        warnings.append(f"[normalizer] game {game_id}: lineup entry missing player id, skipped")
                        continue
                    batters.append(BatterRecord(
                        player_id=str(player["id"]),
                        name=player.get("fullName", ""),
                        team_id=str(team_block["id"]),
                        team_abbr=team_block.get("abbreviation", ""),
                        opponent_team_id=str(opponent_block["id"]),
                        opponent_abbr=opponent_block.get("abbreviation", ""),
                        game_id=game_id,
                        batting_order=order,
                        position=(player.get("primaryPosition") or {}).get("abbreviation"),
                    ))

    return batters


def normalize(raw: RawSlateData) -> NormalizedPackage:
    warnings: List[str] = []
    games, teams_by_id = normalize_games(raw.schedule, warnings)
    pitchers = normalize_pitchers(raw.schedule, raw.people, warnings)
    batters = normalize_batters(raw.schedule, warnings)
    return NormalizedPackage(
        games=games,
        teams=list(teams_by_id.values()),
        pitchers=pitchers,
        batters=batters,
        warnings=warnings,
    )
