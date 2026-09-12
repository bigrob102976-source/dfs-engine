"""NFL M15 -- targeted tests for nfl/pool_cache.py, the production
DraftKings-access resilience layer. Mirrors tests/test_nfl_persistence.
py's tmp_path pattern (output_root=tmp_path is treated as a raw local
scratch path outside research/artifact_storage.py's ARTIFACT_ROOT)."""

from datetime import datetime, timedelta, timezone

import pytest

from nfl.models import NflPlayer, NflPoolBuildResult, NflPoolValidationResult
from nfl.persistence import list_nfl_player_pools, save_nfl_player_pool
from nfl.pool_cache import (
    NflSlateDiscoveryError,
    is_railway_production_environment,
    list_nfl_universe_snapshots,
    load_fresh_cached_pool,
    load_fresh_cached_universe,
    prune_old_snapshots,
    resolve_nfl_slate_date,
    save_nfl_universe_snapshot,
)

NOW = datetime(2026, 9, 13, 17, 0, 0, tzinfo=timezone.utc)


def _player(pid="1"):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id="100", draftable_ids=["1"], name="Test Player",
        first_name="Test", last_name="Player", is_team_entity=False, position="QB", roster_slots=["QB"],
        team="PHI", opponent="DAL", game_id="100", game_description="DAL @ PHI", game_start_time="2026-09-13T17:00:00Z",
        salary=7500, status="None", injury_status=None, draft_group_id=151307, slate_date="2026-09-13",
        slate_name="Featured", source="draftkings_unofficial", source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def _result(draft_group_id=151307, provenance="DRAFTKINGS_UNOFFICIAL_LIVE"):
    validation = NflPoolValidationResult(passed=True, findings=[], total_players=1, position_counts={"QB": 1}, team_count=1, game_count=1, salary_min=7500, salary_max=7500)
    return NflPoolBuildResult(
        draft_group_id=draft_group_id, slate_date="2026-09-13", slate_name="Featured",
        players=[_player()], validation=validation, source_provenance=provenance,
    )


