"""Milestone 31.2C -- scripts/discover_dk_slate_dates.py. Mocks
draftkings_unofficial.client directly (no network), matching this
repo's existing DK-unofficial test convention (see
tests/test_dk_unofficial_collector.py)."""

import importlib
import json

import pytest

from draftkings_unofficial import client, collector
from draftkings_unofficial.models import DkGameType, DkSlate

discover_script = importlib.import_module("scripts.discover_dk_slate_dates")


def _slate(draft_group_id, game_type_id, start_date_est, tag="", label="", game_count=1, game_type_name="Classic"):
    return DkSlate(
        draft_group_id=draft_group_id, sport_id=2, sport_code="MLB", game_type_id=game_type_id,
        game_type_name=game_type_name, start_time="2026-08-21T00:00:00Z", tag=tag, label=label,
        game_count=game_count, raw={"StartDateEst": start_date_est},
    )


CLASSIC_GT = DkGameType(game_type_id=2, sport_id=2, name="Classic", draft_type="SalaryCap")
SHOWDOWN_GT = DkGameType(game_type_id=3, sport_id=2, name="Showdown Captain Mode", draft_type="SalaryCap")
TIERS_GT = DkGameType(game_type_id=4, sport_id=2, name="Tiers", draft_type="Tiered")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("DFS_SALARY_PROVIDER", raising=False)
    monkeypatch.delenv("DK_UNOFFICIAL_ENABLED", raising=False)


def test_active_by_default_with_no_provider_override(monkeypatch, capsys):
    """Milestone M1: DraftKings Unofficial is the permanent default --
    with no DFS_SALARY_PROVIDER set at all (the normal production state)
    and Mock Mode off, this script does real discovery work, not
    "not_applicable"."""
    universe = collector.SportUniverseResult(status=collector.STATUS_NO_ACTIVE_SLATE, sport_code="MLB")
    calls = []
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code: (calls.append(sport_code), universe)[1])
    import sys
    monkeypatch.setattr(sys, "argv", ["discover_dk_slate_dates.py", "--sport", "MLB"])
    discover_script.main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["status"] == "no_active_slate"
    assert calls == ["MLB"]  # real discovery was actually attempted


def test_not_applicable_when_a_different_provider_is_explicitly_selected(monkeypatch, capsys):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "mock")
    calls = []
    monkeypatch.setattr(client, "get_contests", lambda sport_code: calls.append(sport_code))
    import sys
    monkeypatch.setattr(sys, "argv", ["discover_dk_slate_dates.py", "--sport", "MLB"])
    discover_script.main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["status"] == "not_applicable"
    assert out["dates"] == []
    assert calls == []  # zero network calls when a different provider is active


def test_not_applicable_when_mock_mode_is_explicitly_enabled(monkeypatch, capsys):
    # Mirrors dfs/providers/config.py: Mock Mode wins before DraftKings
    # Unofficial is even attempted.
    monkeypatch.setattr(discover_script, "is_mock_mode_enabled", lambda: True)
    calls = []
    monkeypatch.setattr(client, "get_contests", lambda sport_code: calls.append(sport_code))
    import sys
    monkeypatch.setattr(sys, "argv", ["discover_dk_slate_dates.py"])
    discover_script.main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["status"] == "not_applicable"
    assert calls == []


def test_not_applicable_when_kill_switch_is_off(monkeypatch, capsys):
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "false")  # explicit operational kill switch
    calls = []
    monkeypatch.setattr(client, "get_contests", lambda sport_code: calls.append(sport_code))
    import sys
    monkeypatch.setattr(sys, "argv", ["discover_dk_slate_dates.py"])
    discover_script.main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["status"] == "not_applicable"
    assert calls == []


