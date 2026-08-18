"""Fallback DFS salary provider (Milestone 19, priority 2): builds a
player pool directly from the latest CSV-imported EXTERNAL PROJECTION
baseline snapshot (external_projections/csv_import/, Milestone 18) when
no real DraftKings salary CSV has been uploaded yet
(dfs/providers/draftkings_csv_provider.py). Many projection-export
tools (BlueCollar, FantasyCruncher, SaberSim, ...) already mirror a
specific real DraftKings slate's own salaries, so this is still real
salary data -- just not sourced from DraftKings' own file, and clearly
labeled as such (never presented as "DraftKings").

Deliberately checks the snapshot's own `source == "csv_import"` tag
rather than simply "whatever the latest baseline happens to be" -- a
MOCK EXTERNAL PROJECTIONS dev snapshot, or a future live provider-fetch
baseline, must never be used as a salary source here.
"""

from pathlib import Path
from typing import List, Optional

from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
from external_projections.persistence import DEFAULT_EXTERNAL_SNAPSHOT_ROOT, load_latest_baseline_snapshot


def _usable_players(players: List[dict]) -> List[dict]:
    return [p for p in players if p.get("name") and p.get("team") and p.get("position") and p.get("salary") is not None]


class CsvImportPoolProvider(DFSSalaryProvider):
    name = "csv_import_pool"
    requires_api_key = False

    def __init__(self, external_snapshot_root: Path = DEFAULT_EXTERNAL_SNAPSHOT_ROOT):
        self.external_snapshot_root = external_snapshot_root

    def get_slate(
        self, date: str, sport: str = "MLB", site: str = "draftkings", research_games: Optional[List[dict]] = None
    ) -> ProviderSlateResult:
        if sport.upper() != "MLB":
            raise ProviderNoSlateError(f"CsvImportPoolProvider only supports MLB, got sport={sport!r}.")

        baseline = load_latest_baseline_snapshot(date, output_root=self.external_snapshot_root)
        if baseline is None or baseline.get("source") != "csv_import":
            raise ProviderUnavailableError(
                f"No CSV-imported projection snapshot with real salaries found for {date}. "
                f"Import a provider CSV under Settings -> External Data -> Import Projections."
            )

        all_players = baseline.get("players", [])
        usable = _usable_players(all_players)
        if not usable:
            raise ProviderUnavailableError(
                f"The latest CSV-imported snapshot for {date} has no players with name + team + "
                f"position + salary -- cannot build a player pool from it."
            )

        provider_name = baseline.get("provider_name") or baseline.get("provider") or "CSV Import"
        slate_id = f"csvpool-{baseline.get('provider')}-{date}"
        slate_name = f"{provider_name} (CSV Import)"
        retrieved_at = baseline.get("retrieved_at") or ""

        players = [
            ProviderPlayer(
                external_player_id=str(p.get("external_player_id") or p["name"]), name=p["name"], team=p["team"],
                opponent=p.get("opponent"), game=None, salary=int(p["salary"]),
                position_eligibility=[seg.strip() for seg in str(p["position"]).split("/") if seg.strip()],
                slate_id=slate_id, slate_name=slate_name, start_time=None, source=self.name,
                retrieved_at=retrieved_at,
            )
            for p in usable
        ]
        slate_info = ProviderSlateInfo(
            slate_id=slate_id, slate_name=slate_name, site=site, sport=sport, start_time=None,
            game_count=None, game_ids=[], player_count=len(players),
        )

        warnings = [
            f"Using {provider_name} CSV-imported projections as the player pool source -- "
            f"not official DraftKings data. Upload a real DraftKings salary CSV when available."
        ]
        skipped = len(all_players) - len(usable)
        if skipped:
            warnings.append(f"{skipped} player(s) skipped (missing salary/team/position).")

        return ProviderSlateResult(
            slates=[slate_info], players_by_slate={slate_id: players}, source=self.name,
            retrieved_at=retrieved_at, warnings=warnings,
        )
