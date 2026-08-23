import json

import pytest

import external_projections.bluecollar_provider as bluecollar_module
from external_projections.base import (
    ProjectionProviderAuthenticationError,
    ProjectionProviderUnavailableError,
)
from external_projections.bluecollar_provider import BlueCollarProvider


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _sample_doc(date="2026-08-13"):
    # BlueCollar's real "date" field format, confirmed via a live
    # authenticated response: "MM_DD_YY" (e.g. "08_23_26"), not ISO.
    bluecollar_date = bluecollar_module._bluecollar_date(date)
    return {
        "slates": [
            {
                "slate": "Main",
                "slate_type": "Classic",
                "date": bluecollar_date,
                "updated": "2026-08-13T18:00:00Z",
                "info": [
                    {"name": "Ronald Acuna Jr.", "team": "ATL", "position": "OF", "opponent": "NYM", "projection": "12.4", "salary": "5400", "value": "2.3"},
                    {"name": "Zac Gallen", "team": "AZ", "position": "P", "opponent": "SD", "projection": 18.2, "salary": 9200, "value": 2.0},
                ],
            },
            {
                "slate": "Turbo",
                "slate_type": "Classic",
                "date": bluecollar_date,
                "updated": "2026-08-13T18:05:00Z",
                "info": [
                    {"name": "Mookie Betts", "team": "LAD", "position": "OF", "opponent": "SF", "projection": "10.1", "salary": "5200", "value": "1.9"},
                ],
            },
        ],
    }


def _provider(tmp_path, monkeypatch, doc, status=200):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request)
        if status != 200:
            import urllib.error
            raise urllib.error.HTTPError(request.full_url, status, "error", {}, None)
        return _FakeResponse(json.dumps(doc).encode("utf-8"))

    monkeypatch.setattr(bluecollar_module.urllib.request, "urlopen", fake_urlopen)
    provider = BlueCollarProvider(api_key="test-key-not-real", cache_root=tmp_path)
    return provider, calls


# ---------------------------------------------------------------------------
# Date format -- confirmed via a real live response (2026-08-23), not
# guessed: BlueCollar returns "MM_DD_YY", not ISO.
# ---------------------------------------------------------------------------


def test_bluecollar_date_converts_iso_to_the_observed_mm_dd_yy_format():
    assert bluecollar_module._bluecollar_date("2026-08-23") == "08_23_26"
    assert bluecollar_module._bluecollar_date("2026-01-05") == "01_05_26"


# ---------------------------------------------------------------------------
# Auth header + endpoint -- exact documented shape.
# ---------------------------------------------------------------------------


def test_sends_the_documented_authorization_header(tmp_path, monkeypatch):
    provider, calls = _provider(tmp_path, monkeypatch, _sample_doc())
    provider.list_slates("2026-08-13")
    assert len(calls) == 1
    assert calls[0].full_url == "https://bluecollardfs.com/api/mlb_draftkings"
    assert calls[0].get_header("Authorization") == "ApiKey test-key-not-real"


def test_never_makes_a_request_when_no_api_key_is_set(tmp_path, monkeypatch):
    # Isolated cache_root -- must not accidentally read a real cached
    # response from an earlier, properly-authenticated fetch elsewhere
    # on disk (data/cache/bluecollar/), which would serve cached data
    # without ever needing the key and defeat this test's purpose.
    # Also delenv BLUECOLLAR_API_KEY -- see the matching comment in
    # test_external_projections_base_and_registry.py for why
    # api_key=None alone isn't sufficient once a real key exists in
    # dashboard/.env.local (another module loads it into os.environ at
    # import time, for the whole pytest session).
    monkeypatch.delenv("BLUECOLLAR_API_KEY", raising=False)
    provider = BlueCollarProvider(api_key=None, cache_root=tmp_path)
    with pytest.raises(Exception):
        provider.list_slates("2026-08-13")


# ---------------------------------------------------------------------------
# Documented HTTP error codes.
# ---------------------------------------------------------------------------


def test_401_raises_authentication_error(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc(), status=401)
    with pytest.raises(ProjectionProviderAuthenticationError, match="401"):
        provider.list_slates("2026-08-13")


def test_403_raises_authentication_error(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc(), status=403)
    with pytest.raises(ProjectionProviderAuthenticationError, match="403"):
        provider.list_slates("2026-08-13")


def test_429_raises_unavailable_error_mentioning_rate_limit(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc(), status=429)
    with pytest.raises(ProjectionProviderUnavailableError, match="429"):
        provider.list_slates("2026-08-13")


def test_unexpected_status_raises_unavailable_error(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc(), status=500)
    with pytest.raises(ProjectionProviderUnavailableError, match="500"):
        provider.list_slates("2026-08-13")


# ---------------------------------------------------------------------------
# list_slates -- normalizes without inventing data.
# ---------------------------------------------------------------------------