class TestLoadFreshCachedPool:
    def test_returns_none_when_nothing_saved(self, tmp_path):
        assert load_fresh_cached_pool("2026-09-13", 151307, output_root=tmp_path, now_utc=NOW) is None

    def test_returns_the_pool_when_fresh_and_matching(self, tmp_path):
        timestamp = (NOW - timedelta(minutes=5)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        cached = load_fresh_cached_pool("2026-09-13", 151307, output_root=tmp_path, now_utc=NOW)
        assert cached is not None
        assert cached.draft_group_id == 151307
        assert len(cached.players) == 1
        assert cached.players[0].draftkings_player_id == "1"

    # 2026-09-11 incident fix -- past the 15-minute freshness window but
    # well within the 2-hour stale ceiling, this must now be REUSED
    # (marked stale) rather than discarded: discarding a real artifact
    # here is exactly what forced a live DraftKings call from production
    # and returned a bare 502 (DraftKings' own ACCESS_RESTRICTED HTTP 403
    # -- Railway's egress is permanently blocked). See
    # POOL_CACHE_STALE_MAX_SECONDS's own docstring.
    def test_reuses_a_stale_pool_within_the_ceiling_instead_of_discarding_it(self, tmp_path):
        timestamp = (NOW - timedelta(minutes=16)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        cached = load_fresh_cached_pool("2026-09-13", 151307, output_root=tmp_path, now_utc=NOW)
        assert cached is not None
        assert cached.data_status == "stale"
        assert cached.pool_generated_at_utc is not None

    def test_returns_none_once_past_the_stale_ceiling(self, tmp_path):
        timestamp = (NOW - timedelta(hours=3)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        assert load_fresh_cached_pool("2026-09-13", 151307, output_root=tmp_path, now_utc=NOW) is None

    def test_fresh_pool_reports_data_status_fresh(self, tmp_path):
        timestamp = (NOW - timedelta(minutes=5)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        cached = load_fresh_cached_pool("2026-09-13", 151307, output_root=tmp_path, now_utc=NOW)
        assert cached is not None
        assert cached.data_status == "fresh"

    def test_returns_none_for_a_different_draft_group(self, tmp_path):
        timestamp = (NOW - timedelta(minutes=5)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(draft_group_id=999999), timestamp, output_root=tmp_path)

        assert load_fresh_cached_pool("2026-09-13", 151307, output_root=tmp_path, now_utc=NOW) is None

    def test_returns_none_for_non_live_provenance(self, tmp_path):
        timestamp = (NOW - timedelta(minutes=5)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(provenance="SOMETHING_ELSE"), timestamp, output_root=tmp_path)

        assert load_fresh_cached_pool("2026-09-13", 151307, output_root=tmp_path, now_utc=NOW) is None

    def test_respects_a_custom_max_age(self, tmp_path):
        timestamp = (NOW - timedelta(minutes=5)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        # Past the custom (60s) fresh threshold but still well within the
        # default stale ceiling -- reused, marked stale, not discarded.
        past_fresh = load_fresh_cached_pool("2026-09-13", 151307, max_age_seconds=60, output_root=tmp_path, now_utc=NOW)
        assert past_fresh is not None
        assert past_fresh.data_status == "stale"
        within_fresh = load_fresh_cached_pool("2026-09-13", 151307, max_age_seconds=600, output_root=tmp_path, now_utc=NOW)
        assert within_fresh is not None
        assert within_fresh.data_status == "fresh"

    def test_respects_a_custom_stale_ceiling(self, tmp_path):
        timestamp = (NOW - timedelta(minutes=30)).strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        assert load_fresh_cached_pool("2026-09-13", 151307, stale_max_age_seconds=60, output_root=tmp_path, now_utc=NOW) is None


class TestUniverseSnapshot:
    def test_round_trip_fresh(self, tmp_path):
        slates = [{"draft_group_id": 151307, "slate_date": "2026-09-13", "start_time": "2026-09-13T17:00:00Z", "tag": "Main", "label": "NFL Main Slate"}]
        timestamp = (NOW - timedelta(minutes=3)).strftime("%Y%m%dT%H%M%S")
        save_nfl_universe_snapshot(slates, timestamp, output_root=tmp_path)

        loaded = load_fresh_cached_universe(output_root=tmp_path, now_utc=NOW)
        assert loaded == slates

    def test_none_when_nothing_saved(self, tmp_path):
        assert load_fresh_cached_universe(output_root=tmp_path, now_utc=NOW) is None

    # 2026-09-11 incident fix -- same reasoning as the pool cache: a
    # universe past the 15-minute freshness window but within the 2-hour
    # stale ceiling is still a real, usable draft_group_id -> slate_date
    # mapping and must be reused rather than forcing a live call.
    def test_reuses_a_stale_universe_within_the_ceiling(self, tmp_path):
        slates = [{"draft_group_id": 151307, "slate_date": "2026-09-13", "start_time": None, "tag": "Main", "label": "NFL Main Slate"}]
        timestamp = (NOW - timedelta(minutes=20)).strftime("%Y%m%dT%H%M%S")
        save_nfl_universe_snapshot(slates, timestamp, output_root=tmp_path)

        assert load_fresh_cached_universe(output_root=tmp_path, now_utc=NOW) == slates

    def test_none_once_past_the_stale_ceiling(self, tmp_path):
        slates = [{"draft_group_id": 151307, "slate_date": "2026-09-13", "start_time": None, "tag": "Main", "label": "NFL Main Slate"}]
        timestamp = (NOW - timedelta(hours=3)).strftime("%Y%m%dT%H%M%S")
        save_nfl_universe_snapshot(slates, timestamp, output_root=tmp_path)

        assert load_fresh_cached_universe(output_root=tmp_path, now_utc=NOW) is None

    def test_never_overwrites_existing_snapshot(self, tmp_path):
        timestamp = NOW.strftime("%Y%m%dT%H%M%S")
        save_nfl_universe_snapshot([], timestamp, output_root=tmp_path)
        with pytest.raises(FileExistsError):
            save_nfl_universe_snapshot([], timestamp, output_root=tmp_path)


class TestResolveNflSlateDate:
    def test_resolves_from_a_fresh_cached_universe_without_any_live_call(self, tmp_path, monkeypatch):
        import draftkings_unofficial.collector as collector_module

        # Explicit, not just incidental: these local-dev tests must exercise
        # the exact same branch a real local dev machine does, never the
        # production-gated one (see TestProductionNeverAttemptsALiveCall
        # below for that side).
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)

        def _boom(sport_code):  # must never be called when the cache hits
            raise AssertionError("live discovery should not be called when a fresh cache hit resolves the DraftGroup")

        monkeypatch.setattr(collector_module, "collect_sport_universe", _boom)
        timestamp = (NOW - timedelta(minutes=2)).strftime("%Y%m%dT%H%M%S")
        save_nfl_universe_snapshot(
            [{"draft_group_id": 151307, "slate_date": "2026-09-13", "start_time": None, "tag": "Main", "label": "NFL Main Slate"}],
            timestamp, output_root=tmp_path,
        )

        resolved = resolve_nfl_slate_date(151307, output_root=tmp_path, now_utc=NOW)
        assert resolved == "2026-09-13"

    def test_falls_back_to_live_discovery_on_cache_miss(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)

        class FakeSlate:
            draft_group_id = 151307
            game_type_id = 1

        class FakeUniverse:
            status = "ok"
            slates = [FakeSlate()]
            error = None

        import draftkings_unofficial.collector as collector_module

        monkeypatch.setattr(collector_module, "collect_sport_universe", lambda sport_code: FakeUniverse())
        monkeypatch.setattr(collector_module, "STATUS_OK", "ok")
        monkeypatch.setattr(collector_module, "slate_local_date", lambda s: "2026-09-14")

        resolved = resolve_nfl_slate_date(151307, output_root=tmp_path, now_utc=NOW)
        assert resolved == "2026-09-14"

    def test_raises_when_cache_misses_and_live_discovery_fails(self, tmp_path, monkeypatch):
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)

        class FakeUniverse:
            status = "ACCESS_RESTRICTED"
            slates = []
            error = "blocked"

        import draftkings_unofficial.collector as collector_module

        monkeypatch.setattr(collector_module, "collect_sport_universe", lambda sport_code: FakeUniverse())
        monkeypatch.setattr(collector_module, "STATUS_OK", "ok")

        with pytest.raises(NflSlateDiscoveryError):
            resolve_nfl_slate_date(151307, output_root=tmp_path, now_utc=NOW)


# 2026-09-11 incident regression coverage: a request for a DraftGroup whose
# cache had gone stale previously fell through to a live DraftKings call
# from production and returned a bare 502 (DraftKings' own
# ACCESS_RESTRICTED HTTP 403 -- Railway's egress is permanently blocked).
# These prove that path is now refused, not attempted, whenever
# RAILWAY_ENVIRONMENT is set (is_railway_production_environment()).
class TestProductionNeverAttemptsALiveCall:
    def test_is_railway_production_environment_reflects_the_env_var(self, monkeypatch):
        monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
        assert is_railway_production_environment() is False
        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
        assert is_railway_production_environment() is True

    def test_resolve_nfl_slate_date_raises_instead_of_calling_dk_live_in_production(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

        def _boom(sport_code):
            raise AssertionError("a live DraftKings call must never be attempted from production")

        import draftkings_unofficial.collector as collector_module

        monkeypatch.setattr(collector_module, "collect_sport_universe", _boom)

        with pytest.raises(NflSlateDiscoveryError, match="never attempted from production"):
            resolve_nfl_slate_date(151307, output_root=tmp_path, now_utc=NOW)

    def test_resolve_nfl_slate_date_still_reuses_a_stale_cache_in_production(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")

        def _boom(sport_code):
            raise AssertionError("a stale-but-usable cache hit must never fall through to a live call")

        import draftkings_unofficial.collector as collector_module

        monkeypatch.setattr(collector_module, "collect_sport_universe", _boom)

        timestamp = (NOW - timedelta(minutes=20)).strftime("%Y%m%dT%H%M%S")
        save_nfl_universe_snapshot(
            [{"draft_group_id": 151307, "slate_date": "2026-09-13", "start_time": None, "tag": "Main", "label": "NFL Main Slate"}],
            timestamp, output_root=tmp_path,
        )

        assert resolve_nfl_slate_date(151307, output_root=tmp_path, now_utc=NOW) == "2026-09-13"


class TestPruneOldSnapshots:
    def test_keeps_the_most_recent_n_and_deletes_the_rest(self, tmp_path):
        for i in range(5):
            timestamp = (NOW - timedelta(minutes=(4 - i) * 5)).strftime("%Y%m%dT%H%M%S")
            save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        pools = list_nfl_player_pools("2026-09-13", output_root=tmp_path)
        assert len(pools) == 5

        deleted = prune_old_snapshots(pools, keep_last=2)
        assert len(deleted) == 3

        remaining = list_nfl_player_pools("2026-09-13", output_root=tmp_path)
        assert len(remaining) == 2
        assert remaining == pools[-2:]

    def test_no_op_when_at_or_under_the_retention_count(self, tmp_path):
        timestamp = NOW.strftime("%Y%m%dT%H%M%S")
        save_nfl_player_pool(_result(), timestamp, output_root=tmp_path)

        pools = list_nfl_player_pools("2026-09-13", output_root=tmp_path)
        deleted = prune_old_snapshots(pools, keep_last=12)
        assert deleted == []
        assert len(list_nfl_player_pools("2026-09-13", output_root=tmp_path)) == 1

    def test_prunes_universe_snapshots_by_string_key(self, tmp_path):
        for i in range(4):
            timestamp = (NOW - timedelta(minutes=(3 - i) * 5)).strftime("%Y%m%dT%H%M%S")
            save_nfl_universe_snapshot([], timestamp, output_root=tmp_path)

        keys = list_nfl_universe_snapshots(output_root=tmp_path)
        assert len(keys) == 4

        deleted = prune_old_snapshots(keys, keep_last=1)
        assert len(deleted) == 3
        assert len(list_nfl_universe_snapshots(output_root=tmp_path)) == 1
