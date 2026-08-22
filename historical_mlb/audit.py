"""Data quality checks (Milestone 32.0, Part 11).

Every check function here takes plain rows (dicts/dataclasses already
built by the rest of this package) and returns a list of finding dicts
-- {"check": ..., "severity": "error"|"warning", "detail": ...} -- it
never raises and never silently fixes/drops a bad row. Reporting every
issue honestly is the explicit instruction for this milestone's Part
11; auto-repair is a later milestone's decision, not this audit's.
"""

from typing import Dict, List

from historical_mlb.leakage import field_is_leakage_risk


def _finding(check: str, severity: str, detail: str) -> Dict[str, str]:
    return {"check": check, "severity": severity, "detail": detail}


def _game_id_of(row: dict):
    """Milestone 32.0's POC-era rows used "game_id"; Milestone 32.1's
    real warehouse rows use "game_pk" (this project's canonical MLB
    game identifier -- see historical_mlb.game_universe's module
    docstring). Both are accepted so this module works unchanged
    against either row shape."""
    return row.get("game_id") if row.get("game_id") is not None else row.get("game_pk")


def check_duplicate_player_game_rows(rows: List[dict]) -> List[dict]:
    """Milestone 32.1 regression guard: keyed by (player_id, game_id,
    team), NOT just (player_id, game_id). Discovered live during the
    full warehouse build -- 2024-06-26, Blue Jays @ Red Sox (game_pk
    746942) was suspended mid-game and resumed after Danny Jansen was
    traded from TOR to BOS, making him the first player in MLB history
    to legitimately appear on BOTH teams' rosters in the same game_pk
    with two real, different stat lines. Keying by team alone (not
    dropping game_id, not merging the two lines) is the smallest change
    that both preserves catching a REAL duplicate (same player, same
    team, same game -- still an error) and stops flagging this one
    genuine, historically unique exception as corruption."""
    seen = {}
    findings = []
    for row in rows:
        key = (row.get("player_id"), _game_id_of(row), row.get("team"))
        if key in seen:
            findings.append(_finding("duplicate_player_game_row", "error", f"player_id={key[0]} game_id={key[1]} team={key[2]} appears more than once."))
        seen[key] = True
    return findings


def check_duplicate_game_ids(games: List[dict]) -> List[dict]:
    seen = {}
    findings = []
    for g in games:
        gid = g.get("canonical_game_id") or _game_id_of(g)
        if gid in seen:
            findings.append(_finding("duplicate_game_id", "error", f"canonical_game_id={gid} appears more than once."))
        seen[gid] = True
    return findings


_NEGATIVE_FORBIDDEN_FIELDS = (
    "actual_pa", "actual_1b", "actual_2b", "actual_3b", "actual_hr", "actual_bb", "actual_hbp",
    "actual_r", "actual_rbi", "actual_sb", "actual_ip", "actual_k", "actual_h", "actual_er",
)


def check_impossible_negative_counts(rows: List[dict]) -> List[dict]:
    findings = []
    for row in rows:
        for field_name in _NEGATIVE_FORBIDDEN_FIELDS:
            value = row.get(field_name)
            if value is not None and value < 0:
                findings.append(_finding(
                    "negative_counting_stat", "error",
                    f"player_id={row.get('player_id')} game_id={row.get('game_id')} {field_name}={value} is negative.",
                ))
    return findings


def check_missing_team_or_opponent(rows: List[dict]) -> List[dict]:
    findings = []
    for row in rows:
        if not row.get("team"):
            findings.append(_finding("missing_team", "error", f"player_id={row.get('player_id')} game_id={row.get('game_id')} has no team."))
        if "opponent" in row and not row.get("opponent"):
            findings.append(_finding("missing_opponent", "warning", f"player_id={row.get('player_id')} game_id={row.get('game_id')} has no opponent."))
    return findings


def check_missing_handedness(rows: List[dict]) -> List[dict]:
    findings = []
    for row in rows:
        if "bat_hand" in row and not row.get("bat_hand"):
            findings.append(_finding("missing_handedness", "warning", f"player_id={row.get('player_id')} missing bat_hand."))
        if "throw_hand" in row and not row.get("throw_hand"):
            findings.append(_finding("missing_handedness", "warning", f"player_id={row.get('player_id')} missing throw_hand."))
    return findings


