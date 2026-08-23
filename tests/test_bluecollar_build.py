from pathlib import Path

import pytest

from bluecollar import build as bluecollar_build_module
from bluecollar.build import (
    STATUS_API_ERROR,
    STATUS_NOT_CONFIGURED,
    STATUS_NO_RESEARCH,
    STATUS_READY,
    STATUS_SLATE_MATCH_FAILED,
    build_bluecollar_snapshot,
)
from external_projections.bluecollar_provider import BlueCollarProvider


@pytest.fixture(autouse=True)
def _no_identity_crosswalk_by_default(monkeypatch):
    # Canonical MLB Player Identity Foundation: build_bluecollar_snapshot()
    # widens identity matching using the on-disk rolling crosswalk by
    # default (player_identity/persistence.py's DEFAULT_CROSSWALK_PATH).
    # Isolate every test in this file from whatever crosswalk happens to
    # exist on this machine -- mirrors tests/test_pool_builder.py's own
    # identical fixture, added for the identical reason.
    monkeypatch.setattr(bluecollar_build_module, "load_crosswalk", lambda *a, **k: {})


def _write_research_package(root: Path, date: str):
    import json
    folder = root / date
    folder.mkdir(parents=True)
    (folder / "games.json").write_text("[]", encoding="utf-8")
    (folder / "teams.json").write_text("[]", encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps([
        {"player_id": "p1", "name": "Zac Gallen", "team_id": "1", "team_abbr": "AZ",
         "opponent_team_id": "2", "opponent_abbr": "SD", "game_id": "g1", "status": "probable"},
    ]), encoding="utf-8")
    (folder / "batters.json").write_text("[]", encoding="utf-8")


def _dk_slate(slate_id="dk-main", game_count=1, player_count=2, start_time=None, slate_name="Featured"):
    return {"slate_id": slate_id, "game_count": game_count, "player_count": player_count, "start_time": start_time, "slate_name": slate_name}


class _FakeProvider:
    """Stands in for BlueCollarProvider without touching urllib at all --
    tests bluecollar/build.py's own orchestration logic in isolation."""

    def __init__(self, configured=True, slates=None, players=None, list_slates_error=None, get_projections_error=None):
        self._configured = configured
        self._slates = slates or []
        self._players = players or []
        self._list_slates_error = list_slates_error
        self._get_projections_error = get_projections_error

    def is_configured(self):
        return self._configured

    def list_slates(self, date):
        if self._list_slates_error:
            raise self._list_slates_error
        return self._slates

    def get_projections(self, slate_id):
        if self._get_projections_error:
            raise self._get_projections_error
        return self._players


def test_not_configured_returns_status_without_calling_network():
    provider = _FakeProvider(configured=False)
    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", provider=provider)
    assert result["status"] == STATUS_NOT_CONFIGURED
    assert result["snapshot"] is None


def test_api_error_during_list_slates_returns_status_not_raises():
    from external_projections.base import ProjectionProviderUnavailableError
    provider = _FakeProvider(configured=True, list_slates_error=ProjectionProviderUnavailableError("HTTP 500"))
    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", provider=provider)
    assert result["status"] == STATUS_API_ERROR
    assert result["snapshot"] is None
    assert "500" in result["error"]


def test_slate_match_ambiguous_reports_status_never_raises():
    from external_projections.models import ExternalSlateInfo
    slates = [
        ExternalSlateInfo(slate_id="bc-x", slate_name="2:10PM ET (Turbo) 4 Games", sport="MLB", site="draftkings", player_count=380),
        ExternalSlateInfo(slate_id="bc-y", slate_name="2:11PM ET (Snake) 4 Games", sport="MLB", site="draftkings", player_count=381),
    ]
    provider = _FakeProvider(configured=True, slates=slates)
    result = build_bluecollar_snapshot(_dk_slate(game_count=4, player_count=380, start_time=None, slate_name=None), "2026-08-23", provider=provider)
    assert result["status"] == STATUS_SLATE_MATCH_FAILED
    assert "BLUECOLLAR_SLATE_MATCH_AMBIGUOUS" in result["error"]


