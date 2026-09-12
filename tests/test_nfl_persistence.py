"""NFL M2 -- targeted tests for nfl/persistence.py. Mirrors
tests/test_prediction_snapshot.py's tmp_path pattern (a path outside
research/artifact_storage.py's ARTIFACT_ROOT is treated as a raw
absolute scratch path, so output_root=tmp_path just works against
local disk with no object-storage configuration needed)."""

import pytest

from nfl.models import NflPlayer, NflPoolBuildResult, NflPoolValidationResult
from nfl.persistence import list_nfl_player_pools, load_latest_nfl_player_pool, save_nfl_player_pool


def _player(pid="1"):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id="100", draftable_ids=["1"], name="Test Player",
        first_name="Test", last_name="Player", is_team_entity=False, position="QB", roster_slots=["QB"],
        team="PHI", opponent="DAL", game_id="100", game_description="DAL @ PHI", game_start_time="2026-09-13T17:00:00Z",
        salary=7500, status="None", injury_status=None, draft_group_id=151307, slate_date="2026-09-13",
        slate_name="Featured", source="draftkings_unofficial", source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def _result(draft_group_id=151307):
    validation = NflPoolValidationResult(passed=True, findings=[], total_players=1, position_counts={"QB": 1}, team_count=1, game_count=1, salary_min=7500, salary_max=7500)
    return NflPoolBuildResult(
        draft_group_id=draft_group_id, slate_date="2026-09-13", slate_name="Featured",
        players=[_player()], validation=validation, source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def test_save_writes_to_nfl_scoped_date_folder(tmp_path):
    path = save_nfl_player_pool(_result(), "20260913T170000", output_root=tmp_path)
    assert path == tmp_path / "2026-09-13" / "nfl_player_pool_20260913T170000_151307.json"
    assert path.exists()


# 2026-09-11 incident regression coverage: two DraftGroups sharing a
# slate_date AND a fetch cycle's timestamp used to collide on the exact
# same path (no draft_group_id in the filename) -- the second raised
# FileExistsError and every DraftGroup after the first was silently lost
# on every cycle. Confirmed live: 2026-09-13 has five concurrently-live
# Classic DraftGroups; only one (153068) had ever been cached.
def test_two_draft_groups_sharing_a_date_and_timestamp_do_not_collide(tmp_path):
    path_a = save_nfl_player_pool(_result(draft_group_id=153068), "20260913T170000", output_root=tmp_path)
    path_b = save_nfl_player_pool(_result(draft_group_id=153070), "20260913T170000", output_root=tmp_path)
    assert path_a != path_b
    assert path_a.exists()
    assert path_b.exists()


def test_list_and_load_latest_scoped_to_one_draft_group_among_several(tmp_path):
    save_nfl_player_pool(_result(draft_group_id=153068), "20260913T170000", output_root=tmp_path)
    save_nfl_player_pool(_result(draft_group_id=153070), "20260913T170000", output_root=tmp_path)
    save_nfl_player_pool(_result(draft_group_id=153070), "20260913T180000", output_root=tmp_path)

    pools_153068 = list_nfl_player_pools("2026-09-13", 153068, output_root=tmp_path)
    assert len(pools_153068) == 1
    pools_153070 = list_nfl_player_pools("2026-09-13", 153070, output_root=tmp_path)
    assert len(pools_153070) == 2

    latest = load_latest_nfl_player_pool("2026-09-13", 153070, output_root=tmp_path)
    assert latest["draft_group_id"] == 153070


def test_save_never_overwrites_existing_file(tmp_path):
    save_nfl_player_pool(_result(), "20260913T170000", output_root=tmp_path)
    with pytest.raises(FileExistsError):
        save_nfl_player_pool(_result(), "20260913T170000", output_root=tmp_path)


def test_list_and_load_latest_round_trip(tmp_path):
    save_nfl_player_pool(_result(), "20260913T170000", output_root=tmp_path)
    save_nfl_player_pool(_result(), "20260913T180000", output_root=tmp_path)

    pools = list_nfl_player_pools("2026-09-13", output_root=tmp_path)
    assert len(pools) == 2

    latest = load_latest_nfl_player_pool("2026-09-13", output_root=tmp_path)
    assert latest["draft_group_id"] == 151307
    assert latest["source_provenance"] == "DRAFTKINGS_UNOFFICIAL_LIVE"
    assert len(latest["players"]) == 1
    assert latest["players"][0]["draftkings_player_id"] == "1"
    assert latest["players"][0]["projection"] is None
    assert latest["players"][0]["ownership"] is None


def test_load_latest_returns_none_when_nothing_saved(tmp_path):
    assert load_latest_nfl_player_pool("2026-09-13", output_root=tmp_path) is None
