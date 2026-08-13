"""A clearly-labeled DEVELOPMENT/MOCK provider -- NOT a real DraftKings
salary source. Used only so the one-click pipeline can be exercised
end-to-end when no real, credentialed DFS-data provider is configured
(see dfs/providers/config.py's docstring for what a real one would need).

Player IDENTITY (name, team, opponent, game, position eligibility) is
built entirely from the REAL Research Package for the date -- nothing
about who's playing is invented. SALARY is the one field with no real
source available here: it is a deterministic, documented function of
each player's own already-computed overall_score (from the real
Pitcher/Batter Agent snapshots), rounded to DK's typical $100
granularity and clamped to a realistic range. It is intentionally
labeled `source="mock_dev_provider"` everywhere downstream (the pool,
the dashboard) so it can never be mistaken for a real salary.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
from dfs.snapshot_selection import select_snapshot
from research.adapters import batter_input as batter_adapter
from research.adapters import pitcher_input as pitcher_adapter
from research.adapters.pitcher_input import ResearchPackageNotFoundError

_POSITION_MAP = {"C": "C", "1B": "1B", "2B": "2B", "3B": "3B", "SS": "SS", "LF": "OF", "CF": "OF", "RF": "OF", "OF": "OF"}
_DEFAULT_HITTER_POSITION = "OF"  # DH / unmapped -- documented mock-data simplification, not a real eligibility claim

_SALARY_TUNING = {
    "pitcher": {"base": 6000, "scale": 60, "min": 4500, "max": 11000},
    "hitter": {"base": 3000, "scale": 30, "min": 2000, "max": 6500},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mock_salary(player_type: str, overall_score: Optional[float]) -> int:
    cfg = _SALARY_TUNING[player_type]
    score = overall_score if overall_score is not None else 50.0
    raw = cfg["base"] + (score - 50.0) * cfg["scale"]
    rounded = round(raw / 100.0) * 100
    return int(max(cfg["min"], min(cfg["max"], rounded)))


def _hitter_positions(position: Optional[str]) -> List[str]:
    if position and position in _POSITION_MAP:
        return [_POSITION_MAP[position]]
    return [_DEFAULT_HITTER_POSITION]


def _format_et_time(game_datetime_utc: Optional[str]) -> Optional[str]:
    """'2026-08-11T23:05:00Z' -> '7:05PM' -- DK's own Game Info column
    always displays in America/New_York regardless of park timezone."""
    if not game_datetime_utc:
        return None
    from zoneinfo import ZoneInfo

    dt_utc = datetime.fromisoformat(game_datetime_utc.replace("Z", "+00:00"))
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_et = dt_utc.astimezone(ZoneInfo("America/New_York"))
    hour12 = dt_et.strftime("%I").lstrip("0") or "12"
    return f"{hour12}:{dt_et.strftime('%M%p')}"


def _game_string(game: Optional[dict]) -> Optional[str]:
    if not game:
        return None
    time_str = _format_et_time(game.get("game_datetime_utc"))
    base = f"{game['away_team_abbr']}@{game['home_team_abbr']}"
    return f"{base} {time_str} ET" if time_str else base


class MockProvider(DFSSalaryProvider):
    """Development/mock DFS salary provider -- see module docstring."""

    name = "mock_dev_provider"
    requires_api_key = False

    def __init__(self, research_output_root: str = "research_output", predictions_root: str = "predictions"):
        self.research_output_root = research_output_root
        self.predictions_root = predictions_root

    def get_slate(self, date: str, sport: str = "MLB", site: str = "draftkings") -> ProviderSlateResult:
        if sport.upper() != "MLB":
            raise ProviderNoSlateError(f"MockProvider only supports MLB, got sport={sport!r}.")

        try:
            pitcher_pkg = pitcher_adapter.load_research_package(self.research_output_root, date)
        except ResearchPackageNotFoundError as e:
            raise ProviderUnavailableError(
                f"No Research Package found for {date} under {self.research_output_root}/ -- "
                f"build it first (python scripts/build_research_package.py --date {date})."
            ) from e
        batter_pkg = batter_adapter.load_research_package(self.research_output_root, date)

        games_by_id = {g["game_id"]: g for g in pitcher_pkg["games"]}
        retrieved_at = _now()
        if not games_by_id:
            return ProviderSlateResult(
                slates=[], players_by_slate={}, source=self.name, retrieved_at=retrieved_at,
                warnings=[f"No MLB games found for {date}."],
            )

        pitcher_snapshot, _ = select_snapshot(None, date, Path(self.predictions_root), "pitcher_board")
        batter_snapshot, _ = select_snapshot(None, date, Path(self.predictions_root), "batter_board")
        pitcher_scores = {r["player_id"]: r.get("overall_score") for r in (pitcher_snapshot or {}).get("pitchers", [])}
        batter_scores = {r["player_id"]: r.get("overall_score") for r in (batter_snapshot or {}).get("hitters", [])}

        slate_id = f"mock-main-{date}"
        warnings: List[str] = []
        if pitcher_snapshot is None:
            warnings.append("No pitcher snapshot found -- mock pitcher salaries fall back to a neutral score.")
        if batter_snapshot is None:
            warnings.append("No batter snapshot found -- mock hitter salaries fall back to a neutral score.")

        players: List[ProviderPlayer] = []
        for record in pitcher_pkg["pitchers"]:
            game = games_by_id.get(record.get("game_id"))
            players.append(ProviderPlayer(
                external_player_id=f"mock-{record['player_id']}", name=record["name"], team=record["team_abbr"],
                opponent=record["opponent_abbr"], game=_game_string(game),
                salary=_mock_salary("pitcher", pitcher_scores.get(record["player_id"])),
                position_eligibility=["P"], slate_id=slate_id, slate_name="Mock Main (Dev)",
                start_time=game.get("game_datetime_utc") if game else None, source=self.name, retrieved_at=retrieved_at,
            ))

        for record in batter_pkg["batters"]:
            game = games_by_id.get(record.get("game_id"))
            players.append(ProviderPlayer(
                external_player_id=f"mock-{record['player_id']}", name=record["name"], team=record["team_abbr"],
                opponent=record["opponent_abbr"], game=_game_string(game),
                salary=_mock_salary("hitter", batter_scores.get(record["player_id"])),
                position_eligibility=_hitter_positions(record.get("position")), slate_id=slate_id,
                slate_name="Mock Main (Dev)", start_time=game.get("game_datetime_utc") if game else None,
                source=self.name, retrieved_at=retrieved_at,
            ))

        if not batter_pkg["batters"]:
            warnings.append("No posted starting lineups yet -- mock slate currently contains probable pitchers only.")

        slate_info = ProviderSlateInfo(
            slate_id=slate_id, slate_name="Mock Main (Dev)", site=site, sport=sport,
            start_time=None, game_count=len(games_by_id),
        )
        return ProviderSlateResult(
            slates=[slate_info], players_by_slate={slate_id: players}, source=self.name,
            retrieved_at=retrieved_at, warnings=warnings,
        )
