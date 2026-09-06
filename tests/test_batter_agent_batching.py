"""MLB BATTER AGENT PERFORMANCE FIX -- tests for every optimization
actually made: bulk MLB Stats API / Baseball Savant requests replacing
per-player sequential calls, cache-first dedup, chunking, error
isolation, and cache date isolation. See research/collector.py and
research/statcast_batter_collector.py for the real production
measurements (461.89s -> batched) this is fixing.
"""

import json
import urllib.error

import pytest

import research.cache as cache
import research.collector as collector
import research.statcast_batter_collector as statcast_batter_collector


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def _json_response(payload: dict) -> _FakeResponse:
    return _FakeResponse(json.dumps(payload).encode("utf-8"))


def _csv_response(text: str) -> _FakeResponse:
    return _FakeResponse(text.encode("utf-8-sig"))


# ---------------------------------------------------------------------------
# research/cache.py -- read/write primitives (refactor of get_or_fetch)
# ---------------------------------------------------------------------------


class TestCacheReadWrite:
    def test_read_returns_none_when_nothing_cached(self, tmp_path):
        assert cache.read(tmp_path, "2026-09-05", "missing_key") is None

    def test_write_then_read_round_trips(self, tmp_path):
        cache.write(tmp_path, "2026-09-05", "k1", {"stats": [1, 2, 3]})
        assert cache.read(tmp_path, "2026-09-05", "k1") == {"stats": [1, 2, 3]}

    def test_write_none_is_a_no_op_never_caches_a_failure(self, tmp_path):
        cache.write(tmp_path, "2026-09-05", "k1", None)
        assert cache.read(tmp_path, "2026-09-05", "k1") is None

    def test_cache_is_isolated_per_date(self, tmp_path):
        cache.write(tmp_path, "2026-09-05", "k1", {"v": 1})
        assert cache.read(tmp_path, "2026-09-06", "k1") is None

    def test_get_or_fetch_still_works_unchanged(self, tmp_path):
        calls = []

        def fetch():
            calls.append(1)
            return {"v": "real"}

        first = cache.get_or_fetch(tmp_path, "2026-09-05", "k1", fetch)
        second = cache.get_or_fetch(tmp_path, "2026-09-05", "k1", fetch)
        assert first == {"v": "real"}
        assert second == {"v": "real"}
        assert len(calls) == 1  # fetch_fn only called once -- second call was a cache hit


# ---------------------------------------------------------------------------
# research/collector.py -- bulk MLB Stats API hydrate batching
# ---------------------------------------------------------------------------


_DEFAULT_STATS_BLOCK = [{"type": {"displayName": "season"}, "splits": [{"stat": {"avg": ".300"}}]}]


def _bulk_people_payload(player_ids, stats_per_player=None):
    stats_per_player = stats_per_player or {}
    people = []
    for pid in player_ids:
        person = {"id": int(pid), "fullName": f"Player {pid}", "stats": stats_per_player.get(pid, _DEFAULT_STATS_BLOCK)}
        people.append(person)
    return {"copyright": "x", "people": people}


