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

            competition_by_id = {g.competition_id: g for g in detail.games}
            # DraftKings' draftables endpoint returns one row per player PER
            # ROSTER-SLOT ELIGIBILITY, not one row per player -- a player
            # eligible for more than one roster slot in this game type
            # (e.g. a primary-position slot AND a flex/UTIL slot) appears
            # as two-plus rows sharing the same player_id but different
            # draftableId/rosterSlotId (confirmed live, M32.2B: Shohei
            # Ohtani appeared twice for DraftGroup 152543, same player_id
            # 727378, rosterSlotId 112 vs 116). Using draftableId as
            # external_player_id silently duplicated that real person into
            # two ProviderPlayer rows. player_id is DK's own documented
            # stable cross-slate player identity (see DkDraftable's field
            # docstring) -- dedup on it, unioning position eligibility
            # across the merged rows, rather than on the per-roster-slot
            # draftableId.
            merged_by_player_id: Dict[str, dict] = {}
            player_order: List[str] = []
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

                canonical_id = d.player_id if d.player_id is not None else (d.player_dk_id if d.player_dk_id is not None else d.draftable_id)
                key = str(canonical_id)
                if key not in merged_by_player_id:
                    merged_by_player_id[key] = {
                        "name": d.display_name, "team": d.team_abbreviation or "", "opponent": opponent,
                        "game": game_str, "salary": d.salary or 0, "position_eligibility": [],
                        "start_time": game.start_time if game else None,
                    }
                    player_order.append(key)
                if d.position and d.position not in merged_by_player_id[key]["position_eligibility"]:
                    merged_by_player_id[key]["position_eligibility"].append(d.position)

            players: List[ProviderPlayer] = []
            for key in player_order:
                r = merged_by_player_id[key]
                players.append(ProviderPlayer(
                    external_player_id=key, name=r["name"], team=r["team"], opponent=r["opponent"], game=r["game"],
                    salary=r["salary"], position_eligibility=r["position_eligibility"], slate_id=slate_id,
                    slate_name=slate.label or slate.tag, start_time=r["start_time"],
                    source=self.name, retrieved_at=retrieved_at,
                ))
            players_by_slate[slate_id] = players

            slates.append(ProviderSlateInfo(
                slate_id=slate_id, slate_name=slate.label or slate.tag or f"DraftGroup {slate.draft_group_id}",
                site=site, sport=sport, start_time=slate.start_time, game_count=len(detail.games),
                # player_count reflects the DEDUPED player list actually
                # returned in players_by_slate (unique real players), not
                # DraftKings' raw per-roster-slot draftable row count.
                game_ids=game_ids, player_count=len(players),
                source_provenance=UNOFFICIAL_DEVELOPMENT_SOURCE, realism_blocked=False, realism_findings=[],
            ))

        if not slates:
            raise ProviderUnavailableError(
                f"DraftKings unofficial: {len(day_slates)} DraftGroup(s) found for sport={sport!r} on {date}, "
                f"but none could be collected. " + " ".join(warnings)
            )

        return ProviderSlateResult(slates=slates, players_by_slate=players_by_slate, source=self.name, retrieved_at=retrieved_at, warnings=warnings)
