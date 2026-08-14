from external_projections.models import ExternalProjectionPlayer
from external_projections.projection_merge import match_external_to_independent


def _ext(name, team, player_id_suffix="1", projection=10.0):
    return ExternalProjectionPlayer(
        external_player_id=f"mock-ext-{player_id_suffix}", name=name, team=team, position="OF",
        projection=projection, ceiling=projection * 1.6, floor=projection * 0.4,
        provider_name="MOCK EXTERNAL PROJECTIONS", updated_at="2026-08-11T18:00:00Z", slate_id="s1",
    )


def _independent(player_id, name, team, projection=9.0):
    return {"player_id": player_id, "name": name, "team": team, "projection": projection, "ceiling": projection * 1.5, "floor": projection * 0.5}


def test_exact_name_and_team_match():
    result = match_external_to_independent([_ext("Kyle Schwarber", "PHI")], [_independent("h1", "Kyle Schwarber", "PHI")], "hitter")
    assert len(result.records) == 1
    record = result.records[0]
    assert record.independent_player_id == "h1"
    assert record.external_projection == 10.0
    assert record.independent_projection == 9.0
    assert record.player_type == "hitter"
    assert not result.unmatched_external
    assert not result.unmatched_independent


def test_name_only_match_when_unique_across_teams():
    """Team abbreviation mismatch between providers is a known real-world
    hazard -- a unique name-only match should still resolve rather than
    being reported as unmatched."""
    result = match_external_to_independent([_ext("Kyle Schwarber", "PHIL")], [_independent("h1", "Kyle Schwarber", "PHI")], "hitter")
    assert len(result.records) == 1
    assert result.records[0].independent_player_id == "h1"


def test_ambiguous_when_multiple_name_only_candidates():
    independent = [_independent("h1", "Chris Johnson", "AAA"), _independent("h2", "Chris Johnson", "BBB")]
    result = match_external_to_independent([_ext("Chris Johnson", "CCC")], independent, "hitter")
    assert result.records == []
    assert result.ambiguous_external == ["Chris Johnson"]


def test_unmatched_when_no_candidate_at_all():
    result = match_external_to_independent([_ext("Nobody Here", "ZZZ")], [_independent("h1", "Someone Else", "AAA")], "hitter")
    assert result.records == []
    assert result.unmatched_external == ["Nobody Here"]


def test_unmatched_independent_reported():
    result = match_external_to_independent([], [_independent("h1", "Unpicked Player", "AAA")], "hitter")
    assert result.unmatched_independent == ["Unpicked Player"]


def test_normalization_handles_accents_and_suffixes():
    result = match_external_to_independent([_ext("Ronald Acuna Jr", "ATL")], [_independent("h1", "Ronald Acuña Jr.", "ATL")], "hitter")
    assert len(result.records) == 1
    assert result.records[0].independent_player_id == "h1"


def test_independent_and_external_values_are_never_mutated_by_merge():
    ext = _ext("Kyle Schwarber", "PHI", projection=10.0)
    indep = _independent("h1", "Kyle Schwarber", "PHI", projection=9.0)
    match_external_to_independent([ext], [indep], "hitter")
    assert ext.projection == 10.0
    assert indep["projection"] == 9.0


def test_adjusted_fields_start_none_before_adjustment_engine_runs():
    result = match_external_to_independent([_ext("Kyle Schwarber", "PHI")], [_independent("h1", "Kyle Schwarber", "PHI")], "hitter")
    record = result.records[0]
    assert record.adjusted_projection is None
    assert record.adjustments == []
    assert record.adjustment_reasons == []
