"""Enrichment stage for advanced (Statcast) hitting metrics.

Pure data transformation on top of what research.statcast_batter_collector
already fetched -- no network calls. Mirrors research/statcast_enrichment.py
(the pitcher version) exactly in spirit.

SOURCE MAP:

  season xBA / xSLG / xwOBA / wOBA        -> expected_statistics leaderboard
                                              (wOBA here is Savant's own real
                                              number -- preferred over the
                                              platoon-split approximation in
                                              research/batter_enrichment.py)
  season K%/BB%/hard-hit%/barrel%/exit
    velocity/launch angle/sweet-spot%/
    bat speed/GB%                         -> custom leaderboard
  recent (last-14-days) everything         -> per-pitch search export

KNOWN LIMITATIONS (see research/statcast_batter_collector.py for what was
actually tested): season max exit velocity, squared-up%, and swing length
are not reliably exposed by the structured endpoints used here and stay
None. Recent-window max exit velocity IS available (computed from the
per-pitch pull, same technique as the pitcher CSW recent-window).
"""

from dataclasses import dataclass, replace
from statistics import mean
from typing import Dict, List, Optional, Tuple

from models.batter import BatterInput, TrendMetrics
from research.statcast_batter_collector import RawBatterStatcastData

_BARREL_CODE = "6"
_HARD_HIT_THRESHOLD_MPH = 95.0
_MIN_PITCH_TYPE_SAMPLE = 3  # minimum PA-ending events of one pitch type before reporting a wOBA for it


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "-.--", "---", ".---"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _safe_int(value) -> Optional[int]:
    f = _safe_float(value)
    return int(f) if f is not None else None


def _index_by_id(rows: List[dict], id_key: str = "player_id") -> Dict[str, dict]:
    index = {}
    for row in rows:
        pid = row.get(id_key)
        if pid:
            index[str(pid)] = row
    return index


@dataclass
class SeasonLeaderboardIndex:
    expected_statistics: Dict[str, dict]
    custom_leaderboard: Dict[str, dict]


def index_season_leaderboards(raw: RawBatterStatcastData) -> SeasonLeaderboardIndex:
    return SeasonLeaderboardIndex(
        expected_statistics=_index_by_id(raw.expected_statistics),
        custom_leaderboard=_index_by_id(raw.custom_leaderboard),
    )


# ----------------------------------------------------------------------------
# Typed, provenance-tagged lines
# ----------------------------------------------------------------------------


@dataclass
class SeasonBatterStatcastLine:
    player_id: str
    season: str
    xba: Optional[float] = None
    xslg: Optional[float] = None
    xwoba: Optional[float] = None
    woba: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    exit_velocity: Optional[float] = None
    launch_angle: Optional[float] = None
    sweet_spot_percent: Optional[float] = None
    bat_speed: Optional[float] = None
    sample_size_pa: Optional[int] = None
    retrieved_at: str = ""
    source: str = "baseball_savant"
    stat_scope: str = "season"


@dataclass
class RecentBatterStatcastLine:
    player_id: str
    season: str
    xwoba: Optional[float] = None
    exit_velocity: Optional[float] = None
    max_exit_velocity: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    launch_angle: Optional[float] = None
    pitch_type_performance: Optional[Dict[str, float]] = None
    sample_size_pitches: int = 0
    retrieved_at: str = ""
    source: str = "baseball_savant"
    stat_scope: str = "last_14_days"


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------


