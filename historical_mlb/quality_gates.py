"""Milestone 32.1, Part 29 -- HARD-FAIL quality gates for the real,
generated warehouse. Distinct from M32.0's historical_mlb.audit module
(which reports findings and never raises, appropriate for a POC): once
a real warehouse is being built for model training, the specific
violations Part 29 lists must actually STOP the build, not just get
logged. This module reuses audit.py's check functions where they
already exist (never a second implementation of "is this duplicate")
and adds the ones Part 29 needs that audit.py doesn't have yet.
"""

from typing import Dict, List

from historical_mlb import audit
from historical_mlb.manifest import hitter_manifest, pitcher_manifest


class QualityGateFailure(Exception):
    def __init__(self, findings: List[dict]):
        self.findings = findings
        super().__init__(f"{len(findings)} quality gate violation(s): {findings[:5]}{'...' if len(findings) > 5 else ''}")


def check_target_fields_not_pregame_features(manifest_entity_fields: List, feature_row: dict) -> List[dict]:
    """The exact enforcement Part 23 tests must prove: no TARGET or
    HISTORICAL_OUTCOME_ONLY column may be exposed as if it were an
    ALWAYS_PREGAME/PREGAME_AFTER_LINEUPS feature. Since every column in
    a generated row IS present (outcomes + features live in the same
    row by design -- Part 24 says the target must exist ONLY as an
    outcome/target, never fed back as a feature INPUT elsewhere), this
    check instead verifies the MANIFEST itself never mis-classifies an
    actual_*/target column as pregame-safe -- the structural guarantee
    a future model-training step relies on."""
    findings = []
    forbidden_prefixes = ("actual_",)
    for f in manifest_entity_fields:
        looks_like_outcome = any(f.name.startswith(p) for p in forbidden_prefixes)
        if looks_like_outcome and f.availability_class not in ("HISTORICAL_OUTCOME_ONLY", "TARGET"):
            findings.append({
                "check": "target_field_misclassified_as_pregame", "severity": "error",
                "detail": f"{f.name!r} looks like an outcome field but is classified {f.availability_class!r}.",
            })
        if f.name in feature_row and f.availability_class == "TARGET" and not f.target_flag:
            findings.append({"check": "target_flag_missing", "severity": "error", "detail": f"{f.name!r} is TARGET but target_flag is False."})
    return findings


def check_cross_game_contamination(rows: List[dict]) -> List[dict]:
    """A rolling/statcast feature value that is IDENTICAL across two
    different games for the same player AND non-trivial (nonzero
    sample size) is not inherently a bug (a player can genuinely have
    the same 30-day average twice), but a SEASON-TO-DATE sample-size
    field going DOWN as game_date goes UP for the same player, WITHIN
    THE SAME SEASON, is impossible under a correctly-excluding-target-
    game implementation (more history should only ever accumulate over
    one season) -- that specific, structurally-impossible pattern is
    what this checks for, using rolling_games_season as the canary
    field (Part 29's structural "cross-game contamination" check).

    Deliberately compares only consecutive rows within the SAME season
    (row["season"], falling back to the game_date's year when a "season"
    key isn't present) -- season-to-date rolling counts correctly RESET
    at the start of a new season, so a drop across a season boundary
    (e.g. 13 games late in 2024, then 3 games early in 2025) is
    expected, healthy behavior, not contamination. This was caught live
    validating this milestone's own partial warehouse, which legitimately
    spans a season-boundary gap in what had been collected so far."""
    findings = []
    by_player: Dict[str, List[dict]] = {}
    for row in rows:
        by_player.setdefault(row["player_id"], []).append(row)
    for player_id, player_rows in by_player.items():
        ordered = sorted(player_rows, key=lambda r: r["game_date"])
        prev_games = -1
        prev_date = None
        prev_season = None
        for row in ordered:
            games = row.get("rolling_games_season")
            season = row.get("season") or row["game_date"][:4]
            same_season = prev_season is not None and season == prev_season
            if games is not None and prev_games != -1 and same_season and row["game_date"] != prev_date and games < prev_games:
                findings.append({
                    "check": "cross_game_contamination", "severity": "error",
                    "detail": f"player_id={player_id} rolling_games_season went from {prev_games} to {games} between {prev_date} and {row['game_date']} (same season {season}).",
                })
            if games is not None:
                prev_games = games
            prev_date = row["game_date"]
            prev_season = season
    return findings


def run_quality_gates(hitter_rows: List[dict], pitcher_rows: List[dict], game_rows: List[dict]) -> List[dict]:
    """Runs every Part 29 check. Returns the full findings list (for
    the quality report) -- caller decides whether to raise via
    enforce_quality_gates() below."""
    findings: List[dict] = []
    all_player_rows = hitter_rows + pitcher_rows
    # Checked SEPARATELY, never combined: the warehouse has two
    # distinct tables (Part 2), and a pitcher who also batted (common
    # in NL parks without a DH) legitimately produces ONE row in each
    # table for the same (player_id, game_pk) -- that is not a
    # duplicate, it's two different entities sharing a real person.
    findings += audit.check_duplicate_player_game_rows(hitter_rows)
    findings += audit.check_duplicate_player_game_rows(pitcher_rows)
    findings += audit.check_duplicate_game_ids(game_rows)
    findings += audit.check_impossible_negative_counts(all_player_rows)
    findings += audit.check_impossible_innings(pitcher_rows)
    findings += audit.check_invalid_dates(all_player_rows)
    findings += audit.check_doubleheader_collisions(game_rows)
    findings += check_target_fields_not_pregame_features(hitter_manifest(), {})
    findings += check_target_fields_not_pregame_features(pitcher_manifest(), {})
    findings += check_cross_game_contamination(hitter_rows)
    findings += check_cross_game_contamination(pitcher_rows)

    # Negative singles specifically (Part 9/29) -- audit.py's generic
    # negative-count check already covers actual_1b via its forbidden-
    # fields list, this just double-confirms the exact rule Part 9
    # states (1B = H - 2B - 3B - HR must be >= 0).
    for row in hitter_rows:
        if row.get("actual_1b") is not None and row["actual_1b"] < 0:
            findings.append({"check": "negative_singles", "severity": "error", "detail": f"player_id={row['player_id']} game_id={row['game_pk']} actual_1b={row['actual_1b']}."})

    # Missing required game IDs.
    for row in game_rows:
        if not row.get("game_pk"):
            findings.append({"check": "missing_game_id", "severity": "error", "detail": f"Game row missing game_pk: {row}."})

    return findings


BLOCKING_CHECKS = {
    "duplicate_player_game_row", "duplicate_game_id", "negative_counting_stat", "negative_singles",
    "impossible_innings", "invalid_date", "doubleheader_collision", "target_field_misclassified_as_pregame",
    "target_flag_missing", "cross_game_contamination", "missing_game_id",
}


def enforce_quality_gates(hitter_rows: List[dict], pitcher_rows: List[dict], game_rows: List[dict]) -> List[dict]:
    """Raises QualityGateFailure if any BLOCKING_CHECKS finding exists.
    Returns the full findings list (including any non-blocking ones)
    on success, so the caller can still write a complete quality
    report either way."""
    findings = run_quality_gates(hitter_rows, pitcher_rows, game_rows)
    blocking = [f for f in findings if f["check"] in BLOCKING_CHECKS and f["severity"] == "error"]
    if blocking:
        raise QualityGateFailure(blocking)
    return findings