def test_no_research_package_returns_status_not_error(tmp_path):
    from external_projections.models import ExternalSlateInfo
    slates = [ExternalSlateInfo(slate_id="bc-main", slate_name="1:35PM ET Main 1 Games", sport="MLB", site="draftkings", player_count=2)]
    provider = _FakeProvider(configured=True, slates=slates)
    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", research_output_root=str(tmp_path / "no_such_root"), provider=provider)
    assert result["status"] == STATUS_NO_RESEARCH
    assert result["snapshot"] is None


def test_ready_builds_snapshot_and_matches_players(tmp_path):
    from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo
    _write_research_package(tmp_path, "2026-08-23")
    slates = [ExternalSlateInfo(slate_id="bc-main", slate_name="1:35PM ET Main 1 Games", sport="MLB", site="draftkings", player_count=1)]
    players = [ExternalProjectionPlayer(
        external_player_id="zac-gallen|az|p", name="Zac Gallen", team="AZ", position="P", projection=18.2,
        provider_name="BlueCollar DFS", updated_at="12:00:00 ET", slate_id="bc-main", opponent="SD", salary=9200,
    )]
    provider = _FakeProvider(configured=True, slates=slates, players=players)

    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", research_output_root=str(tmp_path), provider=provider)
    assert result["status"] == STATUS_READY
    snap = result["snapshot"]
    assert snap.bluecollar_slate_id == "bc-main"
    assert snap.bluecollar_updated == "12:00:00 ET"
    assert snap.player_count == 1
    assert snap.matched_count == 1
    assert snap.usable_projection_count == 1
    assert snap.players[0].mlb_player_id == "p1"
    assert snap.players[0].usable_projection == 18.2


# ---------------------------------------------------------------------------
# Canonical MLB Player Identity Foundation -- a BlueCollar-projected
# hitter resolves an mlb_player_id even though their team's lineup
# hasn't posted (batters.json empty), via the roster-derived crosswalk.
# ---------------------------------------------------------------------------


def test_bluecollar_hitter_resolves_before_lineup_posts_via_identity_crosswalk(tmp_path, monkeypatch):
    import json

    from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo
    from player_identity.models import CanonicalIdentity

    folder = tmp_path / "2026-08-23"
    folder.mkdir(parents=True)
    (folder / "games.json").write_text(json.dumps([{
        "game_id": "g1", "home_team_abbr": "AZ", "away_team_abbr": "SD",
    }]), encoding="utf-8")
    (folder / "teams.json").write_text(json.dumps([
        {"team_id": "9", "abbreviation": "AZ", "name": "Arizona Diamondbacks"},
        {"team_id": "35", "abbreviation": "SD", "name": "San Diego Padres"},
    ]), encoding="utf-8")
    (folder / "pitchers.json").write_text("[]", encoding="utf-8")
    (folder / "batters.json").write_text("[]", encoding="utf-8")  # lineup NOT posted

    monkeypatch.setattr(bluecollar_build_module, "load_crosswalk", lambda *a, **k: {
        "h1": CanonicalIdentity(
            mlb_player_id="h1", canonical_name="Early Hitter", normalized_name="early hitter",
            current_team="AZ", player_type="hitter", last_verified_at="2026-08-23T18:00:00+00:00",
        ),
    })

    slates = [ExternalSlateInfo(slate_id="bc-main", slate_name="1:35PM ET Main 1 Games", sport="MLB", site="draftkings", player_count=1)]
    players = [ExternalProjectionPlayer(
        external_player_id="early-hitter|az|of", name="Early Hitter", team="AZ", position="OF", projection=11.4,
        provider_name="BlueCollar DFS", updated_at="12:00:00 ET", slate_id="bc-main", opponent="SD", salary=4200,
    )]
    provider = _FakeProvider(configured=True, slates=slates, players=players)

    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", research_output_root=str(tmp_path), provider=provider)

    assert result["status"] == STATUS_READY
    snap = result["snapshot"]
    assert snap.players[0].mlb_player_id == "h1"
    assert snap.players[0].match_status == "matched"
    assert snap.players[0].usable_projection == 11.4


