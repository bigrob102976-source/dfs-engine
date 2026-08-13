"""Enrichment stage for advanced (Statcast) pitching metrics.

Pure data transformation on top of what research.statcast_collector
already fetched -- no network calls here, so everything in this module
is testable with a plain fixture list of dicts.

SOURCE MAP (see research/statcast_collector.py for the actual requests):

  season xba / xwOBA / xERA        -> expected_statistics leaderboard
  season GB% / hard-hit% / barrel% /
    exit velo allowed / swing% /
    whiff% (per SWING, not per pitch) -> custom leaderboard
  season fastball velocity          -> pitch_arsenals leaderboard (ff_avg_speed, falls back to si_avg_speed)
  season pitch mix / usage%         -> pitch_arsenal_stats leaderboard
  recent (last-3-starts) everything -> per-pitch search export, scoped to
                                        those exact 3 start dates

DERIVED (not raw Savant fields, computed here from real inputs -- never
invented):

  season swinging-strike% (per PITCH, matching the existing 6-16% scale
  in config/scoring_config.py) = swing_percent * whiff_percent / 100.
  Savant's own "whiff_percent" is misses-per-SWING, a different and much
  larger number (~20-35%) that would badly break that scale if used
  directly.

KNOWN LIMITATION: season CSW% (called strikes + whiffs, per pitch) is
NOT available from any of Savant's lightweight leaderboard endpoints --
computing it at the season level would require pulling and aggregating
a full season of pitch-by-pitch data per pitcher (~1-2 MB and several
seconds EACH), which this milestone deliberately avoids to keep runtime
and complexity bounded. Season csw_percent stays None; RECENT csw_percent
(a much smaller, cheap per-pitch pull) IS computed and populated.
"""

from dataclasses import dataclass, field, replace
from statistics import mean
from typing import Dict, List, Optional, Tuple

from models.pitcher import PitcherInput, TrendMetrics
from research.statcast_collector import RawStatcastData

