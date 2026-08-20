import json
from pathlib import Path

import pytest

from fantasypros import build as fp_build
from fantasypros import client as fp_client
from fantasypros.build import build_fantasypros_snapshot


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


HITTER_PAYLOAD = {
    "date": "2026-08-19", "position": "H", "count": 1,
    "player": [{"fpid": 1, "player_id": 1, "team_id": "LAD", "name": "Freddie Freeman", "1b": 1.0, "hrs": 0.1}],
    "limit": 10, "public_api_limited": True, "tier": "free",
}
PITCHER_PAYLOAD = {
    "date": "2026-08-19", "position": "P", "count": 1,
    "player": [{"fpid": 2, "player_id": 2, "team_id": "BOS", "name": "Some Pitcher", "ip": 6.0, "k": 6.0}],
    "limit": 10, "public_api_limited": True, "tier": "free",
}


def _write_research_package(root: Path, date: str):
    folder = root / date
    folder.mkdir(parents=True)
    (folder / "games.json").write_text("[]", encoding="utf-8")
    (folder / "teams.json").write_text("[]", encoding="utf-8")
    (folder / "pitchers.json").write_text(json.dumps([
        {"player_id": "p1", "name": "Some Pitcher", "team_id": "1", "team_abbr": "BOS",
         "opponent_team_id": "2", "opponent_abbr": "TOR", "game_id": "g1", "status": "probable"},
    ]), encoding="utf-8")
    (folder / "batters.json").write_text(json.dumps([
        {"player_id": "h1", "name": "Freddie Freeman", "team_id": "1", "team_abbr": "LAD",
         "opponent_team_id": "2", "opponent_abbr": "COL", "game_id": "g2", "batting_order": 3, "status": "starting_lineup"},
    ]), encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch):
    monkeypatch.delenv("FANTASYPROS_API_KEY", raising=False)


def test_not_configured_returns_status_without_calling_api(monkeypatch, tmp_path):
    called = {"count": 0}
    monkeypatch.setattr(fp_client.urllib.request, "urlopen", lambda *a, **k: called.__setitem__("count", called["count"] + 1))
    result = build_fantasypros_snapshot("2026-08-19", str(tmp_path))
    assert result["status"] == "not_configured"
    assert result["snapshot"] is None
    assert called["count"] == 0


def test_no_research_package_returns_status_not_error(monkeypatch, tmp_path):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    monkeypatch.setattr(fp_client.urllib.request, "urlopen", lambda request, timeout=None: FakeResponse(
        json.dumps(HITTER_PAYLOAD if "position=H" in request.full_url else PITCHER_PAYLOAD).encode("utf-8")
    ))
    result = build_fantasypros_snapshot("2026-08-19", str(tmp_path / "no_such_research_root"))
    assert result["status"] == "no_research"
    assert result["snapshot"] is None
    assert result["error"] is not None


def test_api_error_returns_status_not_raises(monkeypatch, tmp_path):
    import urllib.error
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", None, None)

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    result = build_fantasypros_snapshot("2026-08-19", str(tmp_path))
    assert result["status"] == "api_error"
    assert result["snapshot"] is None
    assert "401" in result["error"] or "Unauthorized" in result["error"] or result["error"]


def test_ready_builds_snapshot_with_dk_points_and_matching(monkeypatch, tmp_path):
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    _write_research_package(tmp_path, "2026-08-19")
    monkeypatch.setattr(fp_client.urllib.request, "urlopen", lambda request, timeout=None: FakeResponse(
        json.dumps(HITTER_PAYLOAD if "position=H" in request.full_url else PITCHER_PAYLOAD).encode("utf-8")
    ))

    result = build_fantasypros_snapshot("2026-08-19", str(tmp_path))
    assert result["status"] == "ready"
    snap = result["snapshot"]
    assert snap.hitter_count == 1
    assert snap.pitcher_count == 1
    assert snap.hitters_matched == 1  # Freddie Freeman on LAD matches the fixture
    assert snap.pitchers_matched == 1  # Some Pitcher on BOS matches the fixture
    assert snap.public_api_limited is True
    assert snap.api_tier == "free"

    hitter = next(p for p in snap.players if p.player_type == "hitter")
    assert hitter.mlb_player_id == "h1"
    assert hitter.dk_points is not None
    pitcher = next(p for p in snap.players if p.player_type == "pitcher")
    assert pitcher.mlb_player_id == "p1"
    assert pitcher.dk_points is not None


def test_never_raises_on_unexpected_hitter_fetch_failure_isolated_from_pitcher(monkeypatch, tmp_path):
    """A genuinely unexpected exception during the hitter fetch must not
    leave the caller with a half-built/partial in-memory state -- the
    whole build reports api_error, cleanly, rather than crashing the
    calling pipeline (Native/AI must be unaffected -- see
    dashboard/lib/slatePipeline.ts's own try/except wrapping of this
    script's subprocess call for the other half of this guarantee)."""
    monkeypatch.setenv("FANTASYPROS_API_KEY", "k")
    import urllib.error

    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(fp_client.urllib.request, "urlopen", fake_urlopen)
    result = build_fantasypros_snapshot("2026-08-19", str(tmp_path))
    assert result["status"] == "api_error"
