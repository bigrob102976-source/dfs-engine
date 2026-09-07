"""NFL M6B Phase 3/4/6/7/10/12 -- the DraftKings <-> GSIS identity
matcher. Mirrors dfs/player_resolver.py's tiered-matching shape (crosswalk
-> exact match -> conservative fallback -> never guess) -- a fresh
implementation, not a shared import, because that module's tiers are
keyed to MLB's team-same-day assumptions and its own CanonicalPlayer/
DKSalaryRow types; NFL's Tier 3 (cross-team reconciliation for a player
who changed teams in the offseason) has no MLB equivalent.

Reused, not reinvented: dfs/name_normalization.py::normalize_name (fully
generic, already handles suffixes/punctuation/apostrophes/hyphens/
initials -- audited live against real DK and nflverse NFL names during
this milestone; no NFL-specific normalization rule was found to be
missing)."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from dfs.name_normalization import normalize_name

from historical_nfl.identity_models import (
    CONFIDENCE_BY_METHOD,
    METHOD_EXCEPTION_TABLE,
    METHOD_EXISTING_CROSSWALK,
    METHOD_NAME_POSITION_CROSS_TEAM,
    METHOD_NAME_TEAM_EXACT,
    REVIEW_AUTO_APPROVED,
    REVIEW_NEEDS_REVIEW,
    STATUS_AMBIGUOUS,
    STATUS_MATCHED,
    STATUS_REVIEW_REQUIRED,
    STATUS_UNMATCHED,
    NflCrosswalkRow,
    NflIdentityMatchResult,
)
from historical_nfl.identity_position import is_position_compatible
from historical_nfl.identity_team_normalization import normalize_nflverse_team_abbr

# Phase 3 Tier 4 -- explicit, human-reviewed exceptions ONLY (never a
# generic nickname dictionary). Each entry here was individually
# verified against real data during M6B: DraftKings' "Hollywood Brown"
# (WR, team PHI) and nflreadpy's real 2026 roster row for "Marquise
# Brown" (WR, team PHI, gsis_id resolvable) share the same team and
# position -- Marquise "Hollywood" Brown is public, well-known identity,
# and nflverse's own `football_name` field for that row ("Marquise")
# does not itself resolve the nickname, confirming a real gap
# normalize_name() cannot close deterministically.
# Key: (normalized DK name, DK team) -> normalized nflverse name to
# search for instead.
NAME_EXCEPTIONS: Dict[Tuple[str, str], str] = {
    (normalize_name("Hollywood Brown"), "PHI"): normalize_name("Marquise Brown"),
}


@dataclass
class RosterCandidate:
    gsis_id: str
    name: str
    normalized_name: str
    team: str  # already normalized into DraftKings' team-abbreviation space
    position: str


def build_roster_indices(nflverse_roster_rows: List[dict]) -> Tuple[Dict[Tuple[str, str], List[RosterCandidate]], Dict[str, List[RosterCandidate]]]:
    """`nflverse_roster_rows` -- real rows from nflreadpy.load_rosters()/
    load_rosters_weekly() (dicts with at least gsis_id/full_name/team/
    position). Rows with no usable gsis_id are skipped -- they cannot
    anchor an identity match (M6A already found ~0.1% of real roster
    rows have an empty/null gsis_id)."""
    by_name_team: Dict[Tuple[str, str], List[RosterCandidate]] = {}
    by_name: Dict[str, List[RosterCandidate]] = {}
    for row in nflverse_roster_rows:
        gsis_id = row.get("gsis_id")
        name = row.get("full_name")
        if not gsis_id or not name:
            continue
        team = normalize_nflverse_team_abbr(row.get("team"))
        candidate = RosterCandidate(
            gsis_id=gsis_id, name=name, normalized_name=normalize_name(name),
            team=team, position=row.get("position") or "",
        )
        by_name_team.setdefault((candidate.normalized_name, team), []).append(candidate)
        by_name.setdefault(candidate.normalized_name, []).append(candidate)
    return by_name_team, by_name


def _dedupe_by_gsis(candidates: List[RosterCandidate]) -> List[RosterCandidate]:
    """A player can legitimately appear more than once in a roster
    snapshot (multiple status rows across the season); collapse to
    unique gsis_id before judging ambiguity -- ambiguity should reflect
    distinct PEOPLE, never duplicate rows for the same person."""
    seen: Dict[str, RosterCandidate] = {}
    for c in candidates:
        seen.setdefault(c.gsis_id, c)
    return list(seen.values())


def resolve_identity(
    dk_player_id: str, dk_draftable_id: Optional[str], dk_name: str, dk_team: str, dk_position: str,
    existing_crosswalk: Dict[str, NflCrosswalkRow],
    index_by_name_team: Dict[Tuple[str, str], List[RosterCandidate]],
    index_by_name: Dict[str, List[RosterCandidate]],
) -> NflIdentityMatchResult:
    base = dict(draftkings_player_id=dk_player_id, draftkings_draftable_id=dk_draftable_id, dk_name=dk_name, dk_team=dk_team, dk_position=dk_position)

    # Tier 1: existing approved crosswalk.
    existing = existing_crosswalk.get(dk_player_id)
    if existing is not None and existing.review_status in (REVIEW_AUTO_APPROVED, "REVIEWED_APPROVED"):
        return NflIdentityMatchResult(
            **base, status=STATUS_MATCHED, gsis_id=existing.gsis_id,
            match_method=METHOD_EXISTING_CROSSWALK, match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXISTING_CROSSWALK],
            reason="Reused a previously approved DK<->GSIS mapping.",
        )

    normalized = normalize_name(dk_name)

    # Tier 2: exact normalized name + exact team + compatible position.
    team_candidates = _dedupe_by_gsis([c for c in index_by_name_team.get((normalized, dk_team), []) if is_position_compatible(dk_position, c.position)])
    if len(team_candidates) == 1:
        return NflIdentityMatchResult(
            **base, status=STATUS_MATCHED, gsis_id=team_candidates[0].gsis_id,
            match_method=METHOD_NAME_TEAM_EXACT, match_confidence=CONFIDENCE_BY_METHOD[METHOD_NAME_TEAM_EXACT],
            reason="Exact normalized name + team + compatible position.",
        )
    if len(team_candidates) > 1:
        return NflIdentityMatchResult(
            **base, status=STATUS_AMBIGUOUS, candidate_gsis_ids=[c.gsis_id for c in team_candidates],
            reason="More than one real roster candidate shares this normalized name, team, and compatible position.",
        )

    # Tier 3: exact normalized name (any team) + compatible position --
    # controlled cross-team reconciliation for a real offseason team
    # change (confirmed real cases during M6B: Kayshon Boutte NE->HOU,
    # Quinn Ewers MIA->JAX, etc.).
    name_candidates = _dedupe_by_gsis([c for c in index_by_name.get(normalized, []) if is_position_compatible(dk_position, c.position)])
    if len(name_candidates) == 1:
        candidate = name_candidates[0]
        return NflIdentityMatchResult(
            **base, status=STATUS_MATCHED, gsis_id=candidate.gsis_id,
            match_method=METHOD_NAME_POSITION_CROSS_TEAM, match_confidence=CONFIDENCE_BY_METHOD[METHOD_NAME_POSITION_CROSS_TEAM],
            reason="Exact normalized name + compatible position, matched across a team change.",
        )
    if len(name_candidates) > 1:
        return NflIdentityMatchResult(
            **base, status=STATUS_AMBIGUOUS, candidate_gsis_ids=[c.gsis_id for c in name_candidates],
            reason="More than one real roster candidate (across teams) shares this normalized name and compatible position.",
        )

    # Tier 4: explicit, individually reviewed exception table.
    exception_target = NAME_EXCEPTIONS.get((normalized, dk_team))
    if exception_target is not None:
        exception_candidates = _dedupe_by_gsis([c for c in index_by_name.get(exception_target, []) if is_position_compatible(dk_position, c.position)])
        if len(exception_candidates) == 1:
            return NflIdentityMatchResult(
                **base, status=STATUS_MATCHED, gsis_id=exception_candidates[0].gsis_id,
                match_method=METHOD_EXCEPTION_TABLE, match_confidence=CONFIDENCE_BY_METHOD[METHOD_EXCEPTION_TABLE],
                reason=f"Explicit reviewed name exception ({dk_name!r} -> {exception_target!r}).",
            )

    # Nothing matched at any tier. A same-team name match that only
    # failed on position (real audit finding: usually a different real
    # person sharing a name and team) is worth a human's attention
    # rather than a silent unmatched.
    same_team_wrong_position = _dedupe_by_gsis(index_by_name_team.get((normalized, dk_team), []))
    if same_team_wrong_position:
        return NflIdentityMatchResult(
            **base, status=STATUS_REVIEW_REQUIRED, candidate_gsis_ids=[c.gsis_id for c in same_team_wrong_position],
            reason=f"Name+team matched but nflverse position(s) {sorted({c.position for c in same_team_wrong_position})} are not compatible with DK position {dk_position!r} -- likely a different real person, not confirmed.",
        )

    return NflIdentityMatchResult(**base, status=STATUS_UNMATCHED, reason="No candidate found at any matching tier.")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_crosswalk_row(match: NflIdentityMatchResult, existing: Optional[NflCrosswalkRow]) -> NflCrosswalkRow:
    """Mints/updates the durable row for one match result. canonical_player_id
    is taken from `existing` when a row already exists for this DK player
    (NEVER re-minted); otherwise minted fresh per Phase 12's rule."""
    now = _now_iso()
    created_at = existing.created_at if existing else now

    if existing is not None:
        canonical_player_id = existing.canonical_player_id
    elif match.status == STATUS_MATCHED and match.gsis_id:
        canonical_player_id = f"gsis:{match.gsis_id}"
    else:
        canonical_player_id = f"dk:{match.draftkings_player_id}"

    if match.status == STATUS_MATCHED:
        review_status = REVIEW_AUTO_APPROVED
        gsis_id = match.gsis_id
    else:
        review_status = REVIEW_NEEDS_REVIEW if match.status in (STATUS_AMBIGUOUS, STATUS_REVIEW_REQUIRED) else REVIEW_AUTO_APPROVED
        gsis_id = None  # never persist an unconfirmed candidate as if it were real

    return NflCrosswalkRow(
        canonical_player_id=canonical_player_id, draftkings_player_id=match.draftkings_player_id,
        gsis_id=gsis_id, is_team_entity=False, name=match.dk_name, normalized_name=normalize_name(match.dk_name),
        team=match.dk_team, position=match.dk_position, match_method=match.match_method,
        match_confidence=match.match_confidence, review_status=review_status,
        created_at=created_at, updated_at=now,
    )


def build_dst_crosswalk_row(draftkings_player_id: str, name: str, team: str, existing: Optional[NflCrosswalkRow] = None) -> NflCrosswalkRow:
    """DST identity is the team abbreviation itself -- stable, durable,
    no GSIS/player-level identity is invented (Phase 4)."""
    now = _now_iso()
    canonical_player_id = existing.canonical_player_id if existing else f"dst:{team}"
    return NflCrosswalkRow(
        canonical_player_id=canonical_player_id, draftkings_player_id=draftkings_player_id,
        gsis_id=None, is_team_entity=True, name=name, normalized_name=normalize_name(name),
        team=team, position="DST", match_method="team_identity", match_confidence=1.0,
        review_status=REVIEW_AUTO_APPROVED, created_at=existing.created_at if existing else now, updated_at=now,
    )
