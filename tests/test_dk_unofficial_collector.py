"""Collector orchestration tests -- mocks draftkings_unofficial.client
directly (no network), verifying status translation, no-active-slate
handling, schema-change propagation, and snapshot-save invocation."""

import pytest

from draftkings_unofficial import client, collector
from draftkings_unofficial.cache import DkUnofficialCache

SPORTS_PAYLOAD = {"sports": [{"sportId": 2, "fullName": "Baseball", "hasPublicContests": True, "isEnabled": True, "regionAbbreviatedSportName": "MLB", "sortOrder": 1}]}

CONTESTS_PAYLOAD = {
    "SelectedSport": "MLB",
    "Contests": [{"id": 1, "n": "X", "s": 2, "dg": 10, "gameType": "Classic", "gameTypeId": 2, "sd": "/Date(1788306000000)/", "po": 1.0, "m": 1, "a": 1, "mec": 1, "fpp": 0, "attr": {}}],
    "DraftGroups": [{"DraftGroupId": 10, "SportId": 2, "Sport": "MLB", "GameTypeId": 2, "GameType": None, "StartDate": "x", "StartDateEst": "2026-08-20T18:00:00", "DraftGroupTag": "", "ContestStartTimeSuffix": "", "GameCount": 1}],
    "GameTypes": [{"GameTypeId": 2, "Name": "Classic", "SportId": 2, "DraftType": "SalaryCap", "IsSeasonLong": False}],
}

EMPTY_CONTESTS_PAYLOAD = {"SelectedSport": "NHL", "Contests": [], "DraftGroups": [], "GameTypes": []}

DRAFTABLES_PAYLOAD = {
    "draftables": [{"draftableId": 1, "displayName": "A", "position": "OF", "salary": 4000, "teamId": 1, "teamAbbreviation": "BOS", "competition": {"competitionId": 100}}],
    "competitions": [{"competitionId": 100, "sportId": 2, "name": "X", "startTime": "x"}],
}

RULES_PAYLOAD = {"gameTypeId": 2, "gameTypeName": "Classic", "lineupTemplate": [], "salaryCap": {"isEnabled": True, "maxValue": 50000}}


def test_collect_sports_ok(monkeypatch):
    monkeypatch.setattr(client, "get_sports", lambda: SPORTS_PAYLOAD)
    result = collector.collect_sports(save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_OK
    assert len(result.sports) == 1


def test_collect_sports_schema_changed(monkeypatch):
    monkeypatch.setattr(client, "get_sports", lambda: {"unexpected": []})
    result = collector.collect_sports(save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_SCHEMA_CHANGED


def test_collect_sports_translates_not_found(monkeypatch):
    def raise_404():
        raise client.DraftKingsUnofficialNotFoundError("nope")
    monkeypatch.setattr(client, "get_sports", raise_404)
    result = collector.collect_sports(save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_NOT_FOUND


def test_collect_sports_translates_access_restricted(monkeypatch):
    def raise_403():
        raise client.DraftKingsUnofficialAccessRestrictedError("no")
    monkeypatch.setattr(client, "get_sports", raise_403)
    result = collector.collect_sports(save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_ACCESS_RESTRICTED


def test_collect_sports_translates_rate_limited(monkeypatch):
    def raise_429():
        raise client.DraftKingsUnofficialRateLimitedError("slow down")
    monkeypatch.setattr(client, "get_sports", raise_429)
    result = collector.collect_sports(save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_RATE_LIMITED


def test_collect_sports_translates_unavailable(monkeypatch):
    def raise_unavailable():
        raise client.DraftKingsUnofficialUnavailableError("down")
    monkeypatch.setattr(client, "get_sports", raise_unavailable)
    result = collector.collect_sports(save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_UNAVAILABLE


def test_collect_sports_saves_snapshot_when_requested(monkeypatch):
    saved = []
    monkeypatch.setattr(client, "get_sports", lambda: SPORTS_PAYLOAD)
    monkeypatch.setattr(collector.persistence, "save_raw", lambda *a, **k: saved.append((a, k)))
    collector.collect_sports(save_snapshot=True, cache=DkUnofficialCache())
    assert len(saved) == 1


def test_collect_sport_universe_ok(monkeypatch):
    monkeypatch.setattr(client, "get_contests", lambda sport_code: CONTESTS_PAYLOAD)
    result = collector.collect_sport_universe("MLB", save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_OK
    assert len(result.contests) == 1
    assert len(result.slates) == 1
    assert result.slates[0].contest_ids == [1]


def test_collect_sport_universe_no_active_slate_is_not_an_error(monkeypatch):
    monkeypatch.setattr(client, "get_contests", lambda sport_code: EMPTY_CONTESTS_PAYLOAD)
    result = collector.collect_sport_universe("NHL", save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_NO_ACTIVE_SLATE
    assert result.error is None  # not an error -- see this milestone's explicit "NO ACTIVE SLATE, not an error"


def test_collect_slate_detail_ok_with_rules(monkeypatch):
    monkeypatch.setattr(client, "get_draftables", lambda draft_group_id: DRAFTABLES_PAYLOAD)
    monkeypatch.setattr(client, "get_game_type_rules", lambda game_type_id: RULES_PAYLOAD)
    result = collector.collect_slate_detail(10, "MLB", game_type_id=2, save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_OK
    assert len(result.draftables) == 1
    assert result.roster_rules is not None
    assert result.roster_rules.name == "Classic"


def test_collect_slate_detail_rules_failure_does_not_blank_the_slate(monkeypatch):
    monkeypatch.setattr(client, "get_draftables", lambda draft_group_id: DRAFTABLES_PAYLOAD)

    def raise_unavailable(game_type_id):
        raise client.DraftKingsUnofficialUnavailableError("rules down")
    monkeypatch.setattr(client, "get_game_type_rules", raise_unavailable)

    result = collector.collect_slate_detail(10, "MLB", game_type_id=2, save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_OK  # rules are best-effort
    assert len(result.draftables) == 1  # draftables still present
    assert result.roster_rules is None
    assert result.rules_schema_check["status"] == collector.STATUS_UNAVAILABLE


def test_collect_slate_detail_schema_changed(monkeypatch):
    monkeypatch.setattr(client, "get_draftables", lambda draft_group_id: {"unexpected": []})
    result = collector.collect_slate_detail(10, "MLB", save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_SCHEMA_CHANGED


def test_collect_slate_detail_without_game_type_id_skips_rules(monkeypatch):
    monkeypatch.setattr(client, "get_draftables", lambda draft_group_id: DRAFTABLES_PAYLOAD)
    result = collector.collect_slate_detail(10, "MLB", game_type_id=None, save_snapshot=False, cache=DkUnofficialCache())
    assert result.status == collector.STATUS_OK
    assert result.roster_rules is None
    assert result.rules_schema_check is None


def test_collector_uses_shared_cache_across_two_calls(monkeypatch):
    calls = []

    def fake_get_contests(sport_code):
        calls.append(sport_code)
        return CONTESTS_PAYLOAD

    monkeypatch.setattr(client, "get_contests", fake_get_contests)
    shared_cache = DkUnofficialCache()
    collector.collect_sport_universe("MLB", save_snapshot=False, cache=shared_cache)
    collector.collect_sport_universe("MLB", save_snapshot=False, cache=shared_cache)
    assert len(calls) == 1  # second call served from cache