def check_impossible_innings(rows: List[dict]) -> List[dict]:
    """An MLB half-inning has at most 3 outs recorded per pitcher-inning
    boundary; a single start's innings_pitched decimal fractional part
    (after outs->decimal conversion) must be .0/.1/.2 in baseball
    notation terms -- represented here post-conversion as a
    non-negative float with no upper bound assumed (extra-inning
    outings are legitimate), but a negative value is always impossible."""
    findings = []
    for row in rows:
        ip = row.get("actual_ip")
        if ip is not None and ip < 0:
            findings.append(_finding("impossible_innings", "error", f"player_id={row.get('player_id')} game_id={row.get('game_id')} actual_ip={ip} is negative."))
    return findings


def check_invalid_dates(rows: List[dict], date_field: str = "game_date") -> List[dict]:
    import re
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    findings = []
    for row in rows:
        value = row.get(date_field)
        if value is None or not date_re.match(str(value)):
            findings.append(_finding("invalid_date", "error", f"player_id={row.get('player_id')} {date_field}={value!r} is not a valid YYYY-MM-DD date."))
    return findings


def check_no_leaked_actuals_in_features(feature_row: dict) -> List[dict]:
    """Applies historical_mlb.leakage.field_is_leakage_risk to every key
    in a FEATURE dict (the pregame side of a training row) -- an
    actual_* key present there is always an error, never a warning,
    since it directly violates Part 6's anti-leakage rule."""
    findings = []
    for key in feature_row:
        if field_is_leakage_risk(key):
            findings.append(_finding("leaked_actual_in_features", "error", f"Feature row contains forbidden field {key!r}."))
    return findings


def check_future_data_leakage(rows: List[dict], target_date_field: str = "game_date", observation_date_field: str = "as_of_date") -> List[dict]:
    findings = []
    for row in rows:
        target = row.get(target_date_field)
        as_of = row.get(observation_date_field)
        if target and as_of and as_of > target:
            findings.append(_finding("future_data_leakage", "error", f"player_id={row.get('player_id')} as_of={as_of} is after game_date={target}."))
    return findings


def check_doubleheader_collisions(games: List[dict]) -> List[dict]:
    """Two games sharing date+away+home MUST have distinct game_number
    values -- if they don't (or if game_number is missing entirely on a
    date+team collision), that's exactly the silent-doubleheader-merge
    bug Part 5/11 explicitly warn about."""
    from collections import defaultdict
    by_matchup: Dict[tuple, List[dict]] = defaultdict(list)
    for g in games:
        by_matchup[(g.get("date") or g.get("game_date"), g.get("away_team"), g.get("home_team"))].append(g)

    findings = []
    for matchup, matchup_games in by_matchup.items():
        if len(matchup_games) < 2:
            continue
        game_numbers = [g.get("game_number", 1) for g in matchup_games]
        if len(set(game_numbers)) != len(game_numbers):
            findings.append(_finding(
                "doubleheader_collision", "error",
                f"{len(matchup_games)} games for {matchup} share game_number values {game_numbers} -- would silently merge in a naive date+teams join.",
            ))
    return findings


def run_all_checks(hitter_rows: List[dict], pitcher_rows: List[dict], games: List[dict]) -> List[dict]:
    """Convenience runner for the small proof-of-concept dataset (Part
    10) -- runs every applicable check and returns the combined,
    de-duplicated-by-nothing (every individual finding kept) list."""
    findings: List[dict] = []
    all_player_rows = hitter_rows + pitcher_rows
    findings += check_duplicate_player_game_rows(all_player_rows)
    findings += check_duplicate_game_ids(games)
    findings += check_impossible_negative_counts(all_player_rows)
    findings += check_missing_team_or_opponent(all_player_rows)
    findings += check_missing_handedness(all_player_rows)
    findings += check_impossible_innings(pitcher_rows)
    findings += check_invalid_dates(all_player_rows)
    findings += check_doubleheader_collisions(games)
    return findings
