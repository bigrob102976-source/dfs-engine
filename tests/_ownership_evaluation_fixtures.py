"""Shared synthetic ownership snapshot / actual-ownership document
builders for evaluation/ownership_evaluator.py and actual-ownership
ingestion tests. Not a test module itself (no test_ prefix).
"""


def _snapshot_player(dk_id, name, team, player_type, positions, salary, projected_ownership, tier,
                      tags=None, leverage=0.0, chalk=50.0, mlb_id=None):
    return {
        "dk_player_id": dk_id, "mlb_player_id": mlb_id or dk_id, "name": name, "team": team,
        "player_type": player_type, "dk_positions": positions, "salary": salary,
        "projected_ownership": projected_ownership, "ownership_tier": tier,
        "tags": tags or [], "leverage_score": leverage, "chalk_score": chalk,
    }


def sample_snapshot():
    """2 pitchers + 6 hitters with clean, hand-computable numbers."""
    players = [
        _snapshot_player("p1", "Pitcher One", "TOR", "pitcher", ["P"], 9500, 60.0, "very_high", tags=["elite_leverage"]),
        _snapshot_player("p2", "Pitcher Two", "PIT", "pitcher", ["P"], 6500, 15.0, "medium"),

        _snapshot_player("h1", "Hitter One", "PHI", "hitter", ["C"], 2500, 80.0, "very_high", tags=["chalk"]),
        _snapshot_player("h2", "Hitter Two", "PHI", "hitter", ["1B"], 3200, 60.0, "very_high"),
        _snapshot_player("h3", "Hitter Three", "NYY", "hitter", ["2B"], 4200, 40.0, "very_high"),
        _snapshot_player("h4", "Hitter Four", "NYY", "hitter", ["3B", "OF"], 5200, 20.0, "high", tags=["positive_leverage"]),
        _snapshot_player("h5", "Hitter Five", "BAL", "hitter", ["SS"], 3600, 10.0, "medium"),
        _snapshot_player("h6", "Hitter Six", "BAL", "hitter", ["OF"], 2000, 5.0, "low", tags=["low_owned_ceiling"]),
    ]
    return {
        "slate_date": "2026-08-11", "model_version": "0.1.0", "generated_at": "2026-08-11T18:00:00+00:00",
        "players": players,
        "team_popularity": {
            "PHI": {"aggregate_projected_ownership": 140.0},
            "NYY": {"aggregate_projected_ownership": 60.0},
            "BAL": {"aggregate_projected_ownership": 15.0},
        },
    }


def _actual_record(dk_id, name, team, player_type, actual_ownership, match_status="matched", mlb_id=None):
    return {
        "dk_player_id": dk_id, "mlb_player_id": mlb_id or dk_id, "name": name, "team": team,
        "player_type": player_type, "actual_ownership": actual_ownership,
        "contest_id": "999", "contest_name": None, "contest_size": 8,
        "source_file": "contest-standings-999.csv", "match_status": match_status, "match_confidence": "exact_dk_id",
    }


def sample_actual_document():
    records = [
        _actual_record("p1", "Pitcher One", "TOR", "pitcher", 50.0),
        _actual_record("p2", "Pitcher Two", "PIT", "pitcher", 25.0),
        _actual_record("h1", "Hitter One", "PHI", "hitter", 70.0),
        _actual_record("h2", "Hitter Two", "PHI", "hitter", 65.0),
        _actual_record("h3", "Hitter Three", "NYY", "hitter", 35.0),
        _actual_record("h4", "Hitter Four", "NYY", "hitter", 30.0),
        _actual_record("h5", "Hitter Five", "BAL", "hitter", 8.0),
        _actual_record("h6", "Hitter Six", "BAL", "hitter", 12.0),
    ]
    return {
        "slate_date": "2026-08-11",
        "contest": {
            "contest_id": "999", "contest_name": None, "contest_type": None, "entries": 8, "max_entries": None,
            "results_filename": "contest-standings-999.csv", "source_file_hash": "deadbeef",
            "retrieved_at_utc": "2026-08-12T04:00:00+00:00",
        },
        "format_used": "direct_ownership_table",
        "import_warnings": [],
        "record_count": len(records),
        "matched_count": len(records),
        "unmatched_count": 0,
        "ambiguous_count": 0,
        "match_rate": 1.0,
        "records": records,
    }
