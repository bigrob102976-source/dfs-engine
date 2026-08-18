"""Resolves DraftKings salary rows to our canonical MLB player identity.

Matching hierarchy (first tier that produces a confident, unique result wins):

1. Explicit crosswalk (dk_player_id -> mlb_player_id), when one is supplied.
2/3. Exact normalized name + team match against the Research Package's own
     known players (probable starting pitchers + posted-lineup hitters --
     the only players our Research Engine has resolved MLB identity for).
4. Conservative fallback: exact normalized name match, ignoring team,
     but ONLY accepted if it is unique across the entire slate (guards
     against the case where a team-abbreviation mismatch we don't know
     about yet would otherwise cause a false "unmatched").

If more than one Research Engine player matches at a tier, the row is
marked "ambiguous" and NOT resolved -- never silently pick one. If no
player matches any tier, the row is marked "unmatched" -- never guess.

DraftKings players whose lineup hasn't posted yet (bench hitters, etc.)
are expected to be "unmatched" here, simply because the Research Engine
has no identity record for them at all yet (see
research/adapters/batter_input.py: batters.json only contains posted
starting lineups). dfs/player_pool.py turns that into the
"lineup_not_confirmed" status rather than treating it as a data error.
"""

from typing import Dict, List, Optional, Tuple

from dfs.models import CanonicalPlayer, DKSalaryRow, PlayerMatch
from dfs.name_normalization import normalize_name
from dfs.team_abbreviations import normalize_dk_team_abbr

CanonicalIndex = Dict[Tuple[str, str], List[CanonicalPlayer]]


def build_canonical_index(package: dict) -> CanonicalIndex:
    """Index every player the Research Engine currently knows about
    (probable pitchers + posted-lineup hitters) by (normalized_name, team_abbr)."""
    index: CanonicalIndex = {}
    games_by_id = {g["game_id"]: g for g in package.get("games", [])}

    for record in package.get("pitchers", []):
        player = CanonicalPlayer(
            mlb_player_id=str(record["player_id"]), name=record["name"], team=record["team_abbr"],
            opponent=record["opponent_abbr"], game_id=record["game_id"], player_type="pitcher",
        )
        index.setdefault((normalize_name(record["name"]), record["team_abbr"]), []).append(player)

    for record in package.get("batters", []):
        player = CanonicalPlayer(
            mlb_player_id=str(record["player_id"]), name=record["name"], team=record["team_abbr"],
            opponent=record["opponent_abbr"], game_id=record["game_id"], player_type="hitter",
        )
        index.setdefault((normalize_name(record["name"]), record["team_abbr"]), []).append(player)

    return index


def build_name_only_index(index: CanonicalIndex) -> Dict[str, List[CanonicalPlayer]]:
    by_name: Dict[str, List[CanonicalPlayer]] = {}
    for (name, _team), players in index.items():
        by_name.setdefault(name, []).extend(players)
    return by_name


def build_canonical_by_id(index: CanonicalIndex) -> Dict[str, CanonicalPlayer]:
    by_id: Dict[str, CanonicalPlayer] = {}
    for players in index.values():
        for p in players:
            by_id[p.mlb_player_id] = p
    return by_id


PITCHER_DK_POSITIONS = frozenset({"P", "SP", "RP"})


def _infer_player_type_from_dk_positions(dk_positions: List[str]) -> Optional[str]:
    """DraftKings position eligibility is authoritative for DFS player
    type (see dfs/player_pool.py's module docstring / Milestone 27.3).
    The 'Position' column DraftKings actually exports uses SP/RP, not a
    bare 'P' (that only ever appears in 'Roster Position') -- checking
    for literal 'P' membership here mis-classified every SP/RP row as a
    hitter whenever the row had no canonical research match to inherit
    player_type from instead (the bug M27.3 fixes)."""
    if not dk_positions:
        return None
    return "pitcher" if PITCHER_DK_POSITIONS.intersection(dk_positions) else "hitter"


