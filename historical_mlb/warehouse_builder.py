"""Milestone 32.1 -- top-level warehouse build orchestrator.

Per-date processing writes each date's rows to a durable, atomic
per-date JSON file under processed/_by_date/ BEFORE the checkpoint is
marked complete (Part 5's four-step guarantee). Consolidation into the
final Parquet files is a separate, idempotent, re-runnable step that
simply concatenates every per-date file -- safe to run anytime, and
what --validate-only / a resumed run's final step both use.
"""

import json
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.game_environment_config import BALLPARKS

from historical_mlb import checkpoint
from historical_mlb.cache import atomic_write_text
from historical_mlb.game_universe import GameUniverseRow, build_game_universe, games_for_date
from historical_mlb.hitter_features import build_hitter_game_row
from historical_mlb.paths import PROCESSED_DIR, ensure_directories
from historical_mlb.pitcher_features import build_pitcher_game_row
from historical_mlb.player_crosswalk_builder import PlayerCrosswalkBuilder
from historical_mlb.quality_gates import enforce_quality_gates
from historical_mlb.sources import mlb_stats, statcast, weather
from historical_mlb.sources.statcast import parse_statcast_csv
from historical_mlb.statcast_aggregation import opponent_offense_aggregate
from historical_mlb.venues import build_venue_crosswalk

BY_DATE_DIR = PROCESSED_DIR / "_by_date"

STATCAST_BUFFER_DAYS = 30


class StatcastBuffer:
    """In-memory sliding window of parsed Statcast rows for the trailing
    STATCAST_BUFFER_DAYS -- each date's CSV is fetched (cached to disk,
    Part 4) and parsed AT MOST ONCE per build run, then reused by every
    game/player that references it, instead of re-parsing per player."""

    def __init__(self):
        self._by_date: Dict[str, List[dict]] = {}
        self._order = deque()

    def advance_to(self, date: str, force: bool = False):
        if date in self._by_date and not force:
            return
        text = statcast.fetch_cached_statcast_csv_text(date, force=force)
        self._by_date[date] = parse_statcast_csv(text) if text else []
        self._order.append(date)
        self._evict_older_than(date)

    def _evict_older_than(self, current_date: str):
        from historical_mlb.rolling import days_between
        while self._order and days_between(self._order[0], current_date) > STATCAST_BUFFER_DAYS:
            old = self._order.popleft()
            self._by_date.pop(old, None)

    def rows(self) -> List[dict]:
        out = []
        for rows in self._by_date.values():
            out.extend(rows)
        return out


def _starter_for_side(pitchers: List[dict], side: str) -> Optional[dict]:
    for p in pitchers:
        if p["side"] == side and p["stat"].get("gamesStarted") in (1, "1"):
            return p
    return None


def _batting_order_slot(raw_batting_order: Optional[str]) -> Optional[int]:
    if not raw_batting_order:
        return None
    try:
        return int(raw_batting_order) // 100
    except ValueError:
        return None


