"""Validation stage: sanity-check a normalized package before it's saved.

Validation never deletes or edits data — it only produces
`ValidationIssue`s (warning or error) that get folded into the research
metadata. "Never silently discard information" means a duplicate or
suspicious record is still written to disk; the issue list is what makes
the problem visible to whoever (or whatever agent) reads the package
next.
"""

from collections import Counter
from datetime import datetime
from typing import List

from research.models import BatterRecord, Game, PitcherRecord, Team, ValidationIssue


def validate_date(slate_date: str) -> List[ValidationIssue]:
    issues = []
    try:
        datetime.strptime(slate_date, "%Y-%m-%d")
    except ValueError:
        issues.append(ValidationIssue("error", f"[validator] slate date '{slate_date}' is not in YYYY-MM-DD format"))
    return issues


def validate_games(games: List[Game], slate_date: str) -> List[ValidationIssue]:
    issues = []

    for game in games:
        if not game.game_id:
            issues.append(ValidationIssue("error", "[validator] found a game with an empty game_id"))
        if not game.home_team_id or not game.away_team_id:
            issues.append(ValidationIssue("error", f"[validator] game {game.game_id} is missing a home or away team id"))
        if game.date and game.date != slate_date:
            issues.append(ValidationIssue(
                "warning",
                f"[validator] game {game.game_id} officialDate '{game.date}' does not match requested slate date '{slate_date}'",
            ))

    duplicate_ids = [gid for gid, count in Counter(g.game_id for g in games).items() if count > 1]
    for gid in duplicate_ids:
        issues.append(ValidationIssue("error", f"[validator] duplicate game_id '{gid}' appears more than once"))

    return issues


def validate_teams(teams: List[Team]) -> List[ValidationIssue]:
    issues = []
    for team in teams:
        if not team.team_id:
            issues.append(ValidationIssue("error", "[validator] found a team with an empty team_id"))
        if not team.abbreviation:
            issues.append(ValidationIssue("warning", f"[validator] team {team.team_id} is missing an abbreviation"))

    duplicate_ids = [tid for tid, count in Counter(t.team_id for t in teams).items() if count > 1]
    for tid in duplicate_ids:
        issues.append(ValidationIssue("error", f"[validator] duplicate team_id '{tid}' appears more than once"))

    return issues


def validate_pitchers(pitchers: List[PitcherRecord], known_team_ids: set, known_game_ids: set) -> List[ValidationIssue]:
    issues = []

    for p in pitchers:
        if not p.player_id:
            issues.append(ValidationIssue("error", "[validator] found a pitcher record with an empty player_id"))
        if p.game_id not in known_game_ids:
            issues.append(ValidationIssue("error", f"[validator] pitcher {p.player_id} references unknown game_id '{p.game_id}'"))
        if p.team_id not in known_team_ids:
            issues.append(ValidationIssue("warning", f"[validator] pitcher {p.player_id} references unknown team_id '{p.team_id}'"))

    duplicate_keys = [key for key, count in Counter((p.game_id, p.player_id) for p in pitchers).items() if count > 1]
    for game_id, player_id in duplicate_keys:
        issues.append(ValidationIssue(
            "warning",
            f"[validator] duplicate pitcher record: player {player_id} listed more than once in game {game_id}",
        ))

    cross_game_counts = Counter(p.player_id for p in pitchers)
    for player_id, count in cross_game_counts.items():
        if count > 1:
            games_involved = sorted({p.game_id for p in pitchers if p.player_id == player_id})
            if len(games_involved) > 1:
                issues.append(ValidationIssue(
                    "warning",
                    f"[validator] pitcher {player_id} listed as probable in multiple games on this date: {games_involved}",
                ))

    return issues


def validate_batters(batters: List[BatterRecord], known_team_ids: set, known_game_ids: set) -> List[ValidationIssue]:
    issues = []

    for b in batters:
        if not b.player_id:
            issues.append(ValidationIssue("error", "[validator] found a batter record with an empty player_id"))
        if b.game_id not in known_game_ids:
            issues.append(ValidationIssue("error", f"[validator] batter {b.player_id} references unknown game_id '{b.game_id}'"))
        if b.team_id not in known_team_ids:
            issues.append(ValidationIssue("warning", f"[validator] batter {b.player_id} references unknown team_id '{b.team_id}'"))

    duplicate_keys = [key for key, count in Counter((b.game_id, b.player_id) for b in batters).items() if count > 1]
    for game_id, player_id in duplicate_keys:
        issues.append(ValidationIssue(
            "warning",
            f"[validator] duplicate batter record: player {player_id} listed more than once in game {game_id}",
        ))

    return issues


def validate(
    games: List[Game],
    teams: List[Team],
    pitchers: List[PitcherRecord],
    batters: List[BatterRecord],
    slate_date: str,
) -> List[ValidationIssue]:
    known_team_ids = {t.team_id for t in teams}
    known_game_ids = {g.game_id for g in games}

    issues: List[ValidationIssue] = []
    issues += validate_date(slate_date)
    issues += validate_games(games, slate_date)
    issues += validate_teams(teams)
    issues += validate_pitchers(pitchers, known_team_ids, known_game_ids)
    issues += validate_batters(batters, known_team_ids, known_game_ids)
    return issues