# ---------------------------------------------------------------------------
# ZERO-VALUE HANDLING -- the explicit live finding this milestone requires.
# ---------------------------------------------------------------------------


def test_zero_projection_treated_as_not_available(tmp_path):
    from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo
    _write_research_package(tmp_path, "2026-08-23")
    slates = [ExternalSlateInfo(slate_id="bc-main", slate_name="1:35PM ET Main 1 Games", sport="MLB", site="draftkings", player_count=1)]
    players = [ExternalProjectionPlayer(
        external_player_id="zac-gallen|az|p", name="Zac Gallen", team="AZ", position="P", projection=0.0,
        provider_name="BlueCollar DFS", updated_at="12:00:00 ET", slate_id="bc-main",
    )]
    provider = _FakeProvider(configured=True, slates=slates, players=players)

    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", research_output_root=str(tmp_path), provider=provider)
    snap = result["snapshot"]
    assert snap.players[0].raw_projection == 0.0  # preserved for transparency
    assert snap.players[0].usable_projection is None  # never a fabricated real zero
    assert snap.usable_projection_count == 0


def test_positive_projection_accepted_as_usable(tmp_path):
    from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo
    _write_research_package(tmp_path, "2026-08-23")
    slates = [ExternalSlateInfo(slate_id="bc-main", slate_name="1:35PM ET Main 1 Games", sport="MLB", site="draftkings", player_count=1)]
    players = [ExternalProjectionPlayer(
        external_player_id="zac-gallen|az|p", name="Zac Gallen", team="AZ", position="P", projection=0.1,
        provider_name="BlueCollar DFS", updated_at="12:00:00 ET", slate_id="bc-main",
    )]
    provider = _FakeProvider(configured=True, slates=slates, players=players)

    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", research_output_root=str(tmp_path), provider=provider)
    snap = result["snapshot"]
    assert snap.players[0].usable_projection == 0.1
    assert snap.usable_projection_count == 1


def test_negative_projection_also_treated_as_not_available(tmp_path):
    from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo
    _write_research_package(tmp_path, "2026-08-23")
    slates = [ExternalSlateInfo(slate_id="bc-main", slate_name="1:35PM ET Main 1 Games", sport="MLB", site="draftkings", player_count=1)]
    players = [ExternalProjectionPlayer(
        external_player_id="zac-gallen|az|p", name="Zac Gallen", team="AZ", position="P", projection=-1.0,
        provider_name="BlueCollar DFS", updated_at="12:00:00 ET", slate_id="bc-main",
    )]
    provider = _FakeProvider(configured=True, slates=slates, players=players)
    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", research_output_root=str(tmp_path), provider=provider)
    assert result["snapshot"].players[0].usable_projection is None


def test_get_projections_failure_is_non_blocking(tmp_path):
    from external_projections.base import ProjectionProviderUnavailableError
    from external_projections.models import ExternalSlateInfo
    _write_research_package(tmp_path, "2026-08-23")
    slates = [ExternalSlateInfo(slate_id="bc-main", slate_name="1:35PM ET Main 1 Games", sport="MLB", site="draftkings", player_count=1)]
    provider = _FakeProvider(configured=True, slates=slates, get_projections_error=ProjectionProviderUnavailableError("HTTP 500"))
    result = build_bluecollar_snapshot(_dk_slate(), "2026-08-23", research_output_root=str(tmp_path), provider=provider)
    assert result["status"] == STATUS_API_ERROR
    assert result["snapshot"] is None
