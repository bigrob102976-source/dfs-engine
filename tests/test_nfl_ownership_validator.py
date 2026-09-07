"""NFL M12 -- targeted tests for nfl/ownership_validator.py: independent
re-derivation of bounds/sum checks, never trusting the model's own
normalization_report (mirrors ownership/validator.py's discipline)."""

from nfl.ownership_model import build_nfl_ownership_projections
from nfl.ownership_models import NflOwnershipRecord
from nfl.ownership_validator import validate_ownership
from tests.test_nfl_ownership_model import _realistic_slate

DG_ID = 151307
DATE = "2026-09-13"


def _record(pid, position, ownership, tier="medium"):
    return NflOwnershipRecord(
        sport="NFL", draft_group_id=DG_ID, slate_date=DATE, draftkings_player_id=pid, canonical_player_id=pid,
        name=f"Player {pid}", position=position, team="BUF", opponent="HOU", ownership_projection=ownership,
        ownership_rank=1, source="BIG_MONEY_NATIVE_OWNERSHIP_V1", source_provenance="TEST_PROVENANCE",
        method="deterministic_estimator", model_version="nfl_ownership_v1", generated_at="2026-09-13T12:00:00Z",
        ownership_tier=tier,
    )


def test_validator_passes_on_real_model_output():
    players = _realistic_slate()
    records, _ = build_nfl_ownership_projections(players, DG_ID, DATE, "TEST_PROVENANCE", "2026-09-13T12:00:00Z")
    result = validate_ownership(len(players), records)
    assert result.passed is True
    assert result.players_with_ownership == len(players)
    assert result.players_missing_ownership == 0


def test_validator_catches_out_of_bounds_ownership():
    records = [_record("1", "QB", 150.0)]
    result = validate_ownership(1, records)
    assert result.passed is False
    assert any("out of [0, 100] bounds" in f.message for f in result.findings)


def test_validator_catches_negative_ownership():
    records = [_record("1", "QB", -5.0)]
    result = validate_ownership(1, records)
    assert result.passed is False


def test_validator_catches_qb_sum_far_below_expected():
    """A single QB projected at only 10% ownership is a real, plausible
    normalization bug symptom (QB slot mass should be ~100%)."""
    records = [_record("1", "QB", 10.0)]
    result = validate_ownership(1, records)
    assert result.passed is False
    assert any("QB ownership sum" in f.message for f in result.findings)


def test_validator_catches_duplicate_records():
    records = [_record("1", "QB", 60.0), _record("1", "QB", 40.0)]
    result = validate_ownership(1, records)
    assert result.passed is False
    assert any("duplicate" in f.message.lower() for f in result.findings)


def test_validator_catches_unknown_tier():
    records = [_record("1", "QB", 90.0, tier="nonsense_tier")]
    result = validate_ownership(1, records)
    assert result.passed is False
    assert any("unknown ownership_tier" in f.message.lower() for f in result.findings)


def test_validator_missing_ownership_counted_honestly():
    """total_pool_players can legitimately exceed len(records) -- players
    with no usable projection never get a record at all (see
    nfl/ownership_merge.py); the validator must report that gap, never
    hide it."""
    records = [_record("1", "QB", 90.0)]
    result = validate_ownership(4, records)
    assert result.players_with_ownership == 1
    assert result.players_missing_ownership == 3
