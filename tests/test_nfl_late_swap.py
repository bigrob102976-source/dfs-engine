"""NFL M14 -- targeted tests for nfl/late_swap.py, exercising Phase
14/15/16/23's scenarios against a synthetic multi-team pool."""

from dataclasses import replace as _dc_replace
from datetime import datetime, timezone

import pytest

from nfl.late_swap import LateSwapError, classify_slots, run_late_swap
from nfl.optimizer_models import NflOptimizerPlayer, NflOptimizerSettings, NflStackConfig
from nfl.saved_lineup_models import NflSavedLineup, NflSavedLineupSlot
from tests._nfl_stack_fixtures import multi_team_pool


def NflOptimizerPlayerReplace(player: NflOptimizerPlayer, **overrides) -> NflOptimizerPlayer:
    return _dc_replace(player, **overrides)

DG_ID = 151307
DATE = "2026-09-13"

G1_START = "2026-09-13T17:00:00+00:00"  # TMA @ TMB, 1:00 PM ET
G2_START = "2026-09-13T20:25:00+00:00"  # TMC @ TMD, 4:25 PM ET

_TEAM_GAME_START = {"TMA": G1_START, "TMB": G1_START, "TMC": G2_START, "TMD": G2_START}


def _slot_for(pool_player, roster_slot):
    return NflSavedLineupSlot(
        roster_slot=roster_slot, draftkings_player_id=pool_player.key, name=pool_player.name, team=pool_player.team,
        opponent=pool_player.opponent, game_id=pool_player.game_id, game_start_utc=_TEAM_GAME_START[pool_player.team],
        position=pool_player.position, salary=pool_player.salary,
        projection_snapshot=pool_player.projection, ceiling_snapshot=pool_player.ceiling,
        ownership_snapshot=pool_player.projected_ownership,
    )


def _build_saved_lineup(pool, mode="roster_feasibility", stack_config=None):
    """A real, legal 9-man lineup: 2 from TMA (G1), 2 from TMB (G1), 3 from TMC (G2), 2 from TMD (G2)."""
    by_key = {p.key: p for p in pool}
    slots = [
        _slot_for(by_key["TMA_qb"], "QB"),
        _slot_for(by_key["TMA_rb1"], "RB1"),
        _slot_for(by_key["TMB_rb1"], "RB2"),
        _slot_for(by_key["TMC_wr1"], "WR1"),
        _slot_for(by_key["TMC_wr2"], "WR2"),
        _slot_for(by_key["TMD_wr1"], "WR3"),
        _slot_for(by_key["TMC_te"], "TE"),
        _slot_for(by_key["TMD_rb1"], "FLEX"),
        _slot_for(by_key["TMD_dst"], "DST"),
    ]
    return NflSavedLineup(
        lineup_id="saved-1", sport="NFL", site="DraftKings", draft_group_id=DG_ID, slate_date=DATE,
        created_at="2026-09-10T00:00:00+00:00", updated_at="2026-09-10T00:00:00+00:00",
        mode=mode, stack_config=stack_config or {}, slots=slots,
    )


# ---------------------------------------------------------------------------
# Phase 14: time-based lock scenarios
# ---------------------------------------------------------------------------

def test_A_before_any_game_zero_locked():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)  # well before G1 (17:00 UTC)
    locked, unlocked = classify_slots(saved, now)
    assert len(locked) == 0
    assert len(unlocked) == 9


def test_B_after_early_games_lock_early_players_locked_late_swappable():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)  # after G1 (17:00), before G2 (20:25)
    locked, unlocked = classify_slots(saved, now)
    locked_teams = {s.team for s in locked}
    unlocked_teams = {s.team for s in unlocked}
    assert locked_teams == {"TMA", "TMB"}
    assert unlocked_teams == {"TMC", "TMD"}
    assert len(locked) == 3  # TMA_qb, TMA_rb1, TMB_rb1
    assert len(unlocked) == 6


def test_C_after_4pm_games_only_night_game_players_remain():
    """No true SNF/MNF game in this fixture (only 2 games) -- simulating
    'all remaining games locked' with a time after both G1 and G2."""
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 21, 0, 0, tzinfo=timezone.utc)  # after both G1 and G2
    locked, unlocked = classify_slots(saved, now)
    assert len(locked) == 9
    assert len(unlocked) == 0


def test_D_all_games_locked_produces_no_changes_and_reports_fully_locked():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 21, 0, 0, tzinfo=timezone.utc)
    result = run_late_swap(saved, pool, NflOptimizerSettings(), now)
    assert result.fully_locked is True
    assert result.lineup is None
    assert result.changed_player_keys == []


def test_partial_lock_late_swap_preserves_locked_reoptimizes_unlocked():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)  # G1 locked, G2 unlocked
    result = run_late_swap(saved, pool, NflOptimizerSettings(mode="roster_feasibility"), now)
    assert result.fully_locked is False
    assert result.lineup is not None
    assignments_by_slot = {a.slot: a.draftkings_player_id for a in result.lineup.assignments}
    # Locked slots must be EXACTLY preserved.
    assert assignments_by_slot["QB"] == "TMA_qb"
    assert assignments_by_slot["RB1"] == "TMA_rb1"
    assert assignments_by_slot["RB2"] == "TMB_rb1"
    # Salary is still <= cap for the WHOLE lineup.
    assert result.lineup.total_salary <= 50000