def process_date(
    date: str, games: List[GameUniverseRow], crosswalk: PlayerCrosswalkBuilder,
    statcast_buffer: StatcastBuffer, force: bool = False,
) -> Tuple[List[dict], List[dict]]:
    """Builds every hitter/pitcher row for one date's games. Pure
    orchestration -- delegates the actual per-row math to
    hitter_features.py / pitcher_features.py."""
    statcast_buffer.advance_to(date, force=force)
    statcast_rows = statcast_buffer.rows()

    hitter_rows: List[dict] = []
    pitcher_rows: List[dict] = []
    season = date[:4]

    for game in games:
        box = mlb_stats.fetch_cached_boxscore(game.game_pk, force=force)
        if not box:
            continue
        pitchers, hitters = mlb_stats.extract_all_boxscore_players(box)
        away_starter = _starter_for_side(pitchers, "away")
        home_starter = _starter_for_side(pitchers, "home")

        # Season game logs + person crosswalk (cached, Part 4/8) for every player seen in this game.
        # A two-way player's own game log is fetched under BOTH groups
        # (pitching and hitting), since they genuinely need both.
        pitcher_ids = {p["player_id"] for p in pitchers}
        hitter_ids = {h["player_id"] for h in hitters}
        season_logs: Dict[str, dict] = {}
        for pid in pitcher_ids | hitter_ids:
            entry = next((e for e in pitchers + hitters if e["player_id"] == pid), None)
            season_logs[pid] = {
                "pitching": mlb_stats.fetch_cached_season_game_log(pid, season, "pitching", force=force) if pid in pitcher_ids else None,
                "hitting": mlb_stats.fetch_cached_season_game_log(pid, season, "hitting", force=force) if pid in hitter_ids else None,
            }
            crosswalk.observe(pid, entry["name"], entry["team"], date)

        home_weather = weather.fetch_cached_weather_json(game.home_team, date, force=force)
        weather_obs = weather.weather_at_hour(home_weather, f"{date}T18:00") if home_weather else None
        if weather_obs is None and home_weather and home_weather.get("hourly", {}).get("time"):
            # No exact 18:00 slot (rare) -- fall back to the first available hour that day rather than dropping weather entirely.
            times = home_weather["hourly"]["time"]
            weather_obs = weather.weather_at_hour(home_weather, times[len(times) // 2]) if times else None

        for p in pitchers:
            pid = p["player_id"]
            opponent = game.home_team if p["side"] == "away" else game.away_team
            opponent_offense = opponent_offense_aggregate(statcast_rows, opponent)
            row = build_pitcher_game_row(
                game_pk=game.game_pk, game_date=date, game_number=game.game_number,
                player_id=pid, player_name=p["name"], team=p["team"], opponent=opponent,
                home_away=p["side"], game_start_time=game.scheduled_start, venue_id=game.venue_id,
                bat_hand=crosswalk.get(pid).bat_side, throw_hand=crosswalk.get(pid).throw_side,
                boxscore_entry=p, starter_flag=bool(p["stat"].get("gamesStarted") in (1, "1")),
                season_game_log=season_logs[pid]["pitching"] or [],
                statcast_window_rows=statcast_rows,
                opponent_season_offense=opponent_offense,
                weather=weather_obs, venue_roof_type=BALLPARKS.get(game.home_team, {}).get("roof"),
            )
            pitcher_rows.append(row)

        for h in hitters:
            pid = h["player_id"]
            opponent = game.home_team if h["side"] == "away" else game.away_team
            opposing_starter = home_starter if h["side"] == "away" else away_starter
            opp_starter_era = opp_starter_k_pct = None
            if opposing_starter:
                opp_log = mlb_stats.fetch_cached_season_game_log(opposing_starter["player_id"], season, "pitching", force=force)
                from historical_mlb.rolling import build_rolling_pitcher_stats
                opp_stats = build_rolling_pitcher_stats(opp_log, target_game_date=date, window_days=None, window_label="season")
                opp_starter_era, opp_starter_k_pct = opp_stats.era, opp_stats.k_rate

            batting_order_raw = None
            for side, team_block in (("away", box["teams"]["away"]), ("home", box["teams"]["home"])):
                if side == h["side"]:
                    player_entry = team_block.get("players", {}).get(f"ID{pid}", {})
                    batting_order_raw = player_entry.get("battingOrder")

            row = build_hitter_game_row(
                game_pk=game.game_pk, game_date=date, game_number=game.game_number,
                player_id=pid, player_name=h["name"], team=h["team"], opponent=opponent,
                home_away=h["side"], game_start_time=game.scheduled_start, venue_id=game.venue_id,
                bat_hand=crosswalk.get(pid).bat_side, throw_hand=crosswalk.get(pid).throw_side,
                boxscore_entry=h,
                season_game_log=season_logs[pid]["hitting"] or [],
                statcast_window_rows=statcast_rows,
                opposing_starter_id=opposing_starter["player_id"] if opposing_starter else None,
                opposing_starter_hand=crosswalk.get(opposing_starter["player_id"]).throw_side if opposing_starter else None,
                opposing_starter_season_era=opp_starter_era, opposing_starter_season_k_pct=opp_starter_k_pct,
                batting_order_actual=_batting_order_slot(batting_order_raw), lineup_confirmed=True,
                weather=weather_obs, venue_roof_type=BALLPARKS.get(game.home_team, {}).get("roof"),
            )
            hitter_rows.append(row)

    return hitter_rows, pitcher_rows


def _by_date_path(date: str) -> Path:
    return BY_DATE_DIR / f"{date}.json"


def run_build(start_date: str, end_date: str, resume: bool = False, force: bool = False, validate_only: bool = False) -> dict:
    ensure_directories()
    BY_DATE_DIR.mkdir(parents=True, exist_ok=True)

    universe = build_game_universe(start_date, end_date)
    effective_start = checkpoint.resolve_effective_start(start_date, resume)

    all_dates = sorted({g.game_date for g in universe if effective_start <= g.game_date <= end_date})
    crosswalk = PlayerCrosswalkBuilder()
    statcast_buffer = StatcastBuffer()

    completed_dates, failed_dates = [], []

    if not validate_only:
        for date in all_dates:
            if not force and checkpoint.is_date_complete(date):
                # Still advance the Statcast buffer for a skipped date
                # (cheap: fetch_cached_statcast_csv_text is a disk-cache
                # hit whenever this date was ever collected before, in
                # THIS run or an earlier one) -- otherwise a later date
                # in this same run would see a hole in its trailing
                # rolling window right where dates got skipped, even
                # though the underlying data was always available.
                statcast_buffer.advance_to(date)
                completed_dates.append(date)
                continue
            day_games = games_for_date(universe, date)
            try:
                hitter_rows, pitcher_rows = process_date(date, day_games, crosswalk, statcast_buffer, force=force)
                game_dicts = [vars(g) for g in day_games]
                enforce_quality_gates(hitter_rows, pitcher_rows, game_dicts)  # step 2: validate BEFORE writing
                atomic_write_text(_by_date_path(date), json.dumps({
                    "date": date, "games": game_dicts, "hitters": hitter_rows, "pitchers": pitcher_rows,
                }, default=str))  # step 3: data write
                checkpoint.mark_date_complete(date, {  # step 4: checkpoint, LAST
                    "games": len(day_games), "hitter_rows": len(hitter_rows), "pitcher_rows": len(pitcher_rows),
                })
                completed_dates.append(date)
            except Exception as exc:  # noqa: BLE001 -- one bad date must not abort the whole resumable build
                failed_dates.append({"date": date, "error": str(exc)})

    consolidated = consolidate_and_write_parquet(universe)
    return {
        "requested_start": start_date, "requested_end": end_date, "effective_start": effective_start,
        "dates_completed": checkpoint.list_completed_dates(), "dates_attempted_this_run": completed_dates,
        "failed_dates": failed_dates, **consolidated,
    }


def consolidate_and_write_parquet(universe: List[GameUniverseRow]) -> dict:
    """Idempotent: reads every per-date JSON file written so far and
    rebuilds the Parquet outputs from scratch. Safe to call standalone
    (--validate-only) or as the final step of run_build()."""
    import pandas as pd

    from historical_mlb.paths import (
        GAMES_PARQUET, HITTER_FEATURES_PARQUET, PITCHER_FEATURES_PARQUET,
        PLAYERS_PARQUET, VENUES_PARQUET,
    )

    all_hitters, all_pitchers, all_games_seen = [], [], {}
    for path in sorted(BY_DATE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        all_hitters.extend(payload["hitters"])
        all_pitchers.extend(payload["pitchers"])
        for g in payload["games"]:
            all_games_seen[g["game_pk"]] = g

    game_rows = list(all_games_seen.values())
    findings = enforce_quality_gates(all_hitters, all_pitchers, game_rows)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if game_rows:
        pd.DataFrame(game_rows).to_parquet(GAMES_PARQUET, index=False)
    if all_hitters:
        pd.DataFrame(all_hitters).to_parquet(HITTER_FEATURES_PARQUET, index=False)
    if all_pitchers:
        pd.DataFrame(all_pitchers).to_parquet(PITCHER_FEATURES_PARQUET, index=False)

    venue_rows = build_venue_crosswalk(universe)
    if venue_rows:
        pd.DataFrame([vars(v) for v in venue_rows]).to_parquet(VENUES_PARQUET, index=False)

    player_rows = _build_player_crosswalk_from_rows(all_hitters, all_pitchers)
    if player_rows:
        pd.DataFrame(player_rows).to_parquet(PLAYERS_PARQUET, index=False)

    return {
        "games": len(game_rows), "hitter_rows": len(all_hitters), "pitcher_rows": len(all_pitchers),
        "unique_hitters": len({r["player_id"] for r in all_hitters}),
        "unique_pitchers": len({r["player_id"] for r in all_pitchers}),
        "player_crosswalk_rows": len(player_rows),
        "quality_findings": findings,
    }


def _build_player_crosswalk_from_rows(hitter_rows: List[dict], pitcher_rows: List[dict]) -> List[dict]:
    """Rebuilt from the PERSISTED feature rows (not the transient
    in-memory PlayerCrosswalkBuilder used during collection) so
    consolidation is fully idempotent/re-runnable on its own -- every
    field it needs (player_id, name, team, bat_hand/throw_hand,
    game_date) is already durably on disk in each per-date file."""
    by_player: Dict[str, dict] = {}
    for row in hitter_rows + pitcher_rows:
        pid = row["player_id"]
        existing = by_player.get(pid)
        if existing is None:
            by_player[pid] = {
                "mlbam_id": pid, "player_name": row["player_name"], "team": row["team"],
                "bat_side": row.get("bat_hand"), "throw_side": row.get("throw_hand"),
                "first_seen": row["game_date"], "last_seen": row["game_date"],
                "statcast_id": pid, "bbref_id": None, "fangraphs_id": None, "retrosheet_id": None,
                "draftkings_id": None, "fantasydata_id": None, "fantasypros_id": None,
                "match_method": "mlbam_direct", "match_confidence": 1.0,
            }
        else:
            if row["game_date"] < existing["first_seen"]:
                existing["first_seen"] = row["game_date"]
            if row["game_date"] > existing["last_seen"]:
                existing["last_seen"] = row["game_date"]
                existing["team"] = row["team"]
            existing["bat_side"] = existing["bat_side"] or row.get("bat_hand")
            existing["throw_side"] = existing["throw_side"] or row.get("throw_hand")
    return list(by_player.values())
