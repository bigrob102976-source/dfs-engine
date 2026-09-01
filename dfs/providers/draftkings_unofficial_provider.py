"""Milestone M1 -- the PERMANENT DEFAULT DFSSalaryProvider backed by
draftkings_unofficial/ (DraftKings' unofficial, undocumented public
JSON endpoints).

IMPORTANT -- this intentionally departs from dfs/providers/base.py's
general "never depend on undocumented/private DraftKings endpoints"
rule. Originally (Milestone 31.2) this was a separate, clearly-labeled,
OPT-IN-ONLY development data source; Milestone 32.2B then declared it
the sole DK slate source going forward (see
dfs/providers/source_provenance.py's DRAFTKINGS_UNOFFICIAL_LIVE), and
Milestone M1 finished that transition in the actual provider-selection
code:

  1. It IS registered in dfs/providers/config.py's automatic priority
     cascade -- get_configured_provider() tries it by default, with no
     DFS_SALARY_PROVIDER override required for normal production use.
     It remains additionally reachable via an explicit
     DFS_SALARY_PROVIDER=draftkings_unofficial override too, for parity
     with every other provider.
  2. DK_UNOFFICIAL_ENABLED is no longer an opt-IN gate -- it is now an
     explicit operational kill switch (e.g. temporarily disabling live
     DraftKings-endpoint calls for legal/ToS/rate-limit reasons). Unset,
     or set to anything other than an explicit "off" value, the
     provider is enabled. See is_enabled().

Its data is classified UNOFFICIAL_DEVELOPMENT_SOURCE by default, upgraded
to DRAFTKINGS_UNOFFICIAL_LIVE once structural validation passes (see
dfs/providers/source_provenance.py) -- DRAFTKINGS_UNOFFICIAL_LIVE IS in
TRUSTED_FOR_PRODUCTION, so dfs/pool_builder.py::build_pool() will build a
production pool from it without requiring dev_mode, exactly as a licensed
provider would be treated.
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
from dfs.providers.source_provenance import DRAFTKINGS_UNOFFICIAL_LIVE, UNOFFICIAL_DEVELOPMENT_SOURCE
from dfs.slate_validation import resolve_game_ids
from draftkings_unofficial import collector
from draftkings_unofficial.client import DraftKingsUnofficialError
from draftkings_unofficial.persistence import local_raw_archive_enabled
from draftkings_unofficial.structural_validation import validate_classic_draftgroup


def is_enabled() -> bool:
    """DraftKings Unofficial is enabled by default (Milestone M1 -- it
    is the permanent default DraftKings slate source; no env var is
    required for normal production use). DK_UNOFFICIAL_ENABLED remains
    available purely as an explicit operational kill switch: set it to
    "false", "0", or "no" to disable it. Leaving it unset, or setting it
    to any other value, keeps the provider enabled."""
    value = os.environ.get("DK_UNOFFICIAL_ENABLED", "").strip().lower()
    return value not in ("false", "0", "no")


class DraftKingsUnofficialProvider(DFSSalaryProvider):
    name = "draftkings_unofficial"
    requires_api_key = False

    def get_slate(
        self, date: str, sport: str = "MLB", site: str = "draftkings", research_games: Optional[List[dict]] = None,
        capture=None, cache=None,
    ) -> ProviderSlateResult:
        # M2B: `capture`/`cache` are purely additive (default None --
        # zero behavior change for every existing caller, which is every
        # call site in this codebase today). See
        # draftkings_unofficial/client.py::RawCapture's docstring --
        # canonical_ingestion is the only caller that passes these, to
        # obtain genuine byte-exact RAW captures for the shadow
        # ingestion path without redesigning this provider.
        if not is_enabled():
            raise ProviderUnavailableError(
                "DraftKingsUnofficialProvider is disabled via DK_UNOFFICIAL_ENABLED (operational kill "
                "switch) -- unset it, or set it to a value other than false/0/no, to re-enable the "
                "permanent default DraftKings slate source."
            )

        extra_kwargs: Dict[str, object] = {}
        if cache is not None:
            extra_kwargs["cache"] = cache
        if capture is not None:
            extra_kwargs["capture"] = capture
        # 2026-09-01 disk incident fix: this is the ONE call path the
        # scheduled production worker actually uses (via
        # scripts/fetch_dfs_slate.py) -- collector.py's own
        # save_snapshot=True default grew an un-pruned local disk
        # archive to 27.31 GB in 12 days. R2 (canonical_ingestion/
        # raw_capture.py, M2) is now the real durable RAW record, so
        # this defaults local archiving OFF here specifically, with an
        # explicit env-var opt-in for local debugging -- see
        # draftkings_unofficial/persistence.py's module docstring.
        extra_kwargs["save_snapshot"] = local_raw_archive_enabled(default=False)
        universe = collector.collect_sport_universe(sport.upper(), **extra_kwargs)
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
                detail = collector.collect_slate_detail(slate.draft_group_id, sport.upper(), game_type_id=slate.game_type_id, **extra_kwargs)
            except DraftKingsUnofficialError as exc:
                warnings.append(f"Skipped DraftGroup {slate.draft_group_id} ({slate.label or slate.tag}): {exc}")
                continue
            if detail.status != collector.STATUS_OK:
                warnings.append(f"Skipped DraftGroup {slate.draft_group_id} ({slate.label or slate.tag}): {detail.status} ({detail.error}).")
                continue

            # Milestone 32.2B: structural validation (correct game type,
            # roster template, salary cap, player/team/game identity
            # consistency -- see draftkings_unofficial/structural_
            # validation.py) determines whether this DraftGroup is
            # genuinely a well-formed MLB Classic Salary Cap slate,
            # independent of how many pitchers/hitters it lists (that's
            # a content-plausibility question for source_realism.py's
            # provider-aware rules, never a structural one). Only run for
            # MLB -- the Classic roster-template check is MLB-specific by
            # design; other sports keep the original UNOFFICIAL_
            # DEVELOPMENT_SOURCE claim unchanged, out of scope here.
            structural_result = None
            if sport.upper() == "MLB":
                structural_result = validate_classic_draftgroup(
                    slate.draft_group_id, universe.contests, detail.games, detail.draftables, detail.roster_rules,
                )
                if not structural_result.passed:
                    warnings.append(
                        f"Skipped DraftGroup {slate.draft_group_id} ({slate.label or slate.tag}): failed structural "
                        f"validation -- {[f.message for f in structural_result.findings if f.level == 'BLOCK']}."
                    )
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
                        "start_time": game.start_time if game else None, "draftable_ids": [],
                    }
                    player_order.append(key)
                if d.position and d.position not in merged_by_player_id[key]["position_eligibility"]:
                    merged_by_player_id[key]["position_eligibility"].append(d.position)
                # M1D: preserve every per-roster-slot draftableId for this
                # player_id -- never used as identity (that's `key`,
                # above), only carried forward for the future canonical
                # slate-player row (canonical/models.py).
                merged_by_player_id[key]["draftable_ids"].append(str(d.draftable_id))

            players: List[ProviderPlayer] = []
            for key in player_order:
                r = merged_by_player_id[key]
                players.append(ProviderPlayer(
                    external_player_id=key, name=r["name"], team=r["team"], opponent=r["opponent"], game=r["game"],
                    salary=r["salary"], position_eligibility=r["position_eligibility"], slate_id=slate_id,
                    slate_name=slate.label or slate.tag, start_time=r["start_time"],
                    source=self.name, retrieved_at=retrieved_at,
                    provider_draftable_ids=r["draftable_ids"],
                ))
            players_by_slate[slate_id] = players

            # Milestone 32.2B: structural validation passing upgrades the
            # provenance claim from the generic UNOFFICIAL_DEVELOPMENT_
            # SOURCE to DRAFTKINGS_UNOFFICIAL_LIVE -- still explicitly
            # UNOFFICIAL (never claimed to be an official DraftKings API,
            # never added to TRUSTED_FOR_PRODUCTION), but no longer
            # indistinguishable from "unverified." Content-realism
            # findings (dfs/providers/source_realism.py, run later by
            # dfs/pool_builder.py::build_pool() with provider_kind=
            # PROVIDER_KIND_DRAFTKINGS_UNOFFICIAL) can still downgrade
            # this to SYNTHETIC_VALIDATION if something is genuinely
            # BLOCK-level wrong at the row-content layer.
            provenance_claim = DRAFTKINGS_UNOFFICIAL_LIVE if (structural_result and structural_result.passed) else UNOFFICIAL_DEVELOPMENT_SOURCE

            slates.append(ProviderSlateInfo(
                slate_id=slate_id, slate_name=slate.label or slate.tag or f"DraftGroup {slate.draft_group_id}",
                site=site, sport=sport, start_time=slate.start_time, game_count=len(detail.games),
                # player_count reflects the DEDUPED player list actually
                # returned in players_by_slate (unique real players), not
                # DraftKings' raw per-roster-slot draftable row count.
                game_ids=game_ids, player_count=len(players),
                source_provenance=provenance_claim,
                realism_blocked=False,
                realism_findings=[f.message for f in structural_result.findings] if structural_result else [],
            ))

        if not slates:
            raise ProviderUnavailableError(
                f"DraftKings unofficial: {len(day_slates)} DraftGroup(s) found for sport={sport!r} on {date}, "
                f"but none could be collected. " + " ".join(warnings)
            )

        return ProviderSlateResult(slates=slates, players_by_slate=players_by_slate, source=self.name, retrieved_at=retrieved_at, warnings=warnings)
