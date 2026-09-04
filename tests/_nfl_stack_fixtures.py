"""NFL M13 -- shared synthetic multi-team pool for stacking/bring-back/
RB+DST/exposure/leverage tests. Four teams across two games, each team
with enough WR/TE depth to exercise single AND double QB stacks, plus
real opponents for bring-back. All synthetic (no real player data --
mirrors tests/test_nfl_solver.py's own discipline)."""

from typing import List, Optional

from nfl.optimizer_models import NflOptimizerPlayer

DG_ID = 151307
DATE = "2026-09-13"

# Game 1: TMA @ TMB. Game 2: TMC @ TMD.
_TEAM_OPPONENT = {"TMA": "TMB", "TMB": "TMA", "TMC": "TMD", "TMD": "TMC"}
_TEAM_GAME = {"TMA": "G1", "TMB": "G1", "TMC": "G2", "TMD": "G2"}


def _p(
    key: str, name: str, position: str, team: str, salary: int,
    projection: Optional[float] = None, ceiling: Optional[float] = None,
    projected_ownership: Optional[float] = None, leverage_score: Optional[float] = None,
) -> NflOptimizerPlayer:
    roster_slots = [position, "FLEX"] if position in ("RB", "WR", "TE") else [position]
    return NflOptimizerPlayer(
        key=key, name=name, team=team, opponent=_TEAM_OPPONENT[team], game_id=_TEAM_GAME[team],
        position=position, roster_slots=roster_slots, salary=salary, is_team_entity=(position == "DST"),
        draft_group_id=DG_ID, slate_date=DATE, projection=projection, ceiling=ceiling,
        projected_ownership=projected_ownership, leverage_score=leverage_score,
    )


def multi_team_pool(with_projections: bool = False, with_ownership: bool = False) -> List[NflOptimizerPlayer]:
    """4 teams x (1 QB, 2 RB, 3 WR, 1 TE, 1 DST) = 32 players. Salaries
    and (optionally) projections are varied so a specific "best" pick
    within each position/team is deterministic and testable."""
    players: List[NflOptimizerPlayer] = []
    team_specs = {
        "TMA": {"qb": 7500, "rb": [6500, 4800], "wr": [6800, 5400, 4200], "te": 4000, "dst": 3000},
        "TMB": {"qb": 7000, "rb": [6000, 4500], "wr": [6200, 5000, 3900], "te": 3700, "dst": 2800},
        "TMC": {"qb": 6800, "rb": [5800, 4300], "wr": [6000, 4800, 3700], "te": 3500, "dst": 2600},
        "TMD": {"qb": 6500, "rb": [5500, 4100], "wr": [5700, 4500, 3500], "te": 3300, "dst": 2400},
    }

    def maybe(value, enabled):
        return value if enabled else None

    for team, spec in team_specs.items():
        proj_qb = 18.0 + spec["qb"] / 1000.0 if with_projections else None
        players.append(_p(f"{team}_qb", f"{team} QB", "QB", team, spec["qb"], proj_qb, maybe(proj_qb + 8 if proj_qb else None, with_projections), maybe(2.5, with_ownership), maybe(10.0, with_ownership)))
        for i, sal in enumerate(spec["rb"], start=1):
            proj = 10.0 + sal / 1000.0 if with_projections else None
            players.append(_p(f"{team}_rb{i}", f"{team} RB{i}", "RB", team, sal, proj, maybe(proj + 6 if proj else None, with_projections), maybe(3.0, with_ownership), maybe(5.0, with_ownership)))
        for i, sal in enumerate(spec["wr"], start=1):
            proj = 8.0 + sal / 1000.0 if with_projections else None
            players.append(_p(f"{team}_wr{i}", f"{team} WR{i}", "WR", team, sal, proj, maybe(proj + 7 if proj else None, with_projections), maybe(2.8, with_ownership), maybe(6.0, with_ownership)))
        proj_te = 6.0 + spec["te"] / 1000.0 if with_projections else None
        players.append(_p(f"{team}_te", f"{team} TE", "TE", team, spec["te"], proj_te, maybe(proj_te + 5 if proj_te else None, with_projections), maybe(2.2, with_ownership), maybe(4.0, with_ownership)))
        proj_dst = 5.0 + spec["dst"] / 1000.0 if with_projections else None
        players.append(_p(f"{team}_dst", f"{team} DST", "DST", team, spec["dst"], proj_dst, maybe(proj_dst + 3 if proj_dst else None, with_projections), maybe(4.0, with_ownership), maybe(8.0, with_ownership)))

    return players
