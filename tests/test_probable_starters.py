"""PROBABLE FIX milestone: tests for dfs/probable_starters.py -- real,
evidence-based probable-hitter inference. All network calls
(fetch_team_recent_schedule/fetch_boxscore/fetch_team_roster/
fetch_batter_platoon_split) are monkeypatched to fixed, real-shaped
fixtures -- never a live network call in a test."""

import dfs.probable_starters as ps


def _schedule(*final_games):
    """final_games: list of (gamePk, officialDate) tuples, already Final."""
    return {"dates": [{"games": [
        {"gamePk": pk, "officialDate": d, "status": {"detailedState": "Final"}}
        for pk, d in final_games
    ]}]}


def _boxscore(team_id, side, batting_order_ids):
    return {"teams": {side: {"team": {"id": int(team_id)}, "battingOrder": batting_order_ids}}}


def _roster(*active_ids):
    return {"roster": [{"person": {"id": int(pid)}} for pid in active_ids]}


def _patch_no_platoon(monkeypatch):
    """Most tests don't care about the platoon signal -- return None so
    it never fires (isolates the recent-starts logic being tested)."""
    monkeypatch.setattr(ps, "fetch_batter_platoon_split", lambda *a, **k: None)


def _patch_cache_passthrough(monkeypatch):
    """dfs/probable_starters.py caches boxscores on disk by (date, key) --
    tests use a fresh tmp cache root per call via cache_root param instead
    of monkeypatching cache.get_or_fetch, so the real caching code path is
    still exercised."""


class TestClassifyConfidence:
    def test_high_when_started_most_recent_and_at_least_two_total(self):
        assert ps._classify_confidence([True, True, True]) == ps.HIGH
        assert ps._classify_confidence([True, False, True]) == ps.HIGH

    def test_medium_when_started_most_recent_but_only_one_data_point(self):
        assert ps._classify_confidence([True]) == ps.MEDIUM
        assert ps._classify_confidence([True, False]) == ps.MEDIUM

    def test_low_when_missed_most_recent(self):
        assert ps._classify_confidence([False, True, True]) == ps.LOW
        assert ps._classify_confidence([False]) == ps.LOW


class TestInferProbableHittersForTeam:
    def test_no_recent_games_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: {"dates": []})
        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", cache_root=tmp_path)
        assert result == {}

    def test_real_evidence_only_never_a_guess_with_no_basis(self, monkeypatch, tmp_path):
        """A player who never appears in ANY recent boxscore's starting
        order is never included in the result at all."""
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule((1001, "2026-09-04")))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: _boxscore("100", "home", [111, 222, 333]))
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(111, 222, 333, 444))
        _patch_no_platoon(monkeypatch)

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", cache_root=tmp_path)
        assert set(result.keys()) == {"111", "222", "333"}
        assert "444" not in result  # on roster, but never started recently -- no basis, correctly excluded

    def test_high_confidence_consistent_recent_starter(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule(
            (1003, "2026-09-04"), (1002, "2026-09-02"), (1001, "2026-08-31"),
        ))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: _boxscore("100", "home", [111]))
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(111))
        _patch_no_platoon(monkeypatch)

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", cache_root=tmp_path)
        assert result["111"].confidence == ps.HIGH
        assert result["111"].on_active_roster is True
        assert result["111"].projected_batting_order == 1
        assert "3 of the last 3" in result["111"].reason

    def test_medium_confidence_single_recent_start(self, monkeypatch, tmp_path):
        boxscores = {"1003": _boxscore("100", "home", [111]), "1002": _boxscore("100", "home", []), "1001": _boxscore("100", "home", [])}
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule(
            (1003, "2026-09-04"), (1002, "2026-09-02"), (1001, "2026-08-31"),
        ))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: boxscores[gid])
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(111))
        _patch_no_platoon(monkeypatch)

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", cache_root=tmp_path)
        assert result["111"].confidence == ps.MEDIUM

    def test_low_confidence_missed_most_recent_game(self, monkeypatch, tmp_path):
        boxscores = {"1003": _boxscore("100", "home", []), "1002": _boxscore("100", "home", [111]), "1001": _boxscore("100", "home", [111])}
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule(
            (1003, "2026-09-04"), (1002, "2026-09-02"), (1001, "2026-08-31"),
        ))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: boxscores[gid])
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(111))
        _patch_no_platoon(monkeypatch)

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", cache_root=tmp_path)
        assert result["111"].confidence == ps.LOW
        assert "did not start the most recent" in result["111"].reason

    def test_off_active_roster_becomes_out_never_optimizer_style_eligible(self, monkeypatch, tmp_path):
        """Real recent starts exist, but the player is NOT on today's
        active roster -- on_active_roster=False, confidence is not the
        signal that matters here (dfs/eligibility.py maps this to OUT)."""
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule((1001, "2026-09-04")))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: _boxscore("100", "home", [111]))
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(222))  # 111 traded/injured/optioned
        _patch_no_platoon(monkeypatch)

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", cache_root=tmp_path)
        assert result["111"].on_active_roster is False
        assert result["111"].projected_batting_order is None
        assert "NOT on today's active roster" in result["111"].reason

    def test_contested_slot_surfaces_both_candidates_honestly(self, monkeypatch, tmp_path):
        """Real lineup turnover across the recent window (two different
        players hit leadoff) -- both are honestly surfaced, not collapsed
        into one guess."""
        boxscores = {
            "1002": _boxscore("100", "home", [222]),
            "1001": _boxscore("100", "home", [111]),
        }
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule(
            (1002, "2026-09-04"), (1001, "2026-08-31"),
        ))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: boxscores[gid])
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(111, 222))
        _patch_no_platoon(monkeypatch)

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", cache_root=tmp_path)
        assert result["222"].confidence == ps.MEDIUM  # started the most recent game, only 1 data point
        assert result["111"].confidence == ps.LOW  # missed the most recent game

    def test_platoon_disadvantage_downgrades_confidence_with_real_sample(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule(
            (1002, "2026-09-04"), (1001, "2026-08-31"),
        ))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: _boxscore("100", "home", [111]))
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(111))

        class FakeLine:
            def __init__(self, pa, ops):
                self.plate_appearances = pa
                self.ops = ops

        def fake_parse(raw, player_id, season, sit_code, retrieved_at):
            return raw  # raw already shaped as FakeLine below

        monkeypatch.setattr(ps, "fetch_batter_platoon_split", lambda *a, **k: object())
        monkeypatch.setattr(ps, "parse_platoon_split", lambda raw, pid, season, sit, ts: (
            FakeLine(200, 0.700) if sit == "vr" else FakeLine(200, 0.950)
        ))

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", opposing_pitcher_throws="R", cache_root=tmp_path)
        assert result["111"].confidence == ps.MEDIUM  # would be HIGH without the real platoon disadvantage
        assert "platoon split" in result["111"].reason

    def test_thin_platoon_sample_never_downgrades(self, monkeypatch, tmp_path):
        """A tiny sample size must never be treated as real evidence."""
        monkeypatch.setattr(ps, "fetch_team_recent_schedule", lambda *a, **k: _schedule(
            (1002, "2026-09-04"), (1001, "2026-08-31"),
        ))
        monkeypatch.setattr(ps, "fetch_boxscore", lambda gid: _boxscore("100", "home", [111]))
        monkeypatch.setattr(ps, "fetch_team_roster", lambda *a, **k: _roster(111))

        class FakeLine:
            def __init__(self, pa, ops):
                self.plate_appearances = pa
                self.ops = ops

        monkeypatch.setattr(ps, "fetch_batter_platoon_split", lambda *a, **k: object())
        monkeypatch.setattr(ps, "parse_platoon_split", lambda raw, pid, season, sit, ts: (
            FakeLine(8, 0.500) if sit == "vr" else FakeLine(8, 0.950)
        ))

        result = ps.infer_probable_hitters_for_team("100", "2026-09-05", opposing_pitcher_throws="R", cache_root=tmp_path)
        assert result["111"].confidence == ps.HIGH  # thin sample (8 PA) never downgrades


