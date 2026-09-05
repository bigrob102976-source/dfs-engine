"""NFL M2 -- builds the canonical NflPlayer pool directly from
DraftKings' own raw draftable/game data for one already-identified real
Classic DraftGroup (see NFL M1's validate_nfl_classic_draftgroup()).

Calls draftkings_unofficial/collector.py and structural_validation.py
directly -- the SAME functions dfs/providers/draftkings_unofficial_
provider.py uses -- rather than going through that provider's own
get_slate()/ProviderPlayer layer, which exists to keep MLB's CSV and
live-provider paths byte-compatible (a constraint this package doesn't
have) and drops fields (draftable_id, roster_slot_id, status,
competition_id) this pool needs.

No CSV/mock/synthetic fallback: a DraftKings access failure, a failed
structural validation, or a malformed player raises immediately with a
clear message -- this module never invents a substitute pool.
"""

from typing import Dict, List, Optional

from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE
from draftkings_unofficial import collector
from draftkings_unofficial.models import DkDraftable, DkSlateGame
from draftkings_unofficial.structural_validation import validate_nfl_classic_draftgroup
from nfl.models import NFL_BASE_POSITIONS, FLEX_SLOT_NAME, NflPlayer, NflPoolBuildResult, NflPoolValidationFinding, NflPoolValidationResult


class NflPoolBuildError(Exception):
    """Raised for any real failure building the canonical pool -- a
    DraftGroup not found, a DraftKings access failure, or a failed
    structural validation. Never caught internally to substitute
    CSV/mock/synthetic data."""


def _find_slate(draft_group_id: int, sport_code: str = "NFL"):
    universe = collector.collect_sport_universe(sport_code)
    if universe.status != collector.STATUS_OK:
        raise NflPoolBuildError(f"DraftKings unofficial contest discovery failed for sport={sport_code!r}: {universe.status} ({universe.error}).")
    slate = next((s for s in universe.slates if s.draft_group_id == draft_group_id), None)
    if slate is None:
        raise NflPoolBuildError(f"DraftGroup {draft_group_id} was not found in the current {sport_code} universe.")
    return universe, slate


def _game_lookup(games: List[DkSlateGame]) -> Dict[int, DkSlateGame]:
    return {g.competition_id: g for g in games}


def _slot_name_map(roster_rules) -> Dict[int, str]:
    """Maps DK's own roster_slot_id -> slot name using THIS DraftGroup's
    own /lineups/v1/gametypes/{id}/rules response (already fetched by
    collect_slate_detail) -- never a hardcoded numeric-ID table, so a
    future DK renumbering can't silently mis-map slots."""
    return {slot.roster_slot_id: slot.name for slot in roster_rules.roster_slots}


def _normalize_players(
    draftables: List[DkDraftable], games: List[DkSlateGame], slot_names: Dict[int, str],
    draft_group_id: int, slate_date: str, slate_name: Optional[str], provenance: str,
) -> List[NflPlayer]:
    games_by_id = _game_lookup(games)

    # Group every raw row (one per roster-slot eligibility -- see NFL
    # M2's own investigation: an RB/WR/TE appears twice, once for its
    # base slot and once for FLEX, sharing the same player_id) by DK's
    # stable cross-slate player_id.
    rows_by_player: Dict[str, List[DkDraftable]] = {}
    order: List[str] = []
    for d in draftables:
        if d.player_id is None:
            raise NflPoolBuildError(f"Draftable {d.draftable_id} ({d.display_name!r}) has no player_id -- cannot build a stable canonical identity.")
        key = str(d.player_id)
        if key not in rows_by_player:
            rows_by_player[key] = []
            order.append(key)
        rows_by_player[key].append(d)

    players: List[NflPlayer] = []
    for key in order:
        rows = rows_by_player[key]
        first = rows[0]

        slot_names_seen = {slot_names.get(r.roster_slot_id, str(r.roster_slot_id)) for r in rows}
        base_slots = sorted(slot_names_seen - {FLEX_SLOT_NAME})
        if len(base_slots) != 1:
            raise NflPoolBuildError(
                f"Player {first.display_name!r} (player_id={key}) resolves to {len(base_slots)} non-FLEX roster "
                f"slot(s) {base_slots} -- expected exactly one base position."
            )
        position = base_slots[0]
        if position not in NFL_BASE_POSITIONS:
            raise NflPoolBuildError(f"Player {first.display_name!r} has unsupported position {position!r} -- not a Classic NFL position.")
        roster_slots = sorted(slot_names_seen, key=lambda s: (s == FLEX_SLOT_NAME, s))

        game = games_by_id.get(first.competition_id)
        if game is None:
            raise NflPoolBuildError(f"Player {first.display_name!r} references competition_id={first.competition_id!r}, which isn't a game in this DraftGroup.")
        opponent = None
        if game.home_team and game.away_team:
            if first.team_abbreviation == game.away_team.abbreviation:
                opponent = game.home_team.abbreviation
            elif first.team_abbreviation == game.home_team.abbreviation:
                opponent = game.away_team.abbreviation

        status = first.status
        injury_status = None if status in (None, "None") else status

        players.append(NflPlayer(
            draftkings_player_id=key,
            draftkings_dk_id=str(first.player_dk_id) if first.player_dk_id is not None else None,
            draftable_ids=[str(r.draftable_id) for r in rows],
            name=first.display_name,
            first_name=first.first_name or None,
            last_name=first.last_name or None,
            is_team_entity=(position == "DST"),
            position=position,
            roster_slots=roster_slots,
            team=first.team_abbreviation or "",
            opponent=opponent,
            game_id=str(first.competition_id),
            game_description=game.name,
            game_start_time=game.start_time,
            salary=first.salary or 0,
            status=status,
            injury_status=injury_status,
            draft_group_id=draft_group_id,
            slate_date=slate_date,
            slate_name=slate_name,
            source="draftkings_unofficial",
            source_provenance=provenance,
        ))
    return players


