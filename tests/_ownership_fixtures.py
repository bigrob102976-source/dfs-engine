"""Shared synthetic OwnershipInputPlayer builders for ownership/* tests.

Not a test module itself (no test_ prefix) -- pytest won't collect it.
"""

from ownership.models import OwnershipInputPlayer


def hitter(key, team, positions, salary, projection, opponent="OPP", game_id="g1",
           order=None, pa=300, overall=60.0, confidence=90.0, tags=None):
    return OwnershipInputPlayer(
        dk_player_id=key, mlb_player_id=key, name=key.replace("_", " ").title(), team=team, opponent=opponent,
        game_id=game_id, player_type="hitter", dk_positions=list(positions), salary=salary, projection=projection,
        ceiling=projection * 1.8, overall_score=overall, risk_score=30.0, confidence=confidence,
        batting_order=order, season_sample_size=pa, tags=list(tags or []),
    )


def pitcher(key, team, salary, projection, opponent="OPP", game_id="g2", overall=65.0, confidence=90.0, tags=None):
    return OwnershipInputPlayer(
        dk_player_id=key, mlb_player_id=key, name=key.replace("_", " ").title(), team=team, opponent=opponent,
        game_id=game_id, player_type="pitcher", dk_positions=["P"], salary=salary, projection=projection,
        ceiling=projection * 1.5, overall_score=overall, risk_score=25.0, confidence=confidence,
        batting_order=None, season_sample_size=None, tags=list(tags or []),
    )


def small_slate_pitchers():
    return [
        pitcher("p1", "TOR", 8500, 22.0, opponent="BOS", overall=75.0, tags=["elite_k_upside"]),
        pitcher("p2", "PIT", 7500, 18.0, opponent="MIA", overall=68.0),
        pitcher("p3", "ATL", 6800, 15.5, opponent="NYM", overall=60.0),
        pitcher("p4", "HOU", 5200, 12.0, opponent="SEA", overall=52.0),
    ]


def small_slate_hitters():
    hitters = []
    teams = {"PHI": [8.0, 7.5, 7.0, 6.5, 6.0, 5.5, 5.0], "NYY": [7.8, 7.2, 6.8, 6.0, 5.5]}
    positions_cycle = [["C"], ["1B"], ["2B"], ["3B"], ["SS"], ["OF"], ["OF"]]
    for team, projections in teams.items():
        for i, proj in enumerate(projections):
            pos = positions_cycle[i % len(positions_cycle)]
            hitters.append(hitter(f"{team.lower()}_{i}", team, pos, 3000 + i * 200, proj, order=i + 1))
    # sparse alternates so every position has >1 candidate
    hitters.append(hitter("cin_c", "CIN", ["C"], 2600, 5.0, order=6))
    hitters.append(hitter("cin_ss", "CIN", ["SS"], 2800, 5.4, order=2))
    return hitters