def _dk_cross_team_names(dk_rows: List[DKSalaryRow]) -> set:
    """Normalized names that appear on more than one DISTINCT DK team
    within this same slate. When a name collides across teams (e.g. two
    different DraftKings rows both named "Max Muncy", one on each of two
    different teams -- confirmed real in M27.3's live slate), Tier 4's
    name-only fallback below cannot safely tell them apart and must not
    guess; a genuine team-abbreviation-alias case (the one Tier 4 exists
    for) only ever has ONE DK team for that name in the raw slate."""
    teams_by_name: Dict[str, set] = {}
    for row in dk_rows:
        teams_by_name.setdefault(normalize_name(row.name), set()).add(normalize_dk_team_abbr(row.team_abbrev))
    return {name for name, teams in teams_by_name.items() if len(teams) > 1}


def resolve_player(
    dk_row: DKSalaryRow,
    index: CanonicalIndex,
    name_only_index: Dict[str, List[CanonicalPlayer]],
    crosswalk: Optional[Dict[str, str]] = None,
    canonical_by_id: Optional[Dict[str, CanonicalPlayer]] = None,
    dk_cross_team_names: Optional[set] = None,
) -> PlayerMatch:
    crosswalk = crosswalk or {}
    canonical_by_id = canonical_by_id or {}
    dk_cross_team_names = dk_cross_team_names or set()
    normalized = normalize_name(dk_row.name)
    research_team = normalize_dk_team_abbr(dk_row.team_abbrev)

    # Milestone 27.3: DK position eligibility is THE authority for
    # player_type, full stop -- never the matched research record's own
    # classification (which reflects MLB defensive position / which
    # board the player happened to appear on, not DK roster eligibility).
    # A matched canonical record only fills in player_type on the rare
    # row where DK supplied no position data at all.
    dk_player_type = _infer_player_type_from_dk_positions(dk_row.dk_positions)

    def _effective_player_type(canonical: Optional[CanonicalPlayer]) -> Optional[str]:
        if dk_player_type is not None:
            return dk_player_type
        return canonical.player_type if canonical else None

    base = dict(dk_player_id=dk_row.dk_player_id, dk_name=dk_row.name, dk_team=dk_row.team_abbrev)

    # Tier 1: explicit crosswalk.
    if dk_row.dk_player_id in crosswalk:
        mlb_id = crosswalk[dk_row.dk_player_id]
        canonical = canonical_by_id.get(mlb_id)
        return PlayerMatch(
            **base, match_status="matched", mlb_player_id=mlb_id, match_confidence="explicit_crosswalk",
            player_type=_effective_player_type(canonical),
        )

    # Tiers 2/3: exact normalized name + team.
    candidates = index.get((normalized, research_team), [])
    if len(candidates) == 1:
        c = candidates[0]
        return PlayerMatch(**base, match_status="matched", mlb_player_id=c.mlb_player_id,
                            match_confidence="name_team_exact", player_type=_effective_player_type(c))
    if len(candidates) > 1:
        return PlayerMatch(**base, match_status="ambiguous", player_type=dk_player_type,
                            candidate_mlb_ids=[c.mlb_player_id for c in candidates],
                            candidate_names=[c.name for c in candidates])

    # Tier 4: conservative fallback -- name-only, but must be unique
    # slate-wide AND the name must not collide across two different DK
    # teams in this slate (that's not an abbreviation-alias situation,
    # it's two different players -- see _dk_cross_team_names).
    if normalized not in dk_cross_team_names:
        name_candidates = name_only_index.get(normalized, [])
        if len(name_candidates) == 1:
            c = name_candidates[0]
            return PlayerMatch(**base, match_status="matched", mlb_player_id=c.mlb_player_id,
                                match_confidence="name_only_slate_unique", player_type=_effective_player_type(c))
        if len(name_candidates) > 1:
            return PlayerMatch(**base, match_status="ambiguous", player_type=dk_player_type,
                                candidate_mlb_ids=[c.mlb_player_id for c in name_candidates],
                                candidate_names=[c.name for c in name_candidates])

    return PlayerMatch(**base, match_status="unmatched", player_type=dk_player_type)


def resolve_all(
    dk_rows: List[DKSalaryRow], package: dict, crosswalk: Optional[Dict[str, str]] = None
) -> List[PlayerMatch]:
    index = build_canonical_index(package)
    name_only_index = build_name_only_index(index)
    canonical_by_id = build_canonical_by_id(index)
    cross_team_names = _dk_cross_team_names(dk_rows)
    return [
        resolve_player(row, index, name_only_index, crosswalk, canonical_by_id, cross_team_names)
        for row in dk_rows
    ]