class TestBuildProbableHittersMap:
    def test_skips_teams_whose_lineup_already_posted(self, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(ps, "infer_probable_hitters_for_team", lambda team_id, *a, **k: calls.append(team_id) or {})

        package = {
            "games": [{"game_id": "g1", "home_team_abbr": "BOS", "home_team_id": "111", "away_team_abbr": "TOR", "away_team_id": "222"}],
            "pitchers": [],
            "batters": [{"game_id": "g1", "team_abbr": "BOS", "player_id": "p1", "batting_order": 1}],  # BOS lineup already posted
        }
        ps.build_probable_hitters_map("2026-09-05", package)
        assert calls == ["222"]  # only TOR (unposted) gets a real lookup call

    def test_passes_real_opposing_throws(self, monkeypatch, tmp_path):
        captured_by_team = {}

        def fake_infer(team_id, date, opposing_pitcher_throws=None, **kwargs):
            captured_by_team[team_id] = opposing_pitcher_throws
            return {}
        monkeypatch.setattr(ps, "infer_probable_hitters_for_team", fake_infer)

        package = {
            "games": [{"game_id": "g1", "home_team_abbr": "BOS", "home_team_id": "111", "away_team_abbr": "TOR", "away_team_id": "222"}],
            "pitchers": [{"game_id": "g1", "team_abbr": "TOR", "player_id": "p-tor", "throws": "L"}],
            "batters": [],
        }
        ps.build_probable_hitters_map("2026-09-05", package)
        assert captured_by_team["111"] == "L"  # BOS (home) faces TOR's real probable starter, who throws L
        assert captured_by_team["222"] is None  # TOR (away) faces BOS, whose probable starter isn't known here

    def test_one_teams_failure_never_blocks_the_others(self, monkeypatch, tmp_path):
        def flaky_infer(team_id, *a, **k):
            if team_id == "111":
                raise RuntimeError("network blew up")
            return {"p2": ps.ProbableHitterInfo("p2", "Real Player", True, 3, ps.HIGH, "real evidence", 3, 3)}

        monkeypatch.setattr(ps, "infer_probable_hitters_for_team", flaky_infer)
        package = {
            "games": [{"game_id": "g1", "home_team_abbr": "BOS", "home_team_id": "111", "away_team_abbr": "TOR", "away_team_id": "222"}],
            "pitchers": [], "batters": [],
        }
        result = ps.build_probable_hitters_map("2026-09-05", package)
        assert ("g1", "p2") in result
        assert result[("g1", "p2")].confidence == ps.HIGH