def test_list_slates_returns_one_entry_per_documented_slate(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc())
    slates = provider.list_slates("2026-08-13")
    assert len(slates) == 2
    assert {s.slate_name for s in slates} == {"Main", "Turbo"}
    assert all(s.sport == "MLB" for s in slates)


def test_list_slates_player_count_matches_info_length(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc())
    slates = provider.list_slates("2026-08-13")
    main = next(s for s in slates if s.slate_name == "Main")
    turbo = next(s for s in slates if s.slate_name == "Turbo")
    assert main.player_count == 2
    assert turbo.player_count == 1


def test_list_slates_filters_by_date(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc(date="2026-08-13"))
    assert provider.list_slates("2026-08-14") == []


def test_list_slates_returns_empty_for_non_mlb_sport_without_calling_network(tmp_path, monkeypatch):
    provider, calls = _provider(tmp_path, monkeypatch, _sample_doc())
    assert provider.list_slates("2026-08-13", sport="NFL") == []
    assert calls == []


# ---------------------------------------------------------------------------
# get_projections -- exact documented fields, safe coercion, never invents.
# ---------------------------------------------------------------------------


def test_get_projections_returns_documented_fields_only(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc())
    slates = provider.list_slates("2026-08-13")
    main = next(s for s in slates if s.slate_name == "Main")
    players = provider.get_projections(main.slate_id)
    assert len(players) == 2
    acuna = next(p for p in players if p.name == "Ronald Acuna Jr.")
    assert acuna.team == "ATL"
    assert acuna.position == "OF"
    assert acuna.opponent == "NYM"
    assert acuna.projection == 12.4  # coerced from the documented string "12.4"
    assert acuna.salary == 5400
    assert acuna.provider_name == "BlueCollar DFS"
    assert acuna.updated_at == "2026-08-13T18:00:00Z"


def test_get_projections_coerces_numeric_and_string_projection_values_the_same_way(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc())
    slates = provider.list_slates("2026-08-13")
    main = next(s for s in slates if s.slate_name == "Main")
    players = provider.get_projections(main.slate_id)
    gallen = next(p for p in players if p.name == "Zac Gallen")
    assert gallen.projection == 18.2  # was a raw float in the fixture, not a string
    assert gallen.salary == 9200


def test_get_projections_drops_a_player_with_no_parseable_projection_rather_than_inventing_zero(tmp_path, monkeypatch):
    doc = _sample_doc()
    doc["slates"][0]["info"].append({"name": "No Projection Guy", "team": "ATL", "position": "1B", "opponent": "NYM", "projection": None, "salary": "4000", "value": None})
    provider, _ = _provider(tmp_path, monkeypatch, doc)
    slates = provider.list_slates("2026-08-13")
    main = next(s for s in slates if s.slate_name == "Main")
    players = provider.get_projections(main.slate_id)
    assert all(p.name != "No Projection Guy" for p in players)


def test_get_projections_drops_a_record_missing_name_team_or_position(tmp_path, monkeypatch):
    doc = _sample_doc()
    doc["slates"][0]["info"].append({"name": "", "team": "ATL", "position": "1B", "opponent": "NYM", "projection": 5.0, "salary": 4000, "value": 1.0})
    provider, _ = _provider(tmp_path, monkeypatch, doc)
    slates = provider.list_slates("2026-08-13")
    main = next(s for s in slates if s.slate_name == "Main")
    players = provider.get_projections(main.slate_id)
    assert len(players) == 2  # the malformed record never became a third player


def test_get_projections_normalizes_dk_team_abbreviation_mismatches(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc())
    slates = provider.list_slates("2026-08-13")
    main = next(s for s in slates if s.slate_name == "Main")
    players = provider.get_projections(main.slate_id)
    gallen = next(p for p in players if p.name == "Zac Gallen")
    assert gallen.team == "AZ"  # already AZ in fixture; confirms pass-through is stable


def test_get_projections_raises_for_an_unrecognized_slate_id(tmp_path, monkeypatch):
    provider, _ = _provider(tmp_path, monkeypatch, _sample_doc())
    provider.list_slates("2026-08-13")  # populate cache
    with pytest.raises(ProjectionProviderUnavailableError):
        provider.get_projections("not-a-real-slate-id")


# ---------------------------------------------------------------------------
# Caching -- respects the documented 200 requests/day limit.
# ---------------------------------------------------------------------------


def test_second_call_within_the_same_day_does_not_refetch(tmp_path, monkeypatch):
    provider, calls = _provider(tmp_path, monkeypatch, _sample_doc())
    provider.list_slates("2026-08-13")
    provider.list_slates("2026-08-13")
    provider.get_projections(provider.list_slates("2026-08-13")[0].slate_id)
    assert len(calls) == 1
