from player_identity import roster_source


def test_parse_roster_entries_splits_pitcher_vs_hitter():
    raw = {"roster": [
        {"person": {"id": 607074, "fullName": "Carlos Rodon"}, "position": {"abbreviation": "P"}, "status": {"code": "A"}},
        {"person": {"id": 700250, "fullName": "Ben Rice"}, "position": {"abbreviation": "DH"}, "status": {"code": "A"}},
    ]}
    entries = roster_source.parse_roster_entries(raw)
    assert len(entries) == 2
    pitcher = next(e for e in entries if e["mlb_player_id"] == "607074")
    hitter = next(e for e in entries if e["mlb_player_id"] == "700250")
    assert pitcher["player_type"] == "pitcher"
    assert hitter["player_type"] == "hitter"
    assert pitcher["name"] == "Carlos Rodon"
    assert pitcher["active"] is True


def test_parse_roster_entries_flags_inactive_status():
    raw = {"roster": [
        {"person": {"id": 1, "fullName": "Injured Player"}, "position": {"abbreviation": "OF"}, "status": {"code": "D60"}},
    ]}
    entries = roster_source.parse_roster_entries(raw)
    assert entries[0]["active"] is False


def test_parse_roster_entries_skips_malformed_rows_without_raising():
    raw = {"roster": [
        {"position": {"abbreviation": "P"}},  # no person block
        {"person": {"id": 1, "fullName": ""}},  # empty name
        {"person": {"id": None, "fullName": "No Id"}},
    ]}
    assert roster_source.parse_roster_entries(raw) == []


def test_parse_roster_entries_handles_none_and_empty_payload():
    assert roster_source.parse_roster_entries(None) == []
    assert roster_source.parse_roster_entries({}) == []
    assert roster_source.parse_roster_entries({"roster": []}) == []


def test_fetch_cached_team_roster_caches_and_reuses(tmp_path, monkeypatch):
    call_count = {"n": 0}

    def fake_fetch(team_id):
        call_count["n"] += 1
        return {"roster": [{"person": {"id": 1, "fullName": "X"}, "position": {"abbreviation": "P"}, "status": {"code": "A"}}]}

    monkeypatch.setattr(roster_source, "fetch_team_roster", fake_fetch)

    first = roster_source.fetch_cached_team_roster("147", "2026-08-23", cache_root=tmp_path)
    second = roster_source.fetch_cached_team_roster("147", "2026-08-23", cache_root=tmp_path)

    assert first == second
    assert call_count["n"] == 1  # only fetched once -- second call served from cache


def test_fetch_cached_team_roster_never_caches_a_failure(tmp_path, monkeypatch):
    call_count = {"n": 0}

    def fake_fetch(team_id):
        call_count["n"] += 1
        return None

    monkeypatch.setattr(roster_source, "fetch_team_roster", fake_fetch)

    assert roster_source.fetch_cached_team_roster("147", "2026-08-23", cache_root=tmp_path) is None
    assert roster_source.fetch_cached_team_roster("147", "2026-08-23", cache_root=tmp_path) is None
    assert call_count["n"] == 2  # a failed fetch is retried, never "stuck" as cached None


def test_fetch_cached_team_roster_scoped_per_team(tmp_path, monkeypatch):
    def fake_fetch(team_id):
        return {"roster": [{"person": {"id": int(team_id), "fullName": f"Player {team_id}"}, "position": {"abbreviation": "P"}, "status": {"code": "A"}}]}

    monkeypatch.setattr(roster_source, "fetch_team_roster", fake_fetch)

    a = roster_source.fetch_cached_team_roster("147", "2026-08-23", cache_root=tmp_path)
    b = roster_source.fetch_cached_team_roster("111", "2026-08-23", cache_root=tmp_path)
    assert a != b
