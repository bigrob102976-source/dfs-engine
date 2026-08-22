"""Milestone 32.3B -- M30.1 eligibility filtering tests for hitters
(starting-hitter-only inference, bench/unconfirmed/unmatched
exclusion). No network calls -- writes a fake DK player pool JSON to
tmp_path in the exact shape load_latest_dfs_pool expects. Mirrors
tests/test_big_money_ml_eligible_pitchers.py exactly."""

import json

from big_money_ml.eligible_hitters import build_hitter_eligibility_summary, get_eligible_starting_hitters


def _write_pool(tmp_path, date, players):
    folder = tmp_path / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {"slate_date": date, "generated_at_utc": "2026-08-22T12:00:00Z", "player_count": len(players), "players": players}
    (folder / "dk_player_pool_20260822T120000.json").write_text(json.dumps(doc), encoding="utf-8")


def _hitter_row(mlb_player_id="1", eligibility_status="STARTING_HITTER", optimizer_eligible=True, **overrides):
    row = {
        "dk_player_id": f"dk{mlb_player_id}", "name": f"Hitter {mlb_player_id}", "team": "NYY", "player_type": "hitter",
        "salary": 4500, "mlb_player_id": mlb_player_id, "opponent": "BOS", "game_id": "12345",
        "batting_hand": "R", "batting_order": 3, "eligibility_status": eligibility_status, "optimizer_eligible": optimizer_eligible,
    }
    row.update(overrides)
    return row


def test_starting_hitter_is_included(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_hitter_row("1")])
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert len(eligible) == 1
    assert eligible[0].mlb_player_id == "1"
    assert eligible[0].batting_order == 3


def test_bench_hitter_is_excluded(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_hitter_row("2", eligibility_status="BENCH", optimizer_eligible=False)])
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_unmatched_hitter_row_is_excluded(tmp_path):
    row = _hitter_row("3", eligibility_status="UNMATCHED", optimizer_eligible=False)
    row["mlb_player_id"] = None
    _write_pool(tmp_path, "2026-08-22", [row])
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_lineup_unconfirmed_hitter_is_excluded(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_hitter_row("4", eligibility_status="LINEUP_UNCONFIRMED", optimizer_eligible=False, batting_order=None)])
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_pitchers_are_never_included_even_if_optimizer_eligible(tmp_path):
    pitcher_row = _hitter_row("5", eligibility_status="STARTING_PITCHER")
    pitcher_row["player_type"] = "pitcher"
    _write_pool(tmp_path, "2026-08-22", [pitcher_row])
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_starting_hitter_without_optimizer_eligible_flag_is_excluded(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [_hitter_row("6", eligibility_status="STARTING_HITTER", optimizer_eligible=False)])
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_no_pool_file_returns_empty_list_not_an_error(tmp_path):
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert eligible == []


def test_eligibility_summary_counts_are_correct(tmp_path):
    _write_pool(tmp_path, "2026-08-22", [
        _hitter_row("1"), _hitter_row("2", eligibility_status="BENCH", optimizer_eligible=False),
        _hitter_row("3", eligibility_status="LINEUP_UNCONFIRMED", optimizer_eligible=False, batting_order=None),
    ])
    summary = build_hitter_eligibility_summary("2026-08-22", dfs_input_root=tmp_path)
    assert summary.raw_dk_hitter_rows == 3
    assert summary.confirmed_starting_hitter_count == 1
    assert summary.unconfirmed_hitter_count == 1
    assert summary.ml_eligible_hitter_count == 1


def test_identity_uses_mlb_player_id_and_game_id_not_name(tmp_path):
    """Same-name protection: two different players sharing a name must
    resolve to two distinct eligible entries, distinguished by
    mlb_player_id/game_id -- never collapsed."""
    _write_pool(tmp_path, "2026-08-22", [
        _hitter_row("100", name="Will Smith", team="LAD", game_id="111"),
        _hitter_row("200", name="Will Smith", team="ATL", game_id="222"),
    ])
    eligible = get_eligible_starting_hitters("2026-08-22", dfs_input_root=tmp_path)
    assert len(eligible) == 2
    ids = {(e.mlb_player_id, e.game_id) for e in eligible}
    assert ids == {("100", "111"), ("200", "222")}