def parse_season_batter_statcast(index: SeasonLeaderboardIndex, player_id: str, season: str, retrieved_at: str) -> Optional[SeasonBatterStatcastLine]:
    expected = index.expected_statistics.get(player_id)
    custom = index.custom_leaderboard.get(player_id)
    if not expected and not custom:
        return None

    xba = xslg = xwoba = woba = None
    if expected:
        xba = _safe_float(expected.get("est_ba"))
        xslg = _safe_float(expected.get("est_slg"))
        xwoba = _safe_float(expected.get("est_woba"))
        woba = _safe_float(expected.get("woba"))

    hard_hit_percent = barrel_percent = exit_velocity = launch_angle = sweet_spot_percent = bat_speed = sample_size_pa = None
    if custom:
        hard_hit_percent = _safe_float(custom.get("hard_hit_percent"))
        barrel_percent = _safe_float(custom.get("barrel_batted_rate"))
        exit_velocity = _safe_float(custom.get("exit_velocity_avg"))
        launch_angle = _safe_float(custom.get("launch_angle_avg"))
        sweet_spot_percent = _safe_float(custom.get("sweet_spot_percent"))
        bat_speed = _safe_float(custom.get("avg_swing_speed"))
        sample_size_pa = _safe_int(custom.get("pa"))

    return SeasonBatterStatcastLine(
        player_id=player_id, season=season,
        xba=xba, xslg=xslg, xwoba=xwoba, woba=woba,
        hard_hit_percent=hard_hit_percent, barrel_percent=barrel_percent,
        exit_velocity=exit_velocity, launch_angle=launch_angle,
        sweet_spot_percent=sweet_spot_percent, bat_speed=bat_speed,
        sample_size_pa=sample_size_pa, retrieved_at=retrieved_at,
    )


def parse_recent_batter_statcast(pitch_rows: Optional[List[dict]], player_id: str, season: str, retrieved_at: str) -> Optional[RecentBatterStatcastLine]:
    if not pitch_rows:
        return None

    total_pitches = len(pitch_rows)
    in_play_rows = [r for r in pitch_rows if r.get("bb_type")]
    pa_ending_rows = [r for r in pitch_rows if r.get("woba_value") not in (None, "")]

    exit_velocity = max_exit_velocity = hard_hit_percent = barrel_percent = launch_angle = None
    if in_play_rows:
        exit_velocities = [_safe_float(r.get("launch_speed")) for r in in_play_rows]
        exit_velocities = [v for v in exit_velocities if v is not None]
        if exit_velocities:
            exit_velocity = round(mean(exit_velocities), 1)
            max_exit_velocity = round(max(exit_velocities), 1)
            hard_hit_percent = round(sum(1 for v in exit_velocities if v >= _HARD_HIT_THRESHOLD_MPH) / len(exit_velocities) * 100.0, 1)
        barrel_count = sum(1 for r in in_play_rows if (r.get("launch_speed_angle") or "").strip() == _BARREL_CODE)
        barrel_percent = round(barrel_count / len(in_play_rows) * 100.0, 1)
        launch_angles = [_safe_float(r.get("launch_angle")) for r in in_play_rows]
        launch_angles = [v for v in launch_angles if v is not None]
        if launch_angles:
            launch_angle = round(mean(launch_angles), 1)

    xwoba = None
    if pa_ending_rows:
        xwoba_values = [_safe_float(r.get("estimated_woba_using_speedangle")) for r in pa_ending_rows]
        xwoba_values = [v for v in xwoba_values if v is not None]
        if xwoba_values:
            xwoba = round(mean(xwoba_values), 3)

    pitch_type_performance = None
    by_pitch_type: Dict[str, List[float]] = {}
    for r in pa_ending_rows:
        pitch_type = r.get("pitch_type")
        woba_value = _safe_float(r.get("woba_value"))
        if pitch_type and woba_value is not None:
            by_pitch_type.setdefault(pitch_type, []).append(woba_value)
    if by_pitch_type:
        pitch_type_performance = {
            pt: round(mean(values), 3) for pt, values in by_pitch_type.items() if len(values) >= _MIN_PITCH_TYPE_SAMPLE
        }
        if not pitch_type_performance:
            pitch_type_performance = None

    return RecentBatterStatcastLine(
        player_id=player_id, season=season,
        xwoba=xwoba, exit_velocity=exit_velocity, max_exit_velocity=max_exit_velocity,
        hard_hit_percent=hard_hit_percent, barrel_percent=barrel_percent, launch_angle=launch_angle,
        pitch_type_performance=pitch_type_performance,
        sample_size_pitches=total_pitches, retrieved_at=retrieved_at,
    )


