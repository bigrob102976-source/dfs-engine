"""Milestone 27.3/27.4 fallout, extended by Milestone 32.2B -- source-
level realism sanity checks for a normalized DK row list, run BEFORE
anything is matched to MLB identity.

M27.3 fixed how the pipeline INTERPRETS DK rows (player_type, team,
game_id) faithfully. Live validation then surfaced that a CSV loaded at
that time was itself structurally implausible for a genuine MLB DK
Classic export. Faithful downstream preservation of an implausible
source is still garbage in, garbage out -- this module gives that a
name and a place to surface it, rather than silently trusting "it
parsed" as "it's real".

Milestone 32.2B finding: the ORIGINAL pitcher-pool/pitcher-fraction/
rows-per-game thresholds below were calibrated against that one
corrupted CSV, under the assumption that a real DK slate only salaries
roughly today's confirmed starters plus a handful of notable relievers
per team. Live investigation of three genuinely real DraftKings Classic
MLB DraftGroups (two different dates, cross-checked via DraftKings' own
gameType/roster-template/salary-cap metadata -- see
draftkings_unofficial/structural_validation.py) proved that assumption
false for the `draftkings_unofficial` provider specifically:
DraftKings' real Classic draftables endpoint consistently salaries a
much broader, season-roster-churn-inclusive pitcher pool per team
(~20-34), reproducibly IDENTICAL for the same team across independently
-fetched DraftGroups and stable day-to-day. These checks are real
signal for a CSV/manual-upload source (where that inflated shape WAS a
genuine corruption) but are not valid authenticity blockers for this
provider's actual endpoint behavior -- see PROVIDER_KIND_DRAFTKINGS_
UNOFFICIAL below. The checks themselves are NOT removed (still surfaced
for observability); only their MAXIMUM level is capped at WARN for this
one provider kind. CSV/import providers keep the original BLOCK-capable
behavior unchanged.

This module can only ever find reasons to DISTRUST a source (INFO, WARN,
or BLOCK); it never "corrects" a row's values -- see
dfs/providers/source_provenance.py for how a BLOCK downgrades the
overall provenance classification.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional

from dfs.models import DKSalaryRow
from dfs.player_resolver import PITCHER_DK_POSITIONS

INFO = "INFO"
WARN = "WARN"
BLOCK = "BLOCK"

# Which normalized-row source produced `dk_rows` -- determines whether
# the pitcher-pool-shape checks below may reach BLOCK. Default is "csv"
# (the original, unchanged behavior) so every pre-M32.2B caller that
# doesn't pass provider_kind is fully backward compatible.
PROVIDER_KIND_CSV = "csv"
PROVIDER_KIND_DRAFTKINGS_UNOFFICIAL = "draftkings_unofficial"

# Named, documented thresholds -- not scattered magic numbers. For a
# CSV/manual-upload source, a real DK Classic MLB slate salaries
# roughly a team's active-roster-adjacent player pool per game
# (typically 20-30 hitters + a handful of pitchers per team), never
# anywhere close to an entire organizational pitching staff for one
# game. See the module docstring for why this assumption does NOT
# transfer to the draftkings_unofficial provider's real endpoint shape.
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
    level: str  # INFO | WARN | BLOCK

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


def _capped_level(level: str, provider_kind: str) -> str:
    """The pitcher-pool-shape checks (per-team count, per-game rows,
    pitcher fraction) may never reach BLOCK for draftkings_unofficial --
    live-proven to be a real, reproducible property of that provider's
    actual endpoint, not evidence of corruption. Every other provider
    kind (including the CSV default) is unaffected."""
    if provider_kind == PROVIDER_KIND_DRAFTKINGS_UNOFFICIAL and level == BLOCK:
        return WARN
    return level


def check_source_realism(
    dk_rows: List[DKSalaryRow], game_count: Optional[int] = None, provider_kind: str = PROVIDER_KIND_CSV,
) -> RealismReport:
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
                _capped_level(BLOCK, provider_kind),
                f"Team '{team}' has {team_pitchers} pitcher-eligible rows salaried for this slate -- "
                f"no real MLB team's active-roster-only pitching staff is anywhere near that large."))
        elif team_pitchers >= MAX_PLAUSIBLE_PITCHERS_PER_TEAM_WARN:
            findings.append(RealismFinding(
                WARN, f"Team '{team}' has {team_pitchers} pitcher-eligible rows -- unusually high for a real DK slate."))

    if game_count and game_count > 0:
        per_game = total / game_count
        if per_game >= MAX_PLAUSIBLE_PLAYERS_PER_GAME_BLOCK:
            findings.append(RealismFinding(
                _capped_level(BLOCK, provider_kind),
                f"{total} total rows across {game_count} game(s) ({per_game:.0f}/game) is far beyond a "
                f"plausible CSV-export-shaped DK Classic MLB slate."))
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
            _capped_level(BLOCK, provider_kind),
            f"{pitcher_count}/{total} rows ({100 * pitcher_count / total:.0f}%) are pitcher-eligible -- "
            f"far above a CSV-export-shaped DK slate's typical pitcher share."))

    # Same-name check, sharpened by dk_player_id (Milestone 32.2B): DK's
    # own stable per-player ID (real CSV "ID" column; the unofficial
    # provider's player_id, see draftkings_unofficial_provider.py) lets
    # this distinguish a genuine same-name collision between two
    # different real people (SAME_NAME_DIFFERENT_PLAYER -- informational
    # only, never blocking, for any provider) from the SAME id somehow
    # appearing under multiple teams (a real identity-conflation bug,
    # always concerning regardless of provider).
    name_teams: dict = defaultdict(set)
    name_player_ids: dict = defaultdict(set)
    for row in dk_rows:
        name_teams[row.name].add(row.team_abbrev)
        name_player_ids[row.name].add(row.dk_player_id)
    for name, teams in sorted(name_teams.items()):
        if len(teams) <= 1:
            continue
        distinct_ids = name_player_ids[name]
        if len(distinct_ids) > 1:
            findings.append(RealismFinding(
                INFO, f"SAME_NAME_DIFFERENT_PLAYER: '{name}' appears under {len(teams)} different teams "
                      f"({sorted(teams)}) with {len(distinct_ids)} different DK player IDs -- a genuine "
                      f"same-name collision between different real players, not a data error."))
        else:
            player_id = next(iter(distinct_ids))
            findings.append(RealismFinding(
                BLOCK, f"'{name}' (DK player ID {player_id!r}) appears under {len(teams)} different teams "
                       f"({sorted(teams)}) with the SAME DK player ID -- identity conflated across teams, "
                       f"a real data/parsing bug."))

    return RealismReport(findings)
