from evaluation.actual_ownership_models import ContestMetadata
from evaluation.actual_ownership_parser import RawActualOwnershipRow
from evaluation.actual_ownership_resolver import resolve_actual_ownership


def _contest(entries=10):
    return ContestMetadata(
        contest_id="1", contest_name=None, contest_type=None, entries=entries, max_entries=None,
        results_filename="f.csv", source_file_hash="abc", retrieved_at_utc="2026-08-11T18:00:00+00:00",
    )


def _snapshot_players():
    return [
        {"dk_player_id": "d1", "mlb_player_id": "m1", "name": "Dylan Cease", "team": "TOR", "player_type": "pitcher"},
        {"dk_player_id": "d2", "mlb_player_id": "m2", "name": "Paul Skenes", "team": "PIT", "player_type": "pitcher"},
        {"dk_player_id": "d3", "mlb_player_id": "m3", "name": "Aaron Judge", "team": "NYY", "player_type": "hitter"},
    ]


def test_exact_dk_id_match():
    raw = [RawActualOwnershipRow(name="Dylan Cease", actual_ownership=63.4, dk_player_id="d1")]
    records = resolve_actual_ownership(raw, _snapshot_players(), _contest(), "f.csv")
    assert records[0].match_status == "matched"
    assert records[0].match_confidence == "exact_dk_id"
    assert records[0].dk_player_id == "d1"
    assert records[0].team == "TOR"


def test_crosswalk_fallback_match():
    raw = [RawActualOwnershipRow(name="Some Alias", actual_ownership=10.0, dk_player_id="alias_id")]
    crosswalk = {"alias_id": "m2"}
    records = resolve_actual_ownership(raw, _snapshot_players(), _contest(), "f.csv", crosswalk=crosswalk)
    assert records[0].match_status == "matched"
    assert records[0].match_confidence == "crosswalk"
    assert records[0].dk_player_id == "d2"


def test_name_unique_match_when_no_dk_id():
    raw = [RawActualOwnershipRow(name="Aaron Judge", actual_ownership=45.0)]
    records = resolve_actual_ownership(raw, _snapshot_players(), _contest(), "f.csv")
    assert records[0].match_status == "matched"
    assert records[0].match_confidence == "name_unique_in_snapshot"
    assert records[0].dk_player_id == "d3"


def test_name_normalization_handles_accents_and_suffixes():
    players = [{"dk_player_id": "d4", "mlb_player_id": "m4", "name": "Luis García Jr.", "team": "NYY", "player_type": "hitter"}]
    raw = [RawActualOwnershipRow(name="Luis Garcia Jr", actual_ownership=20.0)]
    records = resolve_actual_ownership(raw, players, _contest(), "f.csv")
    assert records[0].match_status == "matched"


def test_ambiguous_when_two_snapshot_players_share_normalized_name():
    players = _snapshot_players() + [
        {"dk_player_id": "d5", "mlb_player_id": "m5", "name": "Aaron Judge", "team": "BOS", "player_type": "hitter"}
    ]
    raw = [RawActualOwnershipRow(name="Aaron Judge", actual_ownership=30.0)]
    records = resolve_actual_ownership(raw, players, _contest(), "f.csv")
    assert records[0].match_status == "ambiguous"
    assert records[0].dk_player_id is None


def test_unmatched_never_guessed():
    raw = [RawActualOwnershipRow(name="Nobody On This Slate", actual_ownership=2.0)]
    records = resolve_actual_ownership(raw, _snapshot_players(), _contest(), "f.csv")
    assert records[0].match_status == "unmatched"
    assert records[0].dk_player_id is None
    assert records[0].team is None
    # actual_ownership is still preserved -- never silently dropped.
    assert records[0].actual_ownership == 2.0


def test_contest_fields_propagated_to_every_record():
    contest = _contest(entries=42)
    raw = [RawActualOwnershipRow(name="Dylan Cease", actual_ownership=63.4, dk_player_id="d1")]
    records = resolve_actual_ownership(raw, _snapshot_players(), contest, "f.csv")
    assert records[0].contest_id == "1"
    assert records[0].contest_size == 42
    assert records[0].source_file == "f.csv"
