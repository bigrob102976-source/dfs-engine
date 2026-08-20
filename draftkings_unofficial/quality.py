"""Milestone 31.2 -- data quality reporting for one collection run.
Pure functions over already-normalized lists; never re-fetches, never
mutates."""

from collections import Counter
from typing import Dict, List

from draftkings_unofficial.models import DkContest, DkDraftable, DkSlate, PlayerIdentityMatch


def _is_invalid_salary(salary) -> bool:
    return salary is None or salary <= 0


def _is_invalid_start_time(value) -> bool:
    return not value


def build_quality_report(
    sports_count: int,
    contests: List[DkContest],
    slates: List[DkSlate],
    draftables: List[DkDraftable],
    identity_matches: List[PlayerIdentityMatch],
) -> Dict:
    draft_group_ids = {s.draft_group_id for s in slates}
    game_ids = {g.competition_id for s in slates for g in s.games}

    draftable_ids = [d.draftable_id for d in draftables]
    dupe_draftable_ids = sum(1 for _, c in Counter(draftable_ids).items() if c > 1)

    missing_team_ids = sum(1 for d in draftables if d.team_id is None)
    missing_player_ids = sum(1 for d in draftables if d.player_id is None)
    invalid_salaries = sum(1 for d in draftables if _is_invalid_salary(d.salary))
    with_salary = sum(1 for d in draftables if d.salary is not None and d.salary > 0)
    salary_coverage_percent = round(100.0 * with_salary / len(draftables), 1) if draftables else 0.0

    with_position = sum(1 for d in draftables if d.position)
    position_coverage_percent = round(100.0 * with_position / len(draftables), 1) if draftables else 0.0

    invalid_contest_start_times = sum(1 for c in contests if _is_invalid_start_time(c.start_time_iso))

    unresolved_identities = sum(1 for m in identity_matches if m.match_status in ("unmatched", "ambiguous"))

    return {
        "sports_discovered": sports_count,
        "contests_discovered": len(contests),
        "unique_draft_groups": len(draft_group_ids),
        "games": len(game_ids),
        "draftables": len(draftables),
        "unique_players": len({d.player_id for d in draftables if d.player_id is not None}),
        "salary_coverage_percent": salary_coverage_percent,
        "position_coverage_percent": position_coverage_percent,
        "missing_player_ids": missing_player_ids,
        "missing_team_ids": missing_team_ids,
        "duplicate_draftable_ids": dupe_draftable_ids,
        "invalid_salaries": invalid_salaries,
        "invalid_contest_start_times": invalid_contest_start_times,
        "unresolved_identities": unresolved_identities,
    }