# ---------------------------------------------------------------------------
# Phase 15: injury status change scenarios
# ---------------------------------------------------------------------------

def test_unlocked_questionable_becomes_out_before_lock_gets_removed():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)  # TMC/TMD still unlocked

    # TMC_wr1 (an unlocked slot's player) just became OUT.
    updated_pool = [p for p in pool]
    for i, p in enumerate(updated_pool):
        if p.key == "TMC_wr1":
            updated_pool[i] = NflOptimizerPlayerReplace(p, raw_status="OUT")

    result = run_late_swap(saved, updated_pool, NflOptimizerSettings(mode="roster_feasibility"), now)
    assert result.lineup is not None
    new_keys = result.lineup.player_keys()
    assert "TMC_wr1" not in new_keys  # excluded -- OUT and unlocked


def test_locked_player_out_after_their_game_locked_is_preserved():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)  # TMA/TMB locked

    # TMA_qb (a LOCKED slot's player) becomes OUT after their game locked.
    updated_pool = [p for p in pool]
    for i, p in enumerate(updated_pool):
        if p.key == "TMA_qb":
            updated_pool[i] = NflOptimizerPlayerReplace(p, raw_status="OUT")

    result = run_late_swap(saved, updated_pool, NflOptimizerSettings(mode="roster_feasibility"), now)
    assert result.lineup is not None
    assignments_by_slot = {a.slot: a.draftkings_player_id for a in result.lineup.assignments}
    assert assignments_by_slot["QB"] == "TMA_qb"  # NEVER removed -- locked


# ---------------------------------------------------------------------------
# Phase 16: stacking during late swap
# ---------------------------------------------------------------------------

def test_stack_requirement_applies_to_unlocked_portion_when_feasible():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)  # TMC/TMD unlocked
    result = run_late_swap(
        saved, pool, NflOptimizerSettings(mode="roster_feasibility", stack=NflStackConfig(qb_stack_mode="single")), now,
    )
    # No unlocked QB slot exists in this saved lineup (QB is locked, TMA) --
    # the stack requirement is evaluated against whichever QB is actually
    # in the FINAL lineup (still TMA_qb, locked) -- must still produce a
    # legal, validated result without crashing.
    assert result.lineup is not None


# ---------------------------------------------------------------------------
# Phase 23: failure cases
# ---------------------------------------------------------------------------

def test_saved_player_missing_from_current_pool_reconstructed_from_snapshot():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)  # TMA/TMB locked

    # Simulate TMA_qb (locked) vanishing from the current live pool.
    reduced_pool = [p for p in pool if p.key != "TMA_qb"]
    result = run_late_swap(saved, reduced_pool, NflOptimizerSettings(mode="roster_feasibility"), now)
    assert result.lineup is not None
    assignments_by_slot = {a.slot: a.draftkings_player_id for a in result.lineup.assignments}
    assert assignments_by_slot["QB"] == "TMA_qb"  # reconstructed from the saved snapshot, still present


def test_wrong_draft_group_raises_clearly():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    saved.draft_group_id = 999999  # simulate a stale lineup from a different slate
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(LateSwapError):
        run_late_swap(saved, pool, NflOptimizerSettings(), now)


def test_impossible_salary_after_locks_reports_error_not_none_result():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)
    result = run_late_swap(saved, pool, NflOptimizerSettings(salary_cap=100), now)  # impossibly tight
    assert result.lineup is None
    assert result.error is not None


def test_all_players_locked_via_time_reports_fully_locked_not_error():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    now = datetime(2026, 9, 14, 6, 0, 0, tzinfo=timezone.utc)  # long after every game
    result = run_late_swap(saved, pool, NflOptimizerSettings(), now)
    assert result.fully_locked is True
    assert result.error is None


def test_duplicate_player_corruption_raises_before_any_solve():
    pool = multi_team_pool()
    saved = _build_saved_lineup(pool)
    saved.slots[1].draftkings_player_id = saved.slots[0].draftkings_player_id  # corrupt: RB1 == QB
    now = datetime(2026, 9, 13, 10, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(Exception):  # SavedLineupCorruptionError
        run_late_swap(saved, pool, NflOptimizerSettings(), now)


def test_missing_projection_on_unlocked_player_does_not_crash_projection_mode():
    pool = multi_team_pool(with_projections=True)
    saved = _build_saved_lineup(pool, mode="projection")
    now = datetime(2026, 9, 13, 18, 0, 0, tzinfo=timezone.utc)  # TMC/TMD unlocked

    updated_pool = [p for p in pool]
    for i, p in enumerate(updated_pool):
        if p.key == "TMC_wr1":
            updated_pool[i] = NflOptimizerPlayerReplace(p, projection=None, ceiling=None)

    result = run_late_swap(saved, updated_pool, NflOptimizerSettings(mode="projection"), now)
    assert result.lineup is not None
    assert "TMC_wr1" not in result.lineup.player_keys()  # excluded -- no usable projection