def test_groups_by_date_and_ranks_featured_first(monkeypatch, capsys):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "draftkings_unofficial")
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")

    universe = collector.SportUniverseResult(
        status=collector.STATUS_OK, sport_code="MLB",
        slates=[
            _slate(1, 2, "2026-08-21T18:00:00", tag="", label="", game_count=13, game_type_name="Classic"),  # bare "Main Classic"
            _slate(2, 2, "2026-08-21T19:00:00", tag="Featured", game_count=13),
            _slate(3, 2, "2026-08-21T23:00:00", label=" (Night)", game_count=4),
            _slate(4, 2, "2026-08-21T23:30:00", label=" (Late Night)", game_count=2),
            _slate(5, 2, "2026-08-21T18:30:00", label=" (Turbo)", game_count=4),
            _slate(6, 3, "2026-08-21T19:00:00", label=" (Showdown)", game_type_name="Showdown Captain Mode", game_count=1),  # excluded
            _slate(7, 4, "2026-08-21T19:00:00", game_type_name="Tiers", game_count=13),  # excluded (not SalaryCap)
            _slate(8, 2, "2026-08-22T18:00:00", tag="Featured", game_count=11),  # a different date
        ],
        game_types=[CLASSIC_GT, SHOWDOWN_GT, TIERS_GT],
    )
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code: universe)

    import sys
    monkeypatch.setattr(sys, "argv", ["discover_dk_slate_dates.py", "--sport", "MLB"])
    discover_script.main()
    out = json.loads(capsys.readouterr().out.strip())

    assert out["status"] == "ok"
    by_date = {d["date"]: d for d in out["dates"]}
    assert set(by_date) == {"2026-08-21", "2026-08-22"}

    day1 = by_date["2026-08-21"]
    assert day1["slate_count"] == 7  # all 2026-08-21 slates, including excluded ones
    assert day1["salary_cap_slate_count"] == 5  # Showdown + Tiers excluded
    assert day1["has_usable_slate"] is True
    assert day1["best_slate_id"] == "dkunofficial-2"  # the Featured-tagged one wins
    assert day1["best_slate_label"] == "Featured"
    assert day1["best_game_count"] == 13

    day2 = by_date["2026-08-22"]
    assert day2["best_slate_id"] == "dkunofficial-8"


def test_no_active_slate_is_reported_not_raised(monkeypatch, capsys):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "draftkings_unofficial")
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    monkeypatch.setattr(
        collector, "collect_sport_universe",
        lambda sport_code: collector.SportUniverseResult(status=collector.STATUS_NO_ACTIVE_SLATE, sport_code=sport_code),
    )
    import sys
    monkeypatch.setattr(sys, "argv", ["discover_dk_slate_dates.py"])
    discover_script.main()
    out = json.loads(capsys.readouterr().out.strip())
    assert out["status"] == "no_active_slate"
    assert out["dates"] == []


def test_date_with_only_non_salary_cap_slates_is_not_usable(monkeypatch, capsys):
    monkeypatch.setenv("DFS_SALARY_PROVIDER", "draftkings_unofficial")
    monkeypatch.setenv("DK_UNOFFICIAL_ENABLED", "true")
    universe = collector.SportUniverseResult(
        status=collector.STATUS_OK, sport_code="MLB",
        slates=[_slate(1, 4, "2026-08-21T18:00:00", game_type_name="Tiers", game_count=13)],
        game_types=[CLASSIC_GT, TIERS_GT],
    )
    monkeypatch.setattr(collector, "collect_sport_universe", lambda sport_code: universe)
    import sys
    monkeypatch.setattr(sys, "argv", ["discover_dk_slate_dates.py"])
    discover_script.main()
    out = json.loads(capsys.readouterr().out.strip())
    day = out["dates"][0]
    assert day["has_usable_slate"] is False
    assert day["best_slate_id"] is None


def test_slate_local_date_prefers_start_date_est(monkeypatch):
    s = _slate(1, 2, "2026-08-21T18:00:00")
    assert collector.slate_local_date(s) == "2026-08-21"


def test_slate_local_date_falls_back_to_start_time(monkeypatch):
    s = DkSlate(
        draft_group_id=1, sport_id=2, sport_code="MLB", game_type_id=2, game_type_name="Classic",
        start_time="2026-08-22T02:00:00Z", raw={},
    )
    assert collector.slate_local_date(s) == "2026-08-22"


def test_slate_local_date_none_when_no_date_available():
    s = DkSlate(draft_group_id=1, sport_id=2, sport_code="MLB", game_type_id=2, game_type_name="Classic", start_time=None, raw={})
    assert collector.slate_local_date(s) is None