# Statcast's own "barrel" classification: launch_speed_angle == 6.
# https://baseballsavant.mlb.com definitions -- not our own geometry, just
# reading the field Savant already classified.
_BARREL_CODE = "6"
_HARD_HIT_THRESHOLD_MPH = 95.0
_WHIFF_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked"}
_CSW_DESCRIPTIONS = _WHIFF_DESCRIPTIONS | {"called_strike"}


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text in ("-.--", "---", ".---"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _safe_int(value) -> Optional[int]:
    f = _safe_float(value)
    return int(f) if f is not None else None


def _index_by_id(rows: List[dict], id_key: str) -> Dict[str, dict]:
    index = {}
    for row in rows:
        pid = row.get(id_key)
        if pid:
            index[str(pid)] = row
    return index


def _index_pitch_mix(rows: List[dict]) -> Dict[str, Dict[str, float]]:
    """pitch_arsenal_stats has one row per (pitcher, pitch_type). Group
    into {player_id: {pitch_type: usage_percent}}."""
    mix: Dict[str, Dict[str, float]] = {}
    for row in rows:
        pid = row.get("player_id")
        pitch_type = row.get("pitch_type")
        usage = _safe_float(row.get("pitch_usage"))
        if not pid or not pitch_type or usage is None:
            continue
        mix.setdefault(str(pid), {})[pitch_type] = usage
    return mix


@dataclass
class SeasonLeaderboardIndex:
    expected_statistics: Dict[str, dict]
    custom_leaderboard: Dict[str, dict]
    pitch_arsenals: Dict[str, dict]
    pitch_mix_by_player: Dict[str, Dict[str, float]]


def index_season_leaderboards(raw: RawStatcastData) -> SeasonLeaderboardIndex:
    return SeasonLeaderboardIndex(
        expected_statistics=_index_by_id(raw.expected_statistics, "player_id"),
        custom_leaderboard=_index_by_id(raw.custom_leaderboard, "player_id"),
        pitch_arsenals=_index_by_id(raw.pitch_arsenals, "pitcher"),  # this one leaderboard uses "pitcher", not "player_id"
        pitch_mix_by_player=_index_pitch_mix(raw.pitch_arsenal_stats),
    )


# ----------------------------------------------------------------------------
# Typed, provenance-tagged lines
# ----------------------------------------------------------------------------


@dataclass
class SeasonStatcastLine:
    player_id: str
    season: str
    xba: Optional[float] = None
    xwoba: Optional[float] = None
    xera: Optional[float] = None
    ground_ball_percent: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    avg_exit_velocity_allowed: Optional[float] = None
    swinging_strike_percent: Optional[float] = None  # derived: swing% * whiff% / 100
    csw_percent: Optional[float] = None  # always None this milestone -- see module docstring
    velocity: Optional[float] = None  # ff_avg_speed, or si_avg_speed if no four-seamer
    pitch_mix: Optional[Dict[str, float]] = None
    sample_size_pa: Optional[int] = None
    retrieved_at: str = ""
    source: str = "baseball_savant"
    stat_scope: str = "season"


@dataclass
class RecentStatcastLine:
    player_id: str
    season: str
    velocity: Optional[float] = None
    csw_percent: Optional[float] = None
    swinging_strike_percent: Optional[float] = None
    hard_hit_percent: Optional[float] = None
    barrel_percent: Optional[float] = None
    ground_ball_percent: Optional[float] = None
    avg_exit_velocity_allowed: Optional[float] = None
    pitch_mix: Optional[Dict[str, float]] = None
    sample_size_pitches: int = 0
    starts_covered: int = 0
    retrieved_at: str = ""
    source: str = "baseball_savant"
    stat_scope: str = "last_3_starts"


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------


def parse_season_statcast(index: SeasonLeaderboardIndex, player_id: str, season: str, retrieved_at: str) -> Optional[SeasonStatcastLine]:
    expected = index.expected_statistics.get(player_id)
    custom = index.custom_leaderboard.get(player_id)
    arsenal = index.pitch_arsenals.get(player_id)
    pitch_mix = index.pitch_mix_by_player.get(player_id)

    if not any([expected, custom, arsenal, pitch_mix]):
        return None

    xba = xwoba = xera = None
    if expected:
        xba = _safe_float(expected.get("est_ba"))
        xwoba = _safe_float(expected.get("est_woba"))
        xera = _safe_float(expected.get("xera"))

    ground_ball_percent = hard_hit_percent = avg_exit_velocity_allowed = None
    swinging_strike_percent = None
    sample_size_pa = None
    if custom:
        ground_ball_percent = _safe_float(custom.get("groundballs_percent"))
        hard_hit_percent = _safe_float(custom.get("hard_hit_percent"))
        barrel_percent = _safe_float(custom.get("barrel_batted_rate"))
        avg_exit_velocity_allowed = _safe_float(custom.get("exit_velocity_avg"))
        sample_size_pa = _safe_int(custom.get("pa"))
        swing_percent = _safe_float(custom.get("swing_percent"))
        whiff_percent = _safe_float(custom.get("whiff_percent"))  # misses per SWING (Savant's definition)
        if swing_percent is not None and whiff_percent is not None:
            swinging_strike_percent = round(swing_percent * whiff_percent / 100.0, 1)
    else:
        barrel_percent = None

    velocity = None
    if arsenal:
        velocity = _safe_float(arsenal.get("ff_avg_speed"))
        if velocity is None:
            velocity = _safe_float(arsenal.get("si_avg_speed"))  # sinkerballers: no four-seamer

    return SeasonStatcastLine(
        player_id=player_id,
        season=season,
        xba=xba,
        xwoba=xwoba,
        xera=xera,
        ground_ball_percent=ground_ball_percent,
        hard_hit_percent=hard_hit_percent,
        barrel_percent=barrel_percent,
        avg_exit_velocity_allowed=avg_exit_velocity_allowed,
        swinging_strike_percent=swinging_strike_percent,
        velocity=velocity,
        pitch_mix=pitch_mix,
        sample_size_pa=sample_size_pa,
        retrieved_at=retrieved_at,
    )


def parse_recent_statcast(pitch_rows: Optional[List[dict]], player_id: str, season: str, retrieved_at: str) -> Optional[RecentStatcastLine]:
    if not pitch_rows:
        return None

    total_pitches = len(pitch_rows)
    csw_count = 0
    whiff_count = 0
    pitch_type_counts: Dict[str, int] = {}
    fastball_speeds: List[float] = []
    game_dates = set()

    in_play_rows = []
    for row in pitch_rows:
        description = row.get("description") or ""
        if description in _CSW_DESCRIPTIONS:
            csw_count += 1
        if description in _WHIFF_DESCRIPTIONS:
            whiff_count += 1

        pitch_type = row.get("pitch_type") or ""
        if pitch_type:
            pitch_type_counts[pitch_type] = pitch_type_counts.get(pitch_type, 0) + 1
            speed = _safe_float(row.get("release_speed"))
            if pitch_type == "FF" and speed is not None:
                fastball_speeds.append(speed)

        if row.get("game_date"):
            game_dates.add(row["game_date"])

        if row.get("bb_type"):
            in_play_rows.append(row)

    # No four-seamers thrown in the window -- fall back to sinker velocity.
    if not fastball_speeds:
        for row in pitch_rows:
            if row.get("pitch_type") == "SI":
                speed = _safe_float(row.get("release_speed"))
                if speed is not None:
                    fastball_speeds.append(speed)

    velocity = round(mean(fastball_speeds), 1) if fastball_speeds else None
    csw_percent = round(csw_count / total_pitches * 100.0, 1) if total_pitches else None
    swinging_strike_percent = round(whiff_count / total_pitches * 100.0, 1) if total_pitches else None

    hard_hit_percent = barrel_percent = ground_ball_percent = avg_exit_velocity_allowed = None
    if in_play_rows:
        exit_velocities = [_safe_float(r.get("launch_speed")) for r in in_play_rows]
        exit_velocities = [v for v in exit_velocities if v is not None]
        if exit_velocities:
            avg_exit_velocity_allowed = round(mean(exit_velocities), 1)
            hard_hit_percent = round(sum(1 for v in exit_velocities if v >= _HARD_HIT_THRESHOLD_MPH) / len(exit_velocities) * 100.0, 1)
        barrel_count = sum(1 for r in in_play_rows if (r.get("launch_speed_angle") or "").strip() == _BARREL_CODE)
        barrel_percent = round(barrel_count / len(in_play_rows) * 100.0, 1)
        gb_count = sum(1 for r in in_play_rows if r.get("bb_type") == "ground_ball")
        ground_ball_percent = round(gb_count / len(in_play_rows) * 100.0, 1)

    pitch_mix = None
    if pitch_type_counts:
        pitch_mix = {pt: round(count / total_pitches * 100.0, 1) for pt, count in pitch_type_counts.items()}

    return RecentStatcastLine(
        player_id=player_id,
        season=season,
        velocity=velocity,
        csw_percent=csw_percent,
        swinging_strike_percent=swinging_strike_percent,
        hard_hit_percent=hard_hit_percent,
        barrel_percent=barrel_percent,
        ground_ball_percent=ground_ball_percent,
        avg_exit_velocity_allowed=avg_exit_velocity_allowed,
        pitch_mix=pitch_mix,
        sample_size_pitches=total_pitches,
        starts_covered=len(game_dates),
        retrieved_at=retrieved_at,
    )


# ----------------------------------------------------------------------------
# Derived trends -- the Research Engine's job, never the Pitcher Agent's
# ----------------------------------------------------------------------------


def compute_trends(season_line: Optional[SeasonStatcastLine], recent_line: Optional[RecentStatcastLine]) -> Dict[str, Optional[float]]:
    """(recent - season) for every metric where higher-is-better-for-the-
    pitcher, EXCEPT hard_hit/barrel which are inverted (season - recent)
    so a positive trend value always means "moved in the pitcher's favor"
    -- see TrendMetrics' docstring. Any metric missing on either side
    stays None; nothing is estimated or interpolated."""

    def _delta(recent_value, season_value, invert=False):
        if recent_value is None or season_value is None:
            return None
        delta = recent_value - season_value
        return round(-delta if invert else delta, 2)

    season = season_line
    recent = recent_line

    trends = {
        "velocity_trend": _delta(recent.velocity if recent else None, season.velocity if season else None),
        "csw_trend": _delta(recent.csw_percent if recent else None, season.csw_percent if season else None),
        "swinging_strike_trend": _delta(recent.swinging_strike_percent if recent else None, season.swinging_strike_percent if season else None),
        "hard_hit_trend": _delta(recent.hard_hit_percent if recent else None, season.hard_hit_percent if season else None, invert=True),
        "barrel_trend": _delta(recent.barrel_percent if recent else None, season.barrel_percent if season else None, invert=True),
        "ground_ball_trend": _delta(recent.ground_ball_percent if recent else None, season.ground_ball_percent if season else None),
        "pitch_mix_change": None,
    }

    season_mix = season.pitch_mix if season else None
    recent_mix = recent.pitch_mix if recent else None
    if season_mix and recent_mix:
        pitch_types = set(season_mix) | set(recent_mix)
        trends["pitch_mix_change"] = round(sum(abs(recent_mix.get(pt, 0.0) - season_mix.get(pt, 0.0)) for pt in pitch_types), 1)

    return trends


# ----------------------------------------------------------------------------
# Merge into PitcherInput
# ----------------------------------------------------------------------------


def apply_statcast_to_pitcher_inputs(
    pitcher_inputs: List[PitcherInput],
    raw_statcast: RawStatcastData,
    retrieved_at: str,
) -> Tuple[List[PitcherInput], List[dict]]:
    index = index_season_leaderboards(raw_statcast)
    enriched: List[PitcherInput] = []
    provenance: List[dict] = []

    for p in pitcher_inputs:
        season_line = parse_season_statcast(index, p.player_id, raw_statcast.season, retrieved_at)
        recent_line = parse_recent_statcast(raw_statcast.recent_pitch_level.get(p.player_id), p.player_id, raw_statcast.season, retrieved_at)
        trend_values = compute_trends(season_line, recent_line)

        new_season = p.season
        if season_line:
            new_season = replace(
                p.season,
                xba=season_line.xba,
                xwoba_allowed=season_line.xwoba,
                xera=season_line.xera,
                ground_ball_percent=season_line.ground_ball_percent,
                hard_hit_percent=season_line.hard_hit_percent,
                barrel_percent=season_line.barrel_percent,
                avg_exit_velocity_allowed=season_line.avg_exit_velocity_allowed,
                swinging_strike_percent=season_line.swinging_strike_percent,
                pitch_mix=season_line.pitch_mix,
            )
            provenance.append({"type": "season_statcast", **season_line.__dict__})

        new_recent = p.recent
        if recent_line:
            new_recent = replace(
                p.recent,
                velocity=recent_line.velocity,
                # Existing (Milestone 2) field: season-level fastball velocity,
                # read by agents/pitcher_agent.py's velocity_change calculation.
                season_velocity=season_line.velocity if season_line else p.recent.season_velocity,
                csw_percent=recent_line.csw_percent,
                swinging_strike_percent=recent_line.swinging_strike_percent,
                hard_hit_percent=recent_line.hard_hit_percent,
                barrel_percent=recent_line.barrel_percent,
                ground_ball_percent=recent_line.ground_ball_percent,
                avg_exit_velocity_allowed=recent_line.avg_exit_velocity_allowed,
                pitch_mix=recent_line.pitch_mix,
                starts_sampled=recent_line.starts_covered,
            )
            provenance.append({"type": "recent_statcast", **recent_line.__dict__})
        elif season_line and season_line.velocity is not None and p.recent.season_velocity is None:
            # No recent pitch-level data, but season velocity is still worth recording.
            new_recent = replace(p.recent, season_velocity=season_line.velocity)

        new_trends = TrendMetrics(**trend_values)
        if any(v is not None for v in trend_values.values()):
            provenance.append({
                "type": "trends", "player_id": p.player_id, "season": raw_statcast.season,
                "retrieved_at": retrieved_at, "source": "baseball_savant", "stat_scope": "recent_vs_season",
                **trend_values,
            })

        enriched.append(replace(p, season=new_season, recent=new_recent, trends=new_trends))

    return enriched, provenance
