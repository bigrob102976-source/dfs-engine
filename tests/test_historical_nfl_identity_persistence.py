"""NFL M6B -- targeted tests for historical_nfl/identity_persistence.py."""

import pytest

from historical_nfl.identity_models import REVIEW_AUTO_APPROVED, REVIEW_NEEDS_REVIEW, CrosswalkConflictError, NflCrosswalkRow
from historical_nfl.identity_persistence import load_crosswalk, merge_crosswalk, save_crosswalk


def _row(dk_id, gsis_id, review_status=REVIEW_AUTO_APPROVED, name="Player"):
    return NflCrosswalkRow(
        canonical_player_id=f"gsis:{gsis_id}" if gsis_id else f"dk:{dk_id}", draftkings_player_id=dk_id,
        gsis_id=gsis_id, name=name, team="PHI", position="WR", match_method="name_team_exact",
        match_confidence=1.0, review_status=review_status, created_at="2026-08-31T00:00:00+00:00", updated_at="2026-08-31T00:00:00+00:00",
    )


def test_save_and_load_round_trip(tmp_path):
    row = _row("dk1", "00-0001")
    save_crosswalk({"dk1": row}, "2026-08-31T00:00:00+00:00", output_root=tmp_path)
    loaded = load_crosswalk(output_root=tmp_path)
    assert loaded["dk1"].gsis_id == "00-0001"


def test_load_returns_empty_dict_when_nothing_saved(tmp_path):
    assert load_crosswalk(output_root=tmp_path) == {}


def test_save_never_overwrites_a_prior_version(tmp_path):
    row = _row("dk1", "00-0001")
    path1 = save_crosswalk({"dk1": row}, "2026-08-31T00:00:00.000000+00:00", output_root=tmp_path)
    path2 = save_crosswalk({"dk1": row}, "2026-08-31T00:00:00.000001+00:00", output_root=tmp_path)
    assert path1 != path2
    assert path1.exists() and path2.exists()


def test_merge_reaffirms_identical_mapping_as_no_op():
    existing = {"dk1": _row("dk1", "00-0001")}
    same = _row("dk1", "00-0001")
    merged = merge_crosswalk(existing, [same])
    assert merged["dk1"].gsis_id == "00-0001"
    assert len(merged) == 1


def test_merge_adds_a_brand_new_player():
    existing = {"dk1": _row("dk1", "00-0001")}
    new_row = _row("dk2", "00-0002")
    merged = merge_crosswalk(existing, [new_row])
    assert set(merged.keys()) == {"dk1", "dk2"}


def test_merge_raises_on_conflicting_approved_mapping():
    existing = {"dk1": _row("dk1", "00-0001")}
    conflicting = _row("dk1", "00-0002")  # same DK id, different GSIS
    with pytest.raises(CrosswalkConflictError):
        merge_crosswalk(existing, [conflicting])


def test_merge_freely_replaces_a_needs_review_row():
    existing = {"dk1": _row("dk1", None, review_status=REVIEW_NEEDS_REVIEW)}
    resolved = _row("dk1", "00-0001")
    merged = merge_crosswalk(existing, [resolved])
    assert merged["dk1"].gsis_id == "00-0001"


def test_merge_conflict_never_mutates_the_existing_dict_in_place():
    existing = {"dk1": _row("dk1", "00-0001")}
    conflicting = _row("dk1", "00-0002")
    try:
        merge_crosswalk(existing, [conflicting])
    except CrosswalkConflictError:
        pass
    assert existing["dk1"].gsis_id == "00-0001"  # untouched
