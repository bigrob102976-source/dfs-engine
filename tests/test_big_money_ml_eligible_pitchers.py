"""Milestone 32.2B -- M30.1 eligibility filtering tests (starting-
pitcher-only inference, reliever exclusion, unmatched exclusion, bench
exclusion). No network calls -- writes a fake DK player pool JSON to
tmp_path in the exact shape load_latest_dfs_pool expects."""

import json

from big_money_ml.eligible_pitchers import build_eligibility_summary, get_eligible_starting_pitchers


def _write_pool(tmp_path, date, players):
    folder = tmp_path / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {"slate_date": date, "generated_at_utc": "2026-08-22T12:00:00Z", "player_count": len(players), "players": players}
    (folder / "dk_player_pool_20260822T120000.json").write_text(json.dumps(doc), encoding="utf-8")


def _pitcher_row(mlb_player_id="1", eligibility_status="STARTING_PITCHER", optimizer_eligible=True, **overrides):
    row = {
        "dk_player_id": f"dk{mlb_player_id}", "name": f"Pitcher {mlb_player_id}", "team": "NYY", "player_type": "pitcher",
        "salary": 9000, "mlb_player_id": mlb_player_id, "opponent": "BOS", "game_id": "12345",
        "throwing_hand": "R", "eligibility_status": eligibility_status, "optimizer_eligible": optimizer_eligible,
    }
    row.update(overrides)
    return row


def test_starting_pitcher_is_included(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_pitcher_row("1")])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert len(eligible) == 1
    assert eligible[0].mlb_player_id == "1"


def test_relief_pitcher_is_excluded(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_pitcher_row("2", eligibility_status="RELIEF_PITCHER", optimizer_eligible=False)])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_bench_pitcher_is_excluded(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_pitcher_row("3", eligibility_status="BENCH", optimizer_eligible=False)])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_unmatched_pitcher_row_is_excluded(tmp_path):
    row = _pitcher_row("4", eligibility_status="UNMATCHED", optimizer_eligible=False)
    row["mlb_player_id"] = None
    _write_pool(tmp_path, "2026-08-22", [row])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_lineup_unconfirmed_pitcher_is_excluded(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_pitcher_row("5", eligibility_status="LINEUP_UNCONFIRMED", optimizer_eligible=False)])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_hitters_are_never_included_even_if_optimizer_eligible(tmp_path):
    hitter_row = _pitcher_row("6", eligibility_status="STARTING_HITTER")
    hitter_row["player_type"] = "hitter"
    _write_pool(tmp_path, "2026-08-22", [hitter_row])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_starting_pitcher_without_optimizer_eligible_flag_is_excluded(tmp_path):
    """A row could theoretically carry eligibility_status='STARTING_PITCHER'
    but optimizer_eligible=False (defensive edge case) -- must still be
    excluded, since optimizer_eligible is the authoritative gate."""
    _write_pool(tmp_path, "2026-08-22", [_pitcher_row("7", eligibility_status="STARTING_PITCHER", optimizer_eligible=False)])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_no_pool_file_returns_empty_list_not_an_error(tmp_path):
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_eligibility_summary_counts_are_correct(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [
        _pitcher_row("1"), _pitcher_row("2", eligibility_status="RELIEF_PITCHER", optimizer_eligible=False),
        _pitcher_row("3", eligibility_status="BENCH", optimizer_eligible=False),
    ])
    summary = build_eligibility_summary("2026-08-22", dfs_input_root=tmp_path)
    assert summary.raw_dk_pitcher_rows == 3
    assert summary.starting_pitcher_count == 1
    assert summary.ml_eligible_pitcher_count == 1


def test_identity_uses_mlb_player_id_and_game_id_not_name(tmp_path):
    """Same-name protection: two different players sharing a name must
    resolve to two distinct eligible entries, distinguished by
    mlb_player_id/game_id -- never collapsed."""
    _write_pool(tmp_path, "2026-08-22", [
        _pitcher_row("100", name="Chris Sale", team="ATL", game_id="111"),
        _pitcher_row("200", name="Chris Sale", team="BOS", game_id="222"),
    ])
    eligible = get_eligible_starting_pitchers("2026-08-22", dfs_input_root=tmp_path)
    assert len(eligible) == 2
    ids = {(e.mlb_player_id, e.game_id) for e in eligible}
    assert ids == {("100", "111"), ("200", "222")}