# ----------------------------------------------------------------------------
# Derived trends -- Research Engine's job, never the Batter Agent's.
# strikeout_rate_trend/walk_rate_trend come from the ALREADY MLB-stats-
# enriched season/recent K%/BB% (research.batter_enrichment runs first in
# the pipeline), not from Statcast -- this function is the one place that
# combines both sources into TrendMetrics.
# ----------------------------------------------------------------------------


def compute_trends(
    season_line: Optional[SeasonBatterStatcastLine],
    recent_line: Optional[RecentBatterStatcastLine],
    season_k_percent: Optional[float],
    recent_k_percent: Optional[float],
    season_bb_percent: Optional[float],
    recent_bb_percent: Optional[float],
) -> Dict[str, Optional[float]]:
    def _delta(recent_value, season_value):
        if recent_value is None or season_value is None:
            return None
        return round(recent_value - season_value, 3)

    season = season_line
    recent = recent_line

    return {
        "exit_velocity_trend": _delta(recent.exit_velocity if recent else None, season.exit_velocity if season else None),
        "hard_hit_trend": _delta(recent.hard_hit_percent if recent else None, season.hard_hit_percent if season else None),
        "barrel_trend": _delta(recent.barrel_percent if recent else None, season.barrel_percent if season else None),
        "xwoba_trend": _delta(recent.xwoba if recent else None, season.xwoba if season else None),
        # Inverted: fewer strikeouts recently (lower K%) is favorable for a hitter.
        "strikeout_rate_trend": _delta(season_k_percent, recent_k_percent),
        "walk_rate_trend": _delta(recent_bb_percent, season_bb_percent),
    }


# ----------------------------------------------------------------------------
# Merge into BatterInput
# ----------------------------------------------------------------------------


def apply_statcast_to_batter_inputs(
    batter_inputs: List[BatterInput],
    raw_statcast: RawBatterStatcastData,
    retrieved_at: str,
) -> Tuple[List[BatterInput], List[dict]]:
    index = index_season_leaderboards(raw_statcast)
    enriched: List[BatterInput] = []
    provenance: List[dict] = []

    for p in batter_inputs:
        season_line = parse_season_batter_statcast(index, p.player_id, raw_statcast.season, retrieved_at)
        recent_line = parse_recent_batter_statcast(raw_statcast.recent_pitch_level.get(p.player_id), p.player_id, raw_statcast.season, retrieved_at)

        new_season = p.season
        if season_line:
            new_season = replace(
                p.season,
                xba=season_line.xba,
                xslg=season_line.xslg,
                xwoba=season_line.xwoba,
                woba=season_line.woba if season_line.woba is not None else p.season.woba,
                hard_hit_percent=season_line.hard_hit_percent,
                barrel_percent=season_line.barrel_percent,
                exit_velocity=season_line.exit_velocity,
                launch_angle=season_line.launch_angle,
                sweet_spot_percent=season_line.sweet_spot_percent,
                bat_speed=season_line.bat_speed,
            )
            provenance.append({"type": "season_batter_statcast", **season_line.__dict__})

        new_recent = p.recent
        if recent_line:
            new_recent = replace(
                p.recent,
                xwoba=recent_line.xwoba,
                exit_velocity=recent_line.exit_velocity,
                max_exit_velocity=recent_line.max_exit_velocity,
                hard_hit_percent=recent_line.hard_hit_percent,
                barrel_percent=recent_line.barrel_percent,
                launch_angle=recent_line.launch_angle,
                pitch_type_performance=recent_line.pitch_type_performance,
                sample_size_pitches=recent_line.sample_size_pitches,
            )
            provenance.append({"type": "recent_batter_statcast", **recent_line.__dict__})

        trend_values = compute_trends(
            season_line, recent_line,
            p.season.k_percent, p.recent.k_percent,
            p.season.bb_percent, p.recent.bb_percent,
        )
        new_trends = TrendMetrics(**trend_values)
        if any(v is not None for v in trend_values.values()):
            provenance.append({
                "type": "batter_trends", "player_id": p.player_id, "season": raw_statcast.season,
                "retrieved_at": retrieved_at, "source": "baseball_savant", "stat_scope": "recent_vs_season",
                **trend_values,
            })

        enriched.append(replace(p, season=new_season, recent=new_recent, trends=new_trends))

    return enriched, provenance
