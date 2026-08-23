import json
from pathlib import Path

from player_identity import refresh as refresh_module
from player_identity.persistence import load_crosswalk


def _write_teams(research_root: Path, date: str, teams):
    folder = research_root / date
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "teams.json").write_text(json.dumps(teams), encoding="utf-8")


def _roster(entries):
    return {"roster": entries}


def _entry(player_id, name, position="OF"):
    return {"person": {"id": player_id, "fullName": name}, "position": {"abbreviation": position}, "status": {"code": "A"}}


def test_refresh_identity_returns_zero_teams_when_no_schedule_exists(tmp_path):
    result = refresh_module.refresh_identity(
        "2026-08-23", research_output_root=str(tmp_path / "research_output"),
        cache_root=tmp_path / "cache", crosswalk_path=tmp_path / "crosswalk.json",
        snapshot_root=tmp_path / "snapshots", historical_crosswalk_path=tmp_path / "no_historical.parquet",
    )
    assert result.teams_total == 0
    assert result.teams_fetched == 0
    assert result.players_seen_this_refresh == 0


def test_refresh_identity_fetches_each_teams_roster_and_persists_the_crosswalk(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_teams(research_root, "2026-08-23", [
        {"team_id": "147", "abbreviation": "NYY"},
        {"team_id": "111", "abbreviation": "BOS"},
    ])

    def fake_fetch(team_id):
        return _roster([_entry(int(team_id) * 10 + 1, f"Player {team_id}")])

    monkeypatch.setattr(refresh_module, "fetch_cached_team_roster", lambda team_id, date, cache_root: fake_fetch(team_id))

    crosswalk_path = tmp_path / "crosswalk.json"
    result = refresh_module.refresh_identity(
        "2026-08-23", research_output_root=str(research_root), cache_root=tmp_path / "cache",
        crosswalk_path=crosswalk_path, snapshot_root=tmp_path / "snapshots",
        historical_crosswalk_path=tmp_path / "no_historical.parquet",
    )

    assert result.teams_total == 2
    assert result.teams_fetched == 2
    assert result.teams_failed == []
    assert result.players_seen_this_refresh == 2
    assert result.crosswalk_size_after == 2

    persisted = load_crosswalk(crosswalk_path)
    assert len(persisted) == 2


def test_refresh_identity_records_a_teams_failed_fetch_without_blocking_the_others(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_teams(research_root, "2026-08-23", [
        {"team_id": "147", "abbreviation": "NYY"},
        {"team_id": "111", "abbreviation": "BOS"},
    ])

    def fake_fetch(team_id, date, cache_root):
        if team_id == "147":
            return None  # simulated failure
        return _roster([_entry(1, "Player One")])

    monkeypatch.setattr(refresh_module, "fetch_cached_team_roster", fake_fetch)

    result = refresh_module.refresh_identity(
        "2026-08-23", research_output_root=str(research_root), cache_root=tmp_path / "cache",
        crosswalk_path=tmp_path / "crosswalk.json", snapshot_root=tmp_path / "snapshots",
        historical_crosswalk_path=tmp_path / "no_historical.parquet",
    )

    assert result.teams_fetched == 1
    assert result.teams_failed == ["NYY"]
    assert result.players_seen_this_refresh == 1


def test_refresh_identity_saves_an_immutable_audit_snapshot(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_teams(research_root, "2026-08-23", [{"team_id": "147", "abbreviation": "NYY"}])
    monkeypatch.setattr(refresh_module, "fetch_cached_team_roster", lambda team_id, date, cache_root: _roster([_entry(1, "X")]))

    result = refresh_module.refresh_identity(
        "2026-08-23", research_output_root=str(research_root), cache_root=tmp_path / "cache",
        crosswalk_path=tmp_path / "crosswalk.json", snapshot_root=tmp_path / "snapshots",
        historical_crosswalk_path=tmp_path / "no_historical.parquet",
    )

    assert result.snapshot_path is not None
    assert Path(result.snapshot_path).exists()


def test_refresh_identity_merges_with_an_existing_crosswalk_rather_than_replacing_it(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    crosswalk_path = tmp_path / "crosswalk.json"

    # First refresh: only NYY.
    _write_teams(research_root, "2026-08-23", [{"team_id": "147", "abbreviation": "NYY"}])
    monkeypatch.setattr(refresh_module, "fetch_cached_team_roster", lambda team_id, date, cache_root: _roster([_entry(1, "Yankee")]))
    refresh_module.refresh_identity(
        "2026-08-23", research_output_root=str(research_root), cache_root=tmp_path / "cache",
        crosswalk_path=crosswalk_path, snapshot_root=tmp_path / "snapshots",
        historical_crosswalk_path=tmp_path / "no_historical.parquet",
    )

    # Second refresh, different date: only BOS. NYY's earlier identity
    # must survive in the rolling crosswalk even though NYY's roster
    # isn't re-fetched this time.
    _write_teams(research_root, "2026-08-24", [{"team_id": "111", "abbreviation": "BOS"}])
    monkeypatch.setattr(refresh_module, "fetch_cached_team_roster", lambda team_id, date, cache_root: _roster([_entry(2, "Red Sox Player")]))
    result = refresh_module.refresh_identity(
        "2026-08-24", research_output_root=str(research_root), cache_root=tmp_path / "cache",
        crosswalk_path=crosswalk_path, snapshot_root=tmp_path / "snapshots",
        historical_crosswalk_path=tmp_path / "no_historical.parquet",
    )

    assert result.crosswalk_size_after == 2
    persisted = load_crosswalk(crosswalk_path)
    assert "1" in persisted
    assert "2" in persisted


def test_refresh_identity_never_calls_a_teams_roster_more_than_once_per_refresh(tmp_path, monkeypatch):
    research_root = tmp_path / "research_output"
    _write_teams(research_root, "2026-08-23", [
        {"team_id": "147", "abbreviation": "NYY"}, {"team_id": "111", "abbreviation": "BOS"},
        {"team_id": "121", "abbreviation": "NYM"},
    ])
    call_counts = {}

    def fake_fetch(team_id, date, cache_root):
        call_counts[team_id] = call_counts.get(team_id, 0) + 1
        return _roster([_entry(int(team_id), f"Player {team_id}")])

    monkeypatch.setattr(refresh_module, "fetch_cached_team_roster", fake_fetch)
    refresh_module.refresh_identity(
        "2026-08-23", research_output_root=str(research_root), cache_root=tmp_path / "cache",
        crosswalk_path=tmp_path / "crosswalk.json", snapshot_root=tmp_path / "snapshots",
        historical_crosswalk_path=tmp_path / "no_historical.parquet",
    )
    assert all(n == 1 for n in call_counts.values())
    assert len(call_counts) == 3