class TestFetchBulkHydratedPeople:
    def test_reshapes_each_person_into_the_same_shape_single_player_fetch_returned(self, monkeypatch):
        def fake_urlopen(url, timeout=None):
            return _json_response(_bulk_people_payload(["1", "2"]))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        result = collector._fetch_bulk_hydrated_people(["1", "2"], "group=[hitting],type=[season],season=2026")

        assert set(result.keys()) == {"1", "2"}
        for pid in ("1", "2"):
            assert result[pid] == {"stats": [{"type": {"displayName": "season"}, "splits": [{"stat": {"avg": ".300"}}]}]}

    def test_chunks_requests_to_respect_chunk_size(self, monkeypatch):
        requested_id_lists = []

        def fake_urlopen(url, timeout=None):
            ids_param = url.split("personIds=")[1].split("&")[0]
            requested_id_lists.append(ids_param.split(","))
            return _json_response(_bulk_people_payload(ids_param.split(",")))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        player_ids = [str(i) for i in range(1, 8)]  # 7 players
        collector._fetch_bulk_hydrated_people(player_ids, "group=[hitting],type=[season],season=2026", chunk_size=3)

        assert len(requested_id_lists) == 3  # ceil(7/3)
        assert [len(chunk) for chunk in requested_id_lists] == [3, 3, 1]

    def test_a_failed_chunk_never_poisons_other_chunks(self, monkeypatch):
        calls = {"n": 0}

        def fake_urlopen(url, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.URLError("boom")
            ids_param = url.split("personIds=")[1].split("&")[0]
            return _json_response(_bulk_people_payload(ids_param.split(",")))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        player_ids = [str(i) for i in range(1, 5)]
        result = collector._fetch_bulk_hydrated_people(player_ids, "group=[hitting],type=[season],season=2026", chunk_size=2)

        # First chunk (ids 1,2) failed -- second chunk (ids 3,4) still succeeded.
        assert set(result.keys()) == {"3", "4"}

    def test_a_player_missing_from_the_response_simply_has_no_entry(self, monkeypatch):
        def fake_urlopen(url, timeout=None):
            return _json_response(_bulk_people_payload(["1"]))  # "2" never comes back

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        result = collector._fetch_bulk_hydrated_people(["1", "2"], "group=[hitting],type=[season],season=2026")
        assert "2" not in result


class TestCollectHydratedStatCategoryCacheFirst:
    def test_only_fetches_players_not_already_cached(self, tmp_path, monkeypatch):
        cache.write(tmp_path, "2026-09-05", "season_hitting_1_2026", {"stats": ["cached"]})
        requested_ids = []

        def fake_urlopen(url, timeout=None):
            ids_param = url.split("personIds=")[1].split("&")[0]
            requested_ids.extend(ids_param.split(","))
            return _json_response(_bulk_people_payload(ids_param.split(",")))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        result = collector._collect_hydrated_stat_category(
            ["1", "2"], "2026", "2026-09-05", tmp_path, "season_hitting", "group=[hitting],type=[season],season=2026",
        )

        assert requested_ids == ["2"]  # player 1 was already cached -- never re-fetched
        assert result["1"] == {"stats": ["cached"]}
        assert "2" in result

    def test_newly_fetched_players_are_cached_individually_for_a_later_single_player_read(self, tmp_path, monkeypatch):
        def fake_urlopen(url, timeout=None):
            ids_param = url.split("personIds=")[1].split("&")[0]
            return _json_response(_bulk_people_payload(ids_param.split(",")))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        collector._collect_hydrated_stat_category(
            ["1", "2"], "2026", "2026-09-05", tmp_path, "season_hitting", "group=[hitting],type=[season],season=2026",
        )
        # The exact same key format the OLD per-player get_or_fetch() used.
        assert cache.read(tmp_path, "2026-09-05", "season_hitting_1_2026") is not None
        assert cache.read(tmp_path, "2026-09-05", "season_hitting_2_2026") is not None

    def test_no_network_call_at_all_when_every_player_is_already_cached(self, tmp_path, monkeypatch):
        cache.write(tmp_path, "2026-09-05", "season_hitting_1_2026", {"stats": ["cached"]})
        calls = {"n": 0}

        def fake_urlopen(url, timeout=None):
            calls["n"] += 1
            return _json_response(_bulk_people_payload(["1"]))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        collector._collect_hydrated_stat_category(["1"], "2026", "2026-09-05", tmp_path, "season_hitting", "x")
        assert calls["n"] == 0


class TestCollectBatterStatsBatched:
    def test_warnings_match_old_per_player_semantics_for_a_missing_player(self, tmp_path, monkeypatch):
        def fake_urlopen(url, timeout=None):
            # Player "2" is simply absent from every bulk response -- like a real player with no MLB stats yet.
            return _json_response(_bulk_people_payload(["1"]))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        result = collector.collect_batter_stats(["1", "2"], "2026", "2026-09-05", cache_root=tmp_path)

        assert "1" in result.season_hitting
        assert "2" not in result.season_hitting
        assert any("no season hitting stats available for player 2" in w for w in result.warnings)
        assert any("no hitting game log available for player 2" in w for w in result.warnings)
        assert any("no vs-RHP split available for player 2" in w for w in result.warnings)
        assert any("no vs-LHP split available for player 2" in w for w in result.warnings)

    def test_deterministic_output_for_the_same_frozen_input(self, tmp_path, monkeypatch):
        def fake_urlopen(url, timeout=None):
            ids_param = url.split("personIds=")[1].split("&")[0]
            return _json_response(_bulk_people_payload(ids_param.split(",")))

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        first = collector.collect_batter_stats(["1", "2", "3"], "2026", "2026-09-05", cache_root=tmp_path)
        second = collector.collect_batter_stats(["1", "2", "3"], "2026", "2026-09-05", cache_root=tmp_path)
        assert first.season_hitting == second.season_hitting
        assert first.game_log_hitting == second.game_log_hitting


class TestCollectPitcherStatsBatched:
    def test_batches_season_and_gamelog_pitching(self, tmp_path, monkeypatch):
        requested = []

        def fake_urlopen(url, timeout=None):
            requested.append(url)
            if "personIds=" in url:
                ids_param = url.split("personIds=")[1].split("&")[0]
                return _json_response(_bulk_people_payload(ids_param.split(",")))
            return _json_response({"stats": []})  # team hitting (unchanged, still per-team)

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        result = collector.collect_pitcher_stats(["10", "11"], ["200"], "2026", "2026-09-05", cache_root=tmp_path)

        assert "10" in result.season_pitching and "11" in result.season_pitching
        assert "10" in result.game_log_pitching and "11" in result.game_log_pitching
        bulk_calls = [u for u in requested if "personIds=" in u]
        assert len(bulk_calls) == 2  # one for season, one for gameLog -- not one per pitcher


# ---------------------------------------------------------------------------
# research/collector.py -- bulk bio batching
# ---------------------------------------------------------------------------


class TestFetchBulkPeopleBios:
    def test_returns_raw_person_dicts_matching_single_player_shape(self, monkeypatch):
        def fake_urlopen(url, timeout=None):
            return _json_response({"copyright": "x", "people": [
                {"id": 1, "fullName": "A", "batSide": {"code": "L"}},
                {"id": 2, "fullName": "B", "batSide": {"code": "R"}},
            ]})

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        result = collector._fetch_bulk_people(["1", "2"])
        assert result["1"]["batSide"]["code"] == "L"
        assert result["2"]["batSide"]["code"] == "R"

    def test_collect_batter_bios_is_cache_first(self, tmp_path, monkeypatch):
        cache.write(tmp_path, "2026-09-05", "person_1", {"id": 1, "batSide": {"code": "S"}})
        requested = []

        def fake_urlopen(url, timeout=None):
            ids_param = url.split("personIds=")[1].split("&")[0]
            requested.extend(ids_param.split(","))
            return _json_response({"people": [{"id": int(pid), "batSide": {"code": "R"}} for pid in ids_param.split(",")]})

        monkeypatch.setattr(collector.urllib.request, "urlopen", fake_urlopen)
        result = collector.collect_batter_bios(["1", "2"], "2026-09-05", cache_root=tmp_path)

        assert requested == ["2"]
        assert result["1"]["batSide"]["code"] == "S"  # untouched, from cache
        assert result["2"]["batSide"]["code"] == "R"  # freshly fetched


# ---------------------------------------------------------------------------
# research/statcast_batter_collector.py -- Baseball Savant batch batting
# ---------------------------------------------------------------------------


def _savant_csv(rows):
    if not rows:
        return "batter,pitches\n"
    header = ",".join(rows[0].keys())
    lines = [header] + [",".join(str(r[k]) for k in rows[0].keys()) for r in rows]
    return "\n".join(lines) + "\n"


class TestFetchRecentPitchLevelBulk:
    def test_splits_the_combined_csv_by_batter_column(self, monkeypatch):
        def fake_urlopen(req, timeout=None):
            return _csv_response(_savant_csv([
                {"batter": "1", "pitches": "5"},
                {"batter": "1", "pitches": "3"},
                {"batter": "2", "pitches": "7"},
            ]))

        monkeypatch.setattr(statcast_batter_collector.urllib.request, "urlopen", fake_urlopen)
        result = statcast_batter_collector._fetch_recent_pitch_level_bulk(["1", "2"], "2026-08-22", "2026-09-05")

        assert len(result["1"]) == 2
        assert len(result["2"]) == 1

    def test_chunks_requests(self, monkeypatch):
        request_count = {"n": 0}

        def fake_urlopen(req, timeout=None):
            request_count["n"] += 1
            return _csv_response(_savant_csv([{"batter": "1", "pitches": "1"}]))

        monkeypatch.setattr(statcast_batter_collector.urllib.request, "urlopen", fake_urlopen)
        player_ids = [str(i) for i in range(1, 55)]  # 54 players
        statcast_batter_collector._fetch_recent_pitch_level_bulk(player_ids, "2026-08-22", "2026-09-05", chunk_size=25)
        assert request_count["n"] == 3  # ceil(54/25)

    def test_a_failed_chunk_never_poisons_other_chunks(self, monkeypatch):
        calls = {"n": 0}

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.URLError("boom")
            return _csv_response(_savant_csv([{"batter": "3", "pitches": "9"}]))

        monkeypatch.setattr(statcast_batter_collector.urllib.request, "urlopen", fake_urlopen)
        result = statcast_batter_collector._fetch_recent_pitch_level_bulk(["1", "3"], "2026-08-22", "2026-09-05", chunk_size=1)
        assert "1" not in result
        assert "3" in result


class TestCollectBatterStatcastDataCacheFirst:
    def test_only_fetches_players_not_already_cached(self, tmp_path, monkeypatch):
        # window_days defaults to 14, and date_gt is computed as
        # reference_date - (window_days + 1) days -- 2026-09-05 - 15d = 2026-08-21.
        cache.write(tmp_path, "2026-09-05", "batter_recent_pitch_level_1_2026-08-21_2026-09-05", [{"batter": "1", "pitches": "9"}])
        fetched_ids = []

        def fake_urlopen(req, timeout=None):
            url = req.full_url
            if "leaderboard" in url:
                return _csv_response(_savant_csv([{"player_id": "1", "xwoba": ".300"}]))
            lookup = url.split("batters_lookup")[1]
            pid = lookup.split("=")[1].split("&")[0]
            fetched_ids.append(pid)
            return _csv_response(_savant_csv([{"batter": pid, "pitches": "5"}]))

        monkeypatch.setattr(statcast_batter_collector.urllib.request, "urlopen", fake_urlopen)
        result = statcast_batter_collector.collect_batter_statcast_data(["1", "2"], "2026", "2026-09-05", "2026-09-05", cache_root=tmp_path)

        assert fetched_ids == ["2"]
        assert result.recent_pitch_level["1"] == [{"batter": "1", "pitches": "9"}]
        assert "2" in result.recent_pitch_level
