"""Milestone 27.3/27.4 fallout -- source-level realism sanity checks for
a parsed DraftKings salary CSV, run BEFORE anything is normalized or
matched to MLB identity.

M27.3 fixed how the pipeline INTERPRETS DK rows (player_type, team,
game_id) faithfully. Live validation then surfaced that the CSV
currently loaded is itself structurally implausible for a genuine MLB
DK Classic export -- e.g. 30 pitcher-eligible rows salaried for one team
in a single game (no real MLB team salaries anywhere close to its full
organizational pitching depth for one slate; DK typically lists the
probable starter plus a handful of notable relievers per team). Faithful
downstream preservation of an implausible source is still garbage in,
garbage out -- this module gives that a name and a place to surface it,
rather than silently trusting "it parsed" as "it's real".

This module can only ever find reasons to DISTRUST a source (WARN or
BLOCK); it never "corrects" a row's values -- see
dfs/providers/source_provenance.py for how a BLOCK downgrades the
overall provenance classification.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional

from dfs.models import DKSalaryRow
from dfs.player_resolver import PITCHER_DK_POSITIONS

WARN = "WARN"
BLOCK = "BLOCK"

# Named, documented thresholds -- not scattered magic numbers. A real DK
# Classic MLB slate salaries roughly a team's active-roster-adjacent
# player pool per game (typically 20-30 hitters + a handful of pitchers
# per team), never anywhere close to an entire organizational pitching
# staff for one game.
MAX_PLAUSIBLE_PITCHERS_PER_TEAM_WARN = 12
MAX_PLAUSIBLE_PITCHERS_PER_TEAM_BLOCK = 18
MAX_PLAUSIBLE_PLAYERS_PER_GAME_WARN = 70  # both teams combined, per game
MAX_PLAUSIBLE_PLAYERS_PER_GAME_BLOCK = 100
MAX_PLAUSIBLE_PITCHER_FRACTION_BLOCK = 0.40  # of the whole slate
# Below this many total rows, a pitcher-fraction percentage is too noisy
# to judge (e.g. a 2-row test fixture with 1 pitcher is "50%" but proves
# nothing) -- only meaningful at real-slate scale.
MIN_ROWS_FOR_FRACTION_CHECK = 20


@dataclass
class RealismFinding:
    level: str  # WARN | BLOCK
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "message": self.message}


@dataclass
class RealismReport:
    findings: List[RealismFinding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.level == BLOCK for f in self.findings)

    def to_dict(self) -> dict:
        return {"blocked": self.blocked, "findings": [f.to_dict() for f in self.findings]}


def _is_pitcher_row(row: DKSalaryRow) -> bool:
    return bool(PITCHER_DK_POSITIONS.intersection(row.dk_positions))


def check_source_realism(dk_rows: List[DKSalaryRow], game_count: Optional[int] = None) -> RealismReport:
    findings: List[RealismFinding] = []
    total = len(dk_rows)
    if total == 0:
        return RealismReport(findings)

    by_team: dict = defaultdict(list)
    for row in dk_rows:
        by_team[row.team_abbrev].append(row)

    pitcher_count = sum(1 for row in dk_rows if _is_pitcher_row(row))

    for team, rows in sorted(by_team.items()):
        team_pitchers = sum(1 for r in rows if _is_pitcher_row(r))
        if team_pitchers >= MAX_PLAUSIBLE_PITCHERS_PER_TEAM_BLOCK:
            findings.append(RealismFinding(
                BLOCK, f"Team '{team}' has {team_pitchers} pitcher-eligible rows salaried for this slate -- "
                       f"no real MLB team's active pitching staff is anywhere near that large."))
        elif team_pitchers >= MAX_PLAUSIBLE_PITCHERS_PER_TEAM_WARN:
            findings.append(RealismFinding(
                WARN, f"Team '{team}' has {team_pitchers} pitcher-eligible rows -- unusually high for a real DK slate."))

    if game_count and game_count > 0:
        per_game = total / game_count
        if per_game >= MAX_PLAUSIBLE_PLAYERS_PER_GAME_BLOCK:
            findings.append(RealismFinding(
                BLOCK, f"{total} total rows across {game_count} game(s) ({per_game:.0f}/game) is far beyond a "
                       f"plausible real DK Classic MLB slate."))
        elif per_game >= MAX_PLAUSIBLE_PLAYERS_PER_GAME_WARN:
            findings.append(RealismFinding(
                WARN, f"{total} total rows across {game_count} game(s) ({per_game:.0f}/game) is unusually high."))

        team_count = len(by_team)
        expected_teams = game_count * 2
        if team_count != expected_teams:
            findings.append(RealismFinding(
                WARN, f"{team_count} distinct team(s) across {game_count} game(s) -- expected exactly "
                      f"{expected_teams} (2 per game) for a genuine MLB Classic slate."))

    if total >= MIN_ROWS_FOR_FRACTION_CHECK and (pitcher_count / total) >= MAX_PLAUSIBLE_PITCHER_FRACTION_BLOCK:
        findings.append(RealismFinding(
            BLOCK, f"{pitcher_count}/{total} rows ({100 * pitcher_count / total:.0f}%) are pitcher-eligible -- "
                   f"far above a real DK slate's typical pitcher share."))

    name_teams: dict = defaultdict(set)
    for row in dk_rows:
        name_teams[row.name].add(row.team_abbrev)
    for name, teams in sorted(name_teams.items()):
        if len(teams) > 1:
            findings.append(RealismFinding(
                WARN, f"'{name}' appears under {len(teams)} different teams ({sorted(teams)}) in this same slate -- "
                      f"either a genuine same-name collision or a contaminated source."))

    return RealismReport(findings)
