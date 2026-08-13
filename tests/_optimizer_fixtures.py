"""Shared synthetic player-pool builders for optimizer/* tests.

Not a test module itself (no test_ prefix) -- pytest won't collect it.
All salaries/projections are invented purely for exercising solver
mechanics; they carry no relationship to any real player or slate.
"""

from optimizer.models import OptimizerPlayer


def hitter(key, team, positions, salary, projection, opponent="OPP", game_id="g0",
           ceiling=None, floor=None, risk=30.0, confidence=90.0, season_pa=300):
    return OptimizerPlayer(
        key=key, mlb_player_id=key, name=key.replace("_", " ").title(), team=team, opponent=opponent,
        game_id=game_id, player_type="hitter", dk_positions=list(positions), salary=salary,
        projection=projection, ceiling=ceiling if ceiling is not None else projection * 1.8,
        floor=floor if floor is not None else projection * 0.5, risk_score=risk, confidence=confidence,
        season_sample_size=season_pa,
    )


def pitcher(key, team, salary, projection, opponent="OPP", game_id="g0",
            ceiling=None, floor=None, risk=25.0, confidence=95.0):
    return OptimizerPlayer(
        key=key, mlb_player_id=key, name=key.replace("_", " ").title(), team=team, opponent=opponent,
        game_id=game_id, player_type="pitcher", dk_positions=["P"], salary=salary,
        projection=projection, ceiling=ceiling if ceiling is not None else projection * 1.5,
        floor=floor if floor is not None else projection * 0.6, risk_score=risk, confidence=confidence,
        season_sample_size=None,
    )


def feasible_pool():
    """A small but genuinely varied pool: two 'stackable' teams (PHI: 7
    hitters, NYY: 5 hitters), enough alternates at every position to
    build several distinct legal lineups, and a pitcher/hitter pair that
    directly conflict (p_tor vs conflict_hitter) for conflict tests."""
    players = [
        pitcher("p_tor", "TOR", 7500, 20.0, opponent="BOS", game_id="g1"),
        pitcher("p_pit", "PIT", 7000, 18.0, opponent="MIA", game_id="g2"),
        pitcher("p_atl", "ATL", 6800, 17.5, opponent="NYM", game_id="g3"),
        pitcher("p_hou", "HOU", 7200, 19.0, opponent="SEA", game_id="g7"),

        hitter("conflict_hitter", "BOS", ["OF"], 3000, 9.0, opponent="TOR", game_id="g1"),

        hitter("phi_c", "PHI", ["C"], 2500, 8.0, opponent="STL", game_id="g4"),
        hitter("phi_1b", "PHI", ["1B"], 3000, 9.0, opponent="STL", game_id="g4"),
        hitter("phi_2b", "PHI", ["2B"], 2800, 8.5, opponent="STL", game_id="g4"),
        hitter("phi_3b", "PHI", ["3B"], 2900, 8.2, opponent="STL", game_id="g4"),
        hitter("phi_ss", "PHI", ["SS"], 3200, 9.5, opponent="STL", game_id="g4"),
        hitter("phi_of1", "PHI", ["OF"], 3600, 10.0, opponent="STL", game_id="g4"),
        hitter("phi_of2", "PHI", ["OF"], 3400, 9.8, opponent="STL", game_id="g4"),

        hitter("nyy_c", "NYY", ["C"], 2600, 7.5, opponent="SEA", game_id="g5"),
        hitter("nyy_1b", "NYY", ["1B"], 3100, 9.2, opponent="SEA", game_id="g5"),
        hitter("nyy_of1", "NYY", ["OF"], 3700, 10.2, opponent="SEA", game_id="g5"),
        hitter("nyy_of2", "NYY", ["OF"], 3500, 9.9, opponent="SEA", game_id="g5"),
        hitter("nyy_of3", "NYY", ["OF"], 3300, 9.4, opponent="SEA", game_id="g5"),

        hitter("bal_2b", "BAL", ["2B"], 2700, 8.0, opponent="MIN", game_id="g6"),
        hitter("cin_3b", "CIN", ["3B"], 2600, 7.8, opponent="CWS", game_id="g6"),
        hitter("cws_ss", "CWS", ["SS"], 3000, 8.8, opponent="CIN", game_id="g6"),
        hitter("min_1b_of", "MIN", ["1B", "OF"], 2400, 7.2, opponent="BAL", game_id="g6"),
    ]
    return players


def team_max_pool():
    """PHI structurally capable of filling 7 of 8 hitter slots (5
    non-OF + 2 OF) if the team-hitter-max constraint didn't exist, with
    much higher projections than any alternative -- used to prove the
    solver never selects more than DK_MAX_HITTERS_PER_TEAM from one team."""
    players = [
        pitcher("p1", "TOR", 6000, 15.0, opponent="BOS", game_id="g1"),
        pitcher("p2", "PIT", 6000, 15.0, opponent="MIA", game_id="g2"),

        hitter("phi_c", "PHI", ["C"], 2500, 20.0, opponent="STL", game_id="g4"),
        hitter("phi_1b", "PHI", ["1B"], 2500, 20.0, opponent="STL", game_id="g4"),
        hitter("phi_2b", "PHI", ["2B"], 2500, 20.0, opponent="STL", game_id="g4"),
        hitter("phi_3b", "PHI", ["3B"], 2500, 20.0, opponent="STL", game_id="g4"),
        hitter("phi_ss", "PHI", ["SS"], 2500, 20.0, opponent="STL", game_id="g4"),
        hitter("phi_of1", "PHI", ["OF"], 2500, 20.0, opponent="STL", game_id="g4"),
        hitter("phi_of2", "PHI", ["OF"], 2500, 20.0, opponent="STL", game_id="g4"),

        # Cheap, low-projection alternates -- only used because the team cap forces it.
        hitter("alt_c", "NYY", ["C"], 2000, 1.0, opponent="SEA", game_id="g5"),
        hitter("alt_1b", "NYY", ["1B"], 2000, 1.0, opponent="SEA", game_id="g5"),
        hitter("alt_2b", "NYY", ["2B"], 2000, 1.0, opponent="SEA", game_id="g5"),
        hitter("alt_3b", "NYY", ["3B"], 2000, 1.0, opponent="SEA", game_id="g5"),
        hitter("alt_ss", "NYY", ["SS"], 2000, 1.0, opponent="SEA", game_id="g5"),
        hitter("alt_of1", "NYY", ["OF"], 2000, 1.0, opponent="SEA", game_id="g5"),
        hitter("alt_of2", "NYY", ["OF"], 2000, 1.0, opponent="SEA", game_id="g5"),
        hitter("alt_of3", "NYY", ["OF"], 2000, 1.0, opponent="SEA", game_id="g5"),
    ]
    return players
