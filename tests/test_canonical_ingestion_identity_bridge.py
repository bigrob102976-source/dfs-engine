"""M2E / M2M -- MLB identity bridge tests."""

from canonical.identity_models import METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING
from canonical.models import IDENTITY_STATUS_RESOLVED, IDENTITY_STATUS_REVIEW_REQUIRED, IDENTITY_STATUS_UNRESOLVED
from canonical_ingestion.identity_bridge import build_name_team_index, resolve_dk_player
from dfs.name_normalization import normalize_name
from dfs.providers.models import ProviderPlayer
from player_identity.models import CanonicalIdentity


def _dk_player(name="Shohei Ohtani", team="LAD", external_id="999"):
    return ProviderPlayer(
        external_player_id=external_id, name=name, team=team, opponent="SF", game="SF@LAD",
        salary=6200, position_eligibility=["OF", "UTIL"], slate_id="dkunofficial-1", slate_name="Main",
        start_time="2026-08-31T23:05:00Z", source="draftkings_unofficial", retrieved_at="2026-08-31T20:00:00Z",
    )


def _identity(mlb_id="660271", name="Shohei Ohtani", team="LAD", active=True):
    return CanonicalIdentity(mlb_player_id=mlb_id, canonical_name=name, normalized_name=normalize_name(name), current_team=team, active=active)


def test_known_mlb_identity_resolves_and_attaches_both_external_ids():
    crosswalk = {"660271": _identity()}
    index = build_name_team_index(crosswalk)
    result = resolve_dk_player(_dk_player(), index)

    assert result.identity_status == IDENTITY_STATUS_RESOLVED
    assert result.match_method == METHOD_EXACT_DETERMINISTIC_SOURCE_MAPPING
    hints = {h.provider: h.external_id for h in result.external_id_hints}
    assert hints["draftkings"] == "999"
    assert hints["mlbam"] == "660271"


def test_unknown_player_remains_servable_unresolved():
    index = build_name_team_index({})
    result = resolve_dk_player(_dk_player(name="Brand New Rookie", team="LAD"), index)
    assert result.identity_status == IDENTITY_STATUS_UNRESOLVED
    # Still gets a DK external-id hint -- the row itself is servable.
    assert result.external_id_hints[0].provider == "draftkings"
    assert result.reason is not None


def test_ambiguous_candidates_are_review_required_not_guessed():
    # A genuine real-world edge case: two distinct MLB players share the
    # exact same name and team in the crosswalk.
    crosswalk = {
        "1": _identity(mlb_id="1", name="Luis Garcia", team="LAD"),
        "2": _identity(mlb_id="2", name="Luis Garcia", team="LAD"),
    }
    index = build_name_team_index(crosswalk)
    result = resolve_dk_player(_dk_player(name="Luis Garcia", team="LAD"), index)
    assert result.identity_status == IDENTITY_STATUS_REVIEW_REQUIRED
    assert sorted(result.candidate_mlb_player_ids) == ["1", "2"]
    assert result.match_method is None  # never auto-picked one of the candidates


def test_no_fuzzy_auto_merge_slightly_different_name_stays_unresolved():
    # "Shohei Otani" (missing an 'h') must NOT match "Shohei Ohtani" --
    # normalize_name only fixes genuine formatting differences, never
    # similarity/edit-distance.
    crosswalk = {"660271": _identity()}
    index = build_name_team_index(crosswalk)
    result = resolve_dk_player(_dk_player(name="Shohei Otani", team="LAD"), index)
    assert result.identity_status == IDENTITY_STATUS_UNRESOLVED


def test_no_fuzzy_auto_merge_different_team_stays_unresolved():
    # Same exact name, different team (e.g. a trade not yet reflected in
    # the crosswalk) -- must not guess it's the same player.
    crosswalk = {"660271": _identity(team="LAD")}
    index = build_name_team_index(crosswalk)
    result = resolve_dk_player(_dk_player(name="Shohei Ohtani", team="NYY"), index)
    assert result.identity_status == IDENTITY_STATUS_UNRESOLVED


def test_inactive_identity_excluded_from_index():
    crosswalk = {"660271": _identity(active=False)}
    index = build_name_team_index(crosswalk)
    assert index == {}


def test_dk_id_attached_correctly_mlbam_only_when_known():
    index = build_name_team_index({})
    result = resolve_dk_player(_dk_player(external_id="12345"), index)
    providers = [h.provider for h in result.external_id_hints]
    assert providers == ["draftkings"]  # no mlbam hint when unresolved
    assert result.external_id_hints[0].external_id == "12345"
