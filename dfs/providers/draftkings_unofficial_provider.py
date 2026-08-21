"""Milestone 31.2 -- the DEVELOPMENT-ONLY DFSSalaryProvider backed by
draftkings_unofficial/ (DraftKings' unofficial, undocumented public
JSON endpoints).

IMPORTANT -- this intentionally departs from dfs/providers/base.py's
"never depend on undocumented/private DraftKings endpoints" rule,
which was written for the PRODUCTION provider cascade
(dfs/providers/config.py::get_configured_provider, which never
activates this provider automatically). Milestone 31.2 explicitly asks
for a separate, clearly-labeled, OPT-IN-ONLY development data source to
unblock building Big Money DFS before a licensed provider is in place.
Two independent gates keep it from ever activating by accident:

  1. It is NEVER registered in dfs/providers/config.py's automatic
     priority cascade -- reachable ONLY via the existing explicit
     DFS_SALARY_PROVIDER=draftkings_unofficial override.
  2. Even when explicitly named, get_slate() refuses to run at all
     unless DK_UNOFFICIAL_ENABLED=true is also set -- see is_enabled().

Its data is always classified UNOFFICIAL_DEVELOPMENT_SOURCE (see
dfs/providers/source_provenance.py), which is NOT in
TRUSTED_FOR_PRODUCTION -- dfs/pool_builder.py::build_pool() will refuse
to build a production pool from it without dev_mode, exactly like
DEVELOPMENT_MOCK. This provider is meant to be deleted outright once a
licensed provider replaces it -- see draftkings_unofficial/README.md.
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
from dfs.providers.source_provenance import UNOFFICIAL_DEVELOPMENT_SOURCE
from dfs.slate_validation import resolve_game_ids
from draftkings_unofficial import collector
from draftkings_unofficial.client import DraftKingsUnofficialError


def is_enabled() -> bool:
    return os.environ.get("DK_UNOFFICIAL_ENABLED", "").strip().lower() in ("1", "true", "yes")


class DraftKingsUnofficialProvider(DFSSalaryProvider):
    name = "draftkings_unofficial"
    requires_api_key = False

    def get_slate(
        self, date: str, sport: str = "MLB", site: str = "draftkings", research_games: Optional[List[dict]] = None
    ) -> ProviderSlateResult:
        if not is_enabled():
            raise ProviderUnavailableError(
                "DraftKingsUnofficialProvider is disabled -- set DK_UNOFFICIAL_ENABLED=true to use this "
                "development-only data source (see draftkings_unofficial/README.md)."
            )

        universe = collector.collect_sport_universe(sport.upper())
        if universe.status == collector.STATUS_NO_ACTIVE_SLATE:
            raise ProviderNoSlateError(f"DraftKings unofficial: NO ACTIVE SLATE for sport={sport!r}.")
        if universe.status != collector.STATUS_OK:
            raise ProviderUnavailableError(f"DraftKings unofficial contest discovery failed for sport={sport!r}: {universe.status} ({universe.error}).")

        day_slates = [s for s in universe.slates if collector.slate_local_date(s) == date]
        if not day_slates:
            raise ProviderNoSlateError(f"DraftKings unofficial: no DraftGroups found for sport={sport!r} on {date}.")

        retrieved_at = datetime.now(timezone.utc).isoformat()
        slates: List[ProviderSlateInfo] = []
        players_by_slate: Dict[str, List[ProviderPlayer]] = {}
        warnings: List[str] = list(universe.skipped and [f"{len(universe.skipped)} contest/slate record(s) skipped -- see collector skip log."] or [])

        for slate in day_slates:
            slate_id = f"dkunofficial-{slate.draft_group_id}"
            try:
                detail = collector.collect_slate_detail(slate.draft_group_id, sport.upper(), game_type_id=slate.game_type_id)
            except DraftKingsUnofficialError as exc:
                warnings.append(f"Skipped DraftGroup {slate.draft_group_id} ({slate.label or slate.tag}): {exc}")
                continue
            if detail.status != collector.STATUS_OK:
                warnings.append(f"Skipped DraftGroup {slate.draft_group_id} ({slate.label or slate.tag}): {detail.status} ({detail.error}).")
                continue

            game_strings = [f"{g.away_team.abbreviation}@{g.home_team.abbreviation}" for g in detail.games if g.away_team and g.home_team]
            game_ids = resolve_game_ids(game_strings, research_games) if research_games else []

            slates.append(ProviderSlateInfo(
                slate_id=slate_id, slate_name=slate.label or slate.tag or f"DraftGroup {slate.draft_group_id}",
                site=site, sport=sport, start_time=slate.start_time, game_count=len(detail.games),
                game_ids=game_ids, player_count=len(detail.draftables),
                source_provenance=UNOFFICIAL_DEVELOPMENT_SOURCE, realism_blocked=False, realism_findings=[],
            ))

            competition_by_id = {g.competition_id: g for g in detail.games}
            players: List[ProviderPlayer] = []
            for d in detail.draftables:
                game = competition_by_id.get(d.competition_id)
                opponent = None
                game_str = None
                if game and game.home_team and game.away_team:
                    if d.team_abbreviation == game.away_team.abbreviation:
                        opponent = game.home_team.abbreviation
                    elif d.team_abbreviation == game.home_team.abbreviation:
                        opponent = game.away_team.abbreviation
                    game_str = f"{game.away_team.abbreviation}@{game.home_team.abbreviation}"
                players.append(ProviderPlayer(
                    external_player_id=str(d.draftable_id), name=d.display_name, team=d.team_abbreviation or "",
                    opponent=opponent, game=game_str, salary=d.salary or 0,
                    position_eligibility=[d.position] if d.position else [], slate_id=slate_id,
                    slate_name=slate.label or slate.tag, start_time=game.start_time if game else None,
                    source=self.name, retrieved_at=retrieved_at,
                ))
            players_by_slate[slate_id] = players

        if not slates:
            raise ProviderUnavailableError(
                f"DraftKings unofficial: {len(day_slates)} DraftGroup(s) found for sport={sport!r} on {date}, "
                f"but none could be collected. " + " ".join(warnings)
            )

        return ProviderSlateResult(slates=slates, players_by_slate=players_by_slate, source=self.name, retrieved_at=retrieved_at, warnings=warnings)
