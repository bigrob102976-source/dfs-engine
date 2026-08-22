"""Milestone 32.2B -- structural validation for the DraftKings
unofficial provider, run on the normalized DraftKings response BEFORE
content-level realism checks (dfs/providers/source_realism.py).

Determines whether a DraftGroup is genuinely a real, well-formed MLB
Classic Salary Cap slate -- game type, roster template, salary cap,
player/team/game identity consistency -- independent of HOW MANY
pitchers/hitters it lists. Pitcher-pool size is a content-plausibility
question, not a structural one; see source_realism.py's
PROVIDER_KIND_DRAFTKINGS_UNOFFICIAL rules for why a broad real pitcher
pool (live-confirmed, M32.2B: ~20-34 pitchers/team, consistent across
three independently-fetched real Classic DraftGroups on two different
dates) must never BLOCK here or there.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config.game_environment_config import TEAM_LOCATIONS

from draftkings_unofficial.models import DkContest, DkDraftable, DkRosterRules, DkSlateGame

WARN = "WARN"
BLOCK = "BLOCK"

CLASSIC_GAME_TYPE_NAME = "Classic"

# The standard DraftKings MLB Classic Salary Cap roster template --
# verified LIVE, M32.2B: /lineups/v1/gametypes/2/rules for DraftGroup
# 152543 returned exactly P, P, C, 1B, 2B, 3B, SS, OF, OF, OF at a
# $50,000 cap. MIN_PLAUSIBLE_SALARY_CAP is a sanity floor, not the
# literal figure, so a legitimate DK cap change doesn't false-positive.
EXPECTED_MLB_CLASSIC_ROSTER_SLOT_COUNTS: Dict[str, int] = {"P": 2, "C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3}
MIN_PLAUSIBLE_SALARY_CAP = 1000

# Reused from the existing live game-environment config -- never a
# second, independently-maintained team-abbreviation list.
VALID_MLB_TEAM_ABBREVIATIONS = frozenset(TEAM_LOCATIONS.keys())

# The base (non-combo) position vocabulary DraftKings' MLB Classic
# draftables use. A raw position string may combine several of these
# with "/" (e.g. "1B/OF") for a multi-position-eligible player --
# _valid_position_string checks every "/"-separated component against
# this set rather than maintaining an exhaustive combo whitelist.
BASE_MLB_DK_POSITIONS = frozenset({"SP", "RP", "C", "1B", "2B", "3B", "SS", "OF"})


@dataclass
class StructuralFinding:
    level: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "message": self.message}


@dataclass
class StructuralValidationResult:
    draft_group_id: int
    findings: List[StructuralFinding] = field(default_factory=list)
    raw_draftable_count: int = 0
    unique_player_count: int = 0

    @property
    def passed(self) -> bool:
        return not any(f.level == BLOCK for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "draft_group_id": self.draft_group_id, "passed": self.passed,
            "raw_draftable_count": self.raw_draftable_count, "unique_player_count": self.unique_player_count,
            "findings": [f.to_dict() for f in self.findings],
        }


def _valid_position_string(position: str) -> bool:
    return bool(position) and all(part in BASE_MLB_DK_POSITIONS for part in position.split("/"))


def validate_classic_draftgroup(
    draft_group_id: int, contests: List[DkContest], games: List[DkSlateGame],
    draftables: List[DkDraftable], roster_rules: Optional[DkRosterRules],
) -> StructuralValidationResult:
    """Pure function of already-fetched/normalized data -- no network
    calls here. Callers (draftkings_unofficial_provider.py) fetch
    `contests`/`games`/`draftables`/`roster_rules` via collector.py."""
    findings: List[StructuralFinding] = []

    # 1-3: DraftGroup exists (implicit in having draftables/contests),
    # sport MLB (implicit in the caller only ever calling this for MLB),
    # game type Classic.
    matching_contests = [c for c in contests if c.draft_group_id == draft_group_id]
    game_type = next((c.game_type for c in matching_contests if c.game_type), None)
    if game_type != CLASSIC_GAME_TYPE_NAME:
        findings.append(StructuralFinding(
            BLOCK, f"DraftGroup {draft_group_id}'s contest game_type is {game_type!r}, not "
                   f"{CLASSIC_GAME_TYPE_NAME!r} -- not a Classic Salary Cap slate."))

    # 4-5: salary cap + roster template.
    if roster_rules is None:
        findings.append(StructuralFinding(BLOCK, f"No roster/salary-cap rules could be retrieved for DraftGroup {draft_group_id}."))
    else:
        if not roster_rules.salary_cap_enabled:
            findings.append(StructuralFinding(BLOCK, "Salary cap is not enabled for this game type -- not a Salary Cap slate."))
        if not roster_rules.salary_cap or roster_rules.salary_cap < MIN_PLAUSIBLE_SALARY_CAP:
            findings.append(StructuralFinding(BLOCK, f"Implausible or missing salary cap: {roster_rules.salary_cap!r}."))

        slot_counts: Dict[str, int] = {}
        for slot in roster_rules.roster_slots:
            slot_counts[slot.name] = slot_counts.get(slot.name, 0) + 1
        if slot_counts != EXPECTED_MLB_CLASSIC_ROSTER_SLOT_COUNTS:
            findings.append(StructuralFinding(
                BLOCK, f"Roster template {slot_counts} does not match the expected MLB Classic "
                       f"template {EXPECTED_MLB_CLASSIC_ROSTER_SLOT_COUNTS}."))

    # 6: game count > 0.
    if not games:
        findings.append(StructuralFinding(BLOCK, "No games found for this DraftGroup."))

    # 7: unique teams approximately reconcile to games (2 per game).
    teams_seen = {d.team_abbreviation for d in draftables if d.team_abbreviation}
    expected_teams = 2 * len(games)
    if games and len(teams_seen) != expected_teams:
        findings.append(StructuralFinding(
            WARN, f"{len(teams_seen)} distinct team(s) across {len(games)} game(s) -- expected {expected_teams}."))

    # 8: every draftable has a valid stable player_id.
    missing_player_id = [d for d in draftables if d.player_id is None]
    if missing_player_id:
        level = BLOCK if len(missing_player_id) > len(draftables) * 0.05 else WARN
        findings.append(StructuralFinding(level, f"{len(missing_player_id)}/{len(draftables)} draftable(s) have no player_id."))

    # 9/16: duplicate raw rows sharing player_id must be explainable by
    # roster-slot eligibility (different roster_slot_id per row) and
    # dedupe to a single canonical player -- see
    # dfs/providers/draftkings_unofficial_provider.py's player_id-keyed
    # merge. A genuine SAME-roster-slot duplicate row is never explained
    # by eligibility and is a real structural problem.
    by_player: Dict[object, List[DkDraftable]] = {}
    for d in draftables:
        key = d.player_id if d.player_id is not None else d.draftable_id
        by_player.setdefault(key, []).append(d)
    unexplained_dupes = sum(1 for rows in by_player.values() if len(rows) > 1 and len({r.roster_slot_id for r in rows}) == 1)
    if unexplained_dupes:
        findings.append(StructuralFinding(
            BLOCK, f"{unexplained_dupes} player(s) have duplicate raw rows in the SAME roster slot -- "
                   f"not explainable by roster-slot eligibility."))

    # 10: salaries valid positive.
    invalid_salary = [d for d in draftables if not d.salary or d.salary <= 0]
    if invalid_salary:
        findings.append(StructuralFinding(WARN, f"{len(invalid_salary)} draftable(s) have a missing/non-positive salary."))

    # 11: positions valid MLB DK positions.
    invalid_position = [d for d in draftables if d.position and not _valid_position_string(d.position)]
    if invalid_position:
        findings.append(StructuralFinding(
            WARN, f"{len(invalid_position)} draftable(s) have an unrecognized position string, "
                  f"e.g. {invalid_position[0].position!r}."))

    # 12: team abbreviations valid.
    invalid_teams = teams_seen - VALID_MLB_TEAM_ABBREVIATIONS
    if invalid_teams:
        findings.append(StructuralFinding(WARN, f"Unrecognized team abbreviation(s): {sorted(invalid_teams)}."))

    # 13-14/17: game assignment consistency -- every draftable's
    # competition_id must resolve to a real game in this DraftGroup, and
    # its team must be one of that game's two participants.
    games_by_id = {g.competition_id: g for g in games}
    bad_game_assignment = 0
    for d in draftables:
        game = games_by_id.get(d.competition_id)
        if game is None:
            bad_game_assignment += 1
            continue
        game_teams = {t.abbreviation for t in (game.home_team, game.away_team) if t}
        if d.team_abbreviation and d.team_abbreviation not in game_teams:
            bad_game_assignment += 1
    if bad_game_assignment:
        findings.append(StructuralFinding(
            BLOCK, f"{bad_game_assignment} draftable(s) reference a game they aren't actually scheduled to play in."))

    # 15: overall internal consistency -- summarized by `.passed` (no BLOCK finding above).
    return StructuralValidationResult(
        draft_group_id=draft_group_id, findings=findings,
        raw_draftable_count=len(draftables), unique_player_count=len(by_player),
    )
