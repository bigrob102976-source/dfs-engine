"""Milestone 32.2B -- builds today's pregame pitcher features using the
EXACT SAME feature-computation functions historical_models.pitcher_v1
was trained against (historical_mlb.rolling / historical_mlb.
statcast_aggregation), fed by freshly live-fetched data instead of
warehouse parquet rows.

This module never redefines a feature's math -- see feature_parity.py
for the per-column audit proving that. It only supplies live inputs
(current-season game log, trailing-30-day Statcast buffer, live
handedness, static roof lookup) in the exact shapes those training
functions already expect.

IMPORTANT -- import boundary: historical_mlb.pitcher_features,
historical_mlb.hitter_features, historical_mlb.scoring, and
historical_mlb.sources.mlb_stats all import evaluation.* at module
scope (they build POSTGAME rows for the historical warehouse). This
module is part of the LIVE PREGAME path and must never import
evaluation, even transitively (see tests/test_architecture_separation.py)
-- so it imports research.collector directly (the same underlying live
fetchers those historical_mlb modules re-export) and historical_mlb.
sources.statcast/historical_mlb.rolling/historical_mlb.
statcast_aggregation (none of which import evaluation), rather than
going through the historical_mlb.sources.mlb_stats /
historical_mlb.warehouse_builder wrappers. A few tiny (<10 line), pure,
non-scoring helpers (game-log unwrapping, handedness extraction, the
Statcast sliding-window buffer) are mirrored verbatim below rather than
imported, purely to keep this import boundary clean -- not a second
feature-definition system, just avoiding evaluation-importing modules.

Weather is deliberately NOT fetched here (see feature_parity.py --
MISSING, not fabricated); every weather_* feature is left None and the
frozen HistGradientBoostingRegressor natively tolerates that (same
mechanism it uses for any other missing value).
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import date as date_cls, timedelta
from typing import Dict, List, Optional

from config.game_environment_config import BALLPARKS
from historical_mlb.rolling import aggregate_statcast_rates, build_rolling_pitcher_stats, days_between
from historical_mlb.sources.statcast import fetch_cached_statcast_csv_text, parse_statcast_csv
from historical_mlb.statcast_aggregation import opponent_offense_aggregate, pitcher_platoon_splits_allowed
from research.collector import fetch_person, fetch_pitcher_game_log

_ROLLING_WINDOWS = [("7d", 7), ("14d", 14), ("30d", 30), ("season", None)]
_STATCAST_WINDOWS = [("14d", 14), ("30d", 30), ("season", None)]

STATCAST_BUFFER_LOOKBACK_DAYS = 30


def _previous_start(season_game_log: List[dict], target_game_date: str) -> Optional[dict]:
    """Verbatim mirror of historical_mlb.pitcher_features._previous_start
    (most recent PRIOR appearance strictly before target_game_date)."""
    prior = sorted(
        (e for e in season_game_log if e.get("date") and e["date"] < target_game_date),
        key=lambda e: e["date"],
    )
    return prior[-1] if prior else None


def _unwrap_game_log(raw: Optional[dict]) -> List[dict]:
    """Mirrors historical_mlb.sources.mlb_stats.
    fetch_cached_season_game_log's inner unwrapping -- same MLB Stats API
    envelope, same {"date":..., "stat":...} flattening. Hardened against
    a real MLB Stats API response shape ({"stats": []}, e.g. a rookie
    with zero games recorded yet this season) that would otherwise raise
    IndexError on the mirrored [0] access."""
    stats_list = (raw or {}).get("stats") or []
    splits = stats_list[0].get("splits", []) if stats_list else []
    return [{"date": s.get("date"), "stat": s.get("stat", {})} for s in splits if s.get("date")]


def _person_handedness(person: Optional[dict]) -> Dict[str, Optional[str]]:
    """Verbatim mirror of historical_mlb.sources.mlb_stats.person_handedness."""
    if not person:
        return {"bat_side": None, "throw_hand": None}
    return {
        "bat_side": (person.get("batSide") or {}).get("code"),
        "throw_hand": (person.get("pitchHand") or {}).get("code"),
    }


class LiveStatcastBuffer:
    """Verbatim mirror of historical_mlb.warehouse_builder.StatcastBuffer's
    sliding-window logic, built on the evaluation-free
    historical_mlb.sources.statcast fetchers directly."""

    def __init__(self, lookback_days: int = STATCAST_BUFFER_LOOKBACK_DAYS):
        self._by_date: Dict[str, List[dict]] = {}
        self._order = deque()
        self._lookback_days = lookback_days

    def advance_to(self, date: str, force: bool = False) -> None:
        if date in self._by_date and not force:
            return
        text = fetch_cached_statcast_csv_text(date, force=force)
        self._by_date[date] = parse_statcast_csv(text) if text else []
        self._order.append(date)
        self._evict_older_than(date)

    def _evict_older_than(self, current_date: str) -> None:
        while self._order and days_between(self._order[0], current_date) > self._lookback_days:
            old = self._order.popleft()
            self._by_date.pop(old, None)

    def rows(self) -> List[dict]:
        out: List[dict] = []
        for rows in self._by_date.values():
            out.extend(rows)
        return out


@dataclass
class LivePregameFeatureResult:
    player_id: str
    features: Dict
    warnings: List[str] = field(default_factory=list)


def build_live_statcast_buffer(as_of_date: str, lookback_days: int = STATCAST_BUFFER_LOOKBACK_DAYS) -> LiveStatcastBuffer:
    """One shared buffer for an entire slate run -- every eligible
    pitcher's statcast/platoon/opponent features are computed from this
    SAME buffer, so the trailing-window Savant fetches happen once per
    run, not once per pitcher."""
    buffer = LiveStatcastBuffer(lookback_days=lookback_days)
    year, month, day = (int(x) for x in as_of_date.split("-"))
    target = date_cls(year, month, day)
    for offset in range(lookback_days, 0, -1):
        d = (target - timedelta(days=offset)).isoformat()
        buffer.advance_to(d)
    return buffer


def build_live_pregame_pitcher_features(
    *,
    player_id: str,
    team: str,
    opponent: str,
    home_away: str,
    as_of_date: str,
    venue_id: Optional[int],
    statcast_buffer: LiveStatcastBuffer,
) -> LivePregameFeatureResult:
    """Mirrors historical_mlb.pitcher_features.build_pitcher_game_row's
    PREGAME portion exactly (same sub-function calls, same argument
    order), but never requires a boxscore_entry -- there is no outcome
    yet for a game that hasn't been played."""
    warnings: List[str] = []
    season = as_of_date[:4]

    season_game_log = _unwrap_game_log(fetch_pitcher_game_log(player_id, season))
    if not season_game_log:
        warnings.append(f"No current-season game log for player {player_id} -- rolling_*/workload features will be None (first start of the season, or genuinely no data).")

    statcast_rows = statcast_buffer.rows()

    person = fetch_person(player_id)
    handedness = _person_handedness(person)
    if handedness.get("throw_hand") is None:
        warnings.append(f"No throw_hand available from MLB Stats API for player {player_id}.")

    home_team = team if home_away == "home" else opponent
    venue_roof_type = (BALLPARKS.get(home_team) or {}).get("roof")

    row: Dict = {
        "team": team, "opponent": opponent, "home_away": home_away, "venue_id": venue_id,
        "throw_hand": handedness.get("throw_hand"), "bat_hand": handedness.get("bat_side"),
    }

    for label, days in _ROLLING_WINDOWS:
        stats = build_rolling_pitcher_stats(season_game_log, target_game_date=as_of_date, window_days=days, window_label=label)
        row[f"rolling_outs_{label}"] = stats.outs
        row[f"rolling_ip_{label}"] = stats.innings_pitched
        row[f"rolling_bf_{label}"] = stats.batters_faced
        row[f"rolling_so_{label}"] = stats.strikeouts
        row[f"rolling_bb_{label}"] = stats.walks
        row[f"rolling_h_{label}"] = stats.hits_allowed
        row[f"rolling_hr_{label}"] = stats.home_runs_allowed
        row[f"rolling_er_{label}"] = stats.earned_runs
        row[f"rolling_pitch_count_{label}"] = stats.pitch_count
        row[f"rolling_k_pct_{label}"] = stats.k_rate
        row[f"rolling_bb_pct_{label}"] = stats.bb_rate
        row[f"rolling_k_minus_bb_pct_{label}"] = round(stats.k_rate - stats.bb_rate, 4) if stats.k_rate is not None and stats.bb_rate is not None else None
        row[f"rolling_era_{label}"] = stats.era
        row[f"rolling_whip_{label}"] = stats.whip
        row[f"rolling_hr_rate_{label}"] = round(stats.home_runs_allowed / stats.batters_faced, 4) if stats.batters_faced else None
        row[f"rolling_starts_{label}"] = stats.games

    previous = _previous_start(season_game_log, as_of_date)
    row["days_rest"] = days_between(previous["date"], as_of_date) if previous else None
    row["previous_start_pitch_count"] = (previous or {}).get("stat", {}).get("numberOfPitches") if previous else None
    starts_30d = build_rolling_pitcher_stats(season_game_log, target_game_date=as_of_date, window_days=30, window_label="starts_30d")
    row["starts_last_30d"] = starts_30d.games
    row["innings_last_30d"] = starts_30d.innings_pitched

    for label, days in _STATCAST_WINDOWS:
        if days is not None:
            window_rows = [r for r in statcast_rows if r.get("game_date") and days_between(r["game_date"], as_of_date) <= days]
        else:
            window_rows = statcast_rows
        agg = aggregate_statcast_rates(window_rows, "pitcher", player_id)
        row[f"statcast_avg_exit_velocity_allowed_{label}"] = agg["avg_exit_velocity"]
        row[f"statcast_avg_launch_angle_allowed_{label}"] = agg["avg_launch_angle"]
        row[f"statcast_hard_hit_rate_allowed_{label}"] = agg["hard_hit_rate"]
        row[f"statcast_barrel_rate_allowed_{label}"] = agg["barrel_rate_proxy"]
        row[f"statcast_xwoba_allowed_{label}"] = agg["avg_xwoba_contribution"]
        row[f"statcast_xslg_allowed_{label}"] = agg["xslg"]
        row[f"statcast_batted_balls_allowed_{label}"] = agg["batted_ball_events"]

    platoon = pitcher_platoon_splits_allowed(statcast_rows, player_id)
    for side in ("vs_lhb", "vs_rhb"):
        row[f"platoon_{side}_bf"] = platoon[side]["pa"]
        row[f"platoon_{side}_avg_allowed"] = platoon[side]["avg"]
        row[f"platoon_{side}_obp_allowed"] = platoon[side]["obp"]
        row[f"platoon_{side}_slg_allowed"] = platoon[side]["slg"]
        row[f"platoon_{side}_woba_allowed"] = platoon[side]["woba"]

    opponent_offense = opponent_offense_aggregate(statcast_rows, opponent)
    row["opponent_k_pct_season"] = opponent_offense.get("k_pct")
    row["opponent_bb_pct_season"] = opponent_offense.get("bb_pct")
    row["opponent_hr_rate_season"] = opponent_offense.get("hr_rate")
    row["opponent_woba_season"] = opponent_offense.get("woba")
    row["opponent_sample_games"] = opponent_offense.get("sample_games")

    # Weather: MISSING in live V1 (see feature_parity.py) -- never fabricated.
    row["weather_available"] = False
    row["weather_source"] = None
    row["weather_temperature_f"] = None
    row["weather_wind_speed_mph"] = None
    row["weather_wind_direction_deg"] = None
    row["weather_precipitation"] = None
    row["weather_humidity_pct"] = None
    row["venue_roof_type"] = venue_roof_type

    return LivePregameFeatureResult(player_id=str(player_id), features=row, warnings=warnings)
