"""NFL M6B -- targeted tests for historical_nfl/identity_matching.py.
Synthetic fixtures only -- the real-data proof is the M6B final report's
live DraftGroup 151307 x nflverse 2026 roster run."""

from historical_nfl.identity_matching import build_crosswalk_row, build_dst_crosswalk_row, build_roster_indices, resolve_identity
from historical_nfl.identity_models import (
    METHOD_EXCEPTION_TABLE,
    METHOD_EXISTING_CROSSWALK,
    METHOD_NAME_POSITION_CROSS_TEAM,
    METHOD_NAME_TEAM_EXACT,
    REVIEW_AUTO_APPROVED,
    REVIEW_NEEDS_REVIEW,
    STATUS_AMBIGUOUS,
    STATUS_MATCHED,
    STATUS_REVIEW_REQUIRED,
    STATUS_UNMATCHED,
    NflCrosswalkRow,
)


def _roster_row(gsis_id, name, team, position):
    return {"gsis_id": gsis_id, "full_name": name, "team": team, "position": position}


def test_exact_name_team_position_match():
    rows = [_roster_row("00-0001", "Josh Allen", "BUF", "QB")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk1", "d1", "Josh Allen", "BUF", "QB", {}, by_team, by_name)
    assert result.status == STATUS_MATCHED
    assert result.gsis_id == "00-0001"
    assert result.match_method == METHOD_NAME_TEAM_EXACT


def test_suffix_and_punctuation_normalized_via_shared_normalizer():
    rows = [_roster_row("00-0002", "Michael Pittman Jr.", "IND", "WR")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk2", "d2", "Michael Pittman", "IND", "WR", {}, by_team, by_name)
    assert result.status == STATUS_MATCHED
    assert result.gsis_id == "00-0002"


def test_player_traded_between_teams_resolves_via_cross_team_tier():
    rows = [_roster_row("00-0003", "Cooper Rush", "ATL", "QB")]  # nflverse's real current team
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk3", "d3", "Cooper Rush", "DAL", "QB", {}, by_team, by_name)  # DK still shows old team
    assert result.status == STATUS_MATCHED
    assert result.match_method == METHOD_NAME_POSITION_CROSS_TEAM
    assert result.gsis_id == "00-0003"


def test_duplicate_name_different_teams_disambiguated_by_team():
    """Two real, different people sharing a name -- exact team match
    must pick the correct one, never guess."""
    rows = [_roster_row("00-0004", "Josh Allen", "BUF", "QB"), _roster_row("00-0005", "Josh Allen", "MIN", "LB")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk4", "d4", "Josh Allen", "BUF", "QB", {}, by_team, by_name)
    assert result.status == STATUS_MATCHED
    assert result.gsis_id == "00-0004"  # the BUF QB, not the MIN LB


def test_ambiguous_when_multiple_compatible_candidates_same_team():
    rows = [_roster_row("00-0006", "John Smith", "PHI", "WR"), _roster_row("00-0007", "John Smith", "PHI", "WR")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk5", "d5", "John Smith", "PHI", "WR", {}, by_team, by_name)
    assert result.status == STATUS_AMBIGUOUS
    assert set(result.candidate_gsis_ids) == {"00-0006", "00-0007"}


def test_ambiguous_cross_team_when_multiple_compatible_candidates_elsewhere():
    rows = [_roster_row("00-0008", "John Smith", "SEA", "WR"), _roster_row("00-0009", "John Smith", "DET", "WR")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk6", "d6", "John Smith", "PHI", "WR", {}, by_team, by_name)
    assert result.status == STATUS_AMBIGUOUS


def test_review_required_when_name_team_match_has_incompatible_position():
    """Real audit finding: usually a different real person sharing name
    and team -- never silently accepted, never silently dropped."""
    rows = [_roster_row("00-0010", "Connor Heyward", "LV", "TE")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk7", "d7", "Connor Heyward", "LV", "RB", {}, by_team, by_name)
    assert result.status == STATUS_REVIEW_REQUIRED
    assert result.candidate_gsis_ids == ["00-0010"]
    assert result.gsis_id is None  # never persisted as a real match


def test_unmatched_when_no_candidate_anywhere():
    rows = [_roster_row("00-0011", "Someone Else", "PHI", "WR")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk8", "d8", "Nobody Here", "PHI", "WR", {}, by_team, by_name)
    assert result.status == STATUS_UNMATCHED
    assert result.gsis_id is None


def test_missing_gsis_id_roster_row_never_used_as_a_candidate():
    rows = [{"gsis_id": "", "full_name": "No GSIS Guy", "team": "PHI", "position": "WR"}]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk9", "d9", "No GSIS Guy", "PHI", "WR", {}, by_team, by_name)
    assert result.status == STATUS_UNMATCHED


def test_existing_approved_crosswalk_reused_without_rematching():
    existing_row = NflCrosswalkRow(
        canonical_player_id="gsis:00-0099", draftkings_player_id="dk10", gsis_id="00-0099",
        name="Someone", team="PHI", position="WR", match_method="name_team_exact", match_confidence=1.0,
        review_status=REVIEW_AUTO_APPROVED, created_at="t0", updated_at="t0",
    )
    # Deliberately empty roster indices -- if Tier 1 didn't short-circuit, this would UNMATCH.
    result = resolve_identity("dk10", "d10", "Someone", "PHI", "WR", {"dk10": existing_row}, {}, {})
    assert result.status == STATUS_MATCHED
    assert result.match_method == METHOD_EXISTING_CROSSWALK
    assert result.gsis_id == "00-0099"


def test_needs_review_existing_row_is_not_treated_as_approved():
    existing_row = NflCrosswalkRow(
        canonical_player_id="dk:dk11", draftkings_player_id="dk11", gsis_id=None,
        name="Ambi Guy", team="PHI", position="WR", review_status=REVIEW_NEEDS_REVIEW,
        created_at="t0", updated_at="t0",
    )
    rows = [_roster_row("00-0012", "Ambi Guy", "PHI", "WR")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk11", "d11", "Ambi Guy", "PHI", "WR", {"dk11": existing_row}, by_team, by_name)
    assert result.status == STATUS_MATCHED
    assert result.match_method == METHOD_NAME_TEAM_EXACT  # re-resolved, not blindly reused


def test_exception_table_resolves_verified_nickname_case():
    rows = [_roster_row("00-0013", "Marquise Brown", "PHI", "WR")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk12", "d12", "Hollywood Brown", "PHI", "WR", {}, by_team, by_name)
    assert result.status == STATUS_MATCHED
    assert result.match_method == METHOD_EXCEPTION_TABLE
    assert result.gsis_id == "00-0013"


def test_no_fuzzy_acceptance_of_a_materially_different_name():
    rows = [_roster_row("00-0014", "Jonathan Taylor", "IND", "RB")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk13", "d13", "Jon Taylor Jr Smith", "IND", "RB", {}, by_team, by_name)
    assert result.status == STATUS_UNMATCHED  # normalize_name would not equate these -- no fuzzy fallback exists


def test_build_crosswalk_row_mints_gsis_prefixed_canonical_id_when_matched():
    rows = [_roster_row("00-0015", "New Player", "PHI", "WR")]
    by_team, by_name = build_roster_indices(rows)
    result = resolve_identity("dk14", "d14", "New Player", "PHI", "WR", {}, by_team, by_name)
    row = build_crosswalk_row(result, existing=None)
    assert row.canonical_player_id == "gsis:00-0015"
    assert row.review_status == REVIEW_AUTO_APPROVED


def test_build_crosswalk_row_mints_dk_prefixed_canonical_id_when_unmatched():
    result = resolve_identity("dk15", "d15", "Totally New Rookie", "PHI", "WR", {}, {}, {})
    row = build_crosswalk_row(result, existing=None)
    assert row.canonical_player_id == "dk:dk15"
    assert row.gsis_id is None


def test_canonical_id_never_changes_once_minted_even_after_later_gsis_match():
    """Phase 12: the canonical ID is immutable once established -- a
    later run finding a real GSIS for a previously-dk:-anchored player
    updates gsis_id but must NEVER change canonical_player_id."""
    first_result = resolve_identity("dk16", "d16", "Future Rookie", "PHI", "WR", {}, {}, {})
    first_row = build_crosswalk_row(first_result, existing=None)
    assert first_row.canonical_player_id == "dk:dk16"

    rows = [_roster_row("00-0016", "Future Rookie", "PHI", "WR")]
    by_team, by_name = build_roster_indices(rows)
    second_result = resolve_identity("dk16", "d16", "Future Rookie", "PHI", "WR", {}, by_team, by_name)
    second_row = build_crosswalk_row(second_result, existing=first_row)
    assert second_row.canonical_player_id == "dk:dk16"  # unchanged
    assert second_row.gsis_id == "00-0016"  # but the mapping itself is now filled in


def test_ambiguous_and_review_required_rows_marked_needs_review():
    ambiguous = resolve_identity("dk17", "d17", "John Smith", "PHI", "WR", {}, *build_roster_indices(
        [_roster_row("00-0017", "John Smith", "PHI", "WR"), _roster_row("00-0018", "John Smith", "PHI", "WR")]
    ))
    row = build_crosswalk_row(ambiguous, existing=None)
    assert row.review_status == REVIEW_NEEDS_REVIEW
    assert row.gsis_id is None


def test_dst_crosswalk_row_uses_team_identity_not_gsis():
    row = build_dst_crosswalk_row("dst1", "Eagles", "PHI")
    assert row.canonical_player_id == "dst:PHI"
    assert row.is_team_entity is True
    assert row.gsis_id is None
    assert row.position == "DST"


def test_dst_crosswalk_row_canonical_id_stable_across_reruns():
    first = build_dst_crosswalk_row("dst1", "Eagles", "PHI")
    second = build_dst_crosswalk_row("dst1", "Eagles", "PHI", existing=first)
    assert second.canonical_player_id == first.canonical_player_id