def validate_pool(players: List[NflPlayer], draft_group_id: int, expected_provenance: str = DRAFTKINGS_UNOFFICIAL_LIVE) -> NflPoolValidationResult:
    findings: List[NflPoolValidationFinding] = []

    if not players:
        findings.append(NflPoolValidationFinding("BLOCK", f"Zero players in the pool for DraftGroup {draft_group_id}."))

    bad_provenance = [p for p in players if p.source_provenance != expected_provenance]
    if bad_provenance:
        findings.append(NflPoolValidationFinding(
            "BLOCK", f"{len(bad_provenance)} player(s) do not carry provenance {expected_provenance!r}."))

    seen_ids = set()
    dup_ids = set()
    for p in players:
        if p.draftkings_player_id in seen_ids:
            dup_ids.add(p.draftkings_player_id)
        seen_ids.add(p.draftkings_player_id)
    if dup_ids:
        findings.append(NflPoolValidationFinding("BLOCK", f"{len(dup_ids)} duplicate canonical player ID(s): {sorted(dup_ids)}."))

    seen_draftable_ids = set()
    dup_draftable_ids = set()
    for p in players:
        for did in p.draftable_ids:
            if did in seen_draftable_ids:
                dup_draftable_ids.add(did)
            seen_draftable_ids.add(did)
    if dup_draftable_ids:
        findings.append(NflPoolValidationFinding("BLOCK", f"{len(dup_draftable_ids)} duplicate draftable ID(s)."))

    invalid_positions = {p.position for p in players} - NFL_BASE_POSITIONS
    if invalid_positions:
        findings.append(NflPoolValidationFinding("BLOCK", f"Unsupported position(s) present: {sorted(invalid_positions)}."))

    invalid_salary = [p for p in players if p.salary <= 0]
    if invalid_salary:
        findings.append(NflPoolValidationFinding("WARN", f"{len(invalid_salary)} player(s) have a non-positive salary."))

    unassigned_game = [p for p in players if not p.game_id]
    if unassigned_game:
        findings.append(NflPoolValidationFinding("BLOCK", f"{len(unassigned_game)} player(s) have no game assignment."))

    position_counts: Dict[str, int] = {}
    for p in players:
        position_counts[p.position] = position_counts.get(p.position, 0) + 1
    salaries = [p.salary for p in players if p.salary]

    return NflPoolValidationResult(
        passed=not any(f.level == "BLOCK" for f in findings),
        findings=findings,
        total_players=len(players),
        position_counts=position_counts,
        team_count=len({p.team for p in players if p.team}),
        game_count=len({p.game_id for p in players if p.game_id}),
        salary_min=min(salaries) if salaries else None,
        salary_max=max(salaries) if salaries else None,
    )


def build_pool(slate_date: str, draft_group_id: int, sport_code: str = "NFL") -> NflPoolBuildResult:
    """Fetches DraftGroup `draft_group_id` live, structurally validates
    it as a real NFL Classic slate, and normalizes it into a canonical
    NflPlayer pool. Raises NflPoolBuildError for any real failure --
    never returns a partial/fabricated pool."""
    universe, slate = _find_slate(draft_group_id, sport_code)

    detail = collector.collect_slate_detail(draft_group_id, sport_code, game_type_id=slate.game_type_id)
    if detail.status != collector.STATUS_OK:
        raise NflPoolBuildError(f"DraftKings unofficial slate detail fetch failed for DraftGroup {draft_group_id}: {detail.status} ({detail.error}).")

    structural_result = validate_nfl_classic_draftgroup(draft_group_id, universe.contests, detail.games, detail.draftables, detail.roster_rules)
    if not structural_result.passed:
        block_messages = [f.message for f in structural_result.findings if f.level == "BLOCK"]
        raise NflPoolBuildError(f"DraftGroup {draft_group_id} failed NFL Classic structural validation: {block_messages}.")

    if detail.roster_rules is None:
        raise NflPoolBuildError(f"DraftGroup {draft_group_id} passed structural validation but has no roster_rules -- cannot map roster slots.")

    slot_names = _slot_name_map(detail.roster_rules)
    slate_name = slate.label or slate.tag

    players = _normalize_players(
        detail.draftables, detail.games, slot_names, draft_group_id, slate_date, slate_name, DRAFTKINGS_UNOFFICIAL_LIVE,
    )
    validation = validate_pool(players, draft_group_id)

    return NflPoolBuildResult(
        draft_group_id=draft_group_id, slate_date=slate_date, slate_name=slate_name,
        players=players, validation=validation, source_provenance=DRAFTKINGS_UNOFFICIAL_LIVE,
    )


def build_pool_preferring_cache(slate_date: str, draft_group_id: int, sport_code: str = "NFL") -> NflPoolBuildResult:
    """NFL M15 -- production DraftKings-access resilience: reuses a
    recent (<=15 min, see nfl/pool_cache.py) real, live-provenance pool
    snapshot for this exact DraftGroup if one exists, only calling
    DraftKings live via build_pool() when no such snapshot exists.

    A snapshot only exists once something has explicitly written one
    (a normal dashboard run, or the external scripts/fetch_nfl_slates.py
    -- see that script's docstring for why an external fetch is needed
    at all), so ordinary local dev behaves exactly as before: no
    snapshot -> straight to build_pool()'s live fetch, unchanged."""
    from nfl.pool_cache import load_fresh_cached_pool
    cached = load_fresh_cached_pool(slate_date, draft_group_id)
    if cached is not None:
        return cached
    return build_pool(slate_date, draft_group_id, sport_code)
