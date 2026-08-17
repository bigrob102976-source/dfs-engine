"""Enrichment stage: turn raw MLB Stats API stat payloads (already
fetched by research.collector) into typed, provenance-tagged stat lines,
and merge them onto PitcherInput objects built by
research.adapters.pitcher_input.

Pure data transformation -- no network calls here. Every function in
this module can be tested with a plain fixture dict.

Formulas (per milestone spec, batters-faced as the denominator, not
innings):

    K%    = strikeouts / batters_faced
    BB%   = walks / batters_faced
    K-BB% = K% - BB%

FIP is intentionally NOT computed as official FIP: the standard formula
needs a season-specific FIP constant, and we don't have a trustworthy
source for it yet. We compute the constant-free component
(`fip_without_constant`) for transparency/provenance only, and never
write it into PitcherInput.season.fip -- that field stays None rather
than silently mislabeling an approximation as the real thing.
"""

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Tuple

from models.pitcher import PitcherInput
from research import innings
from research.collector import RawPitcherStats

# ----------------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------------


def compute_rate_percent(numerator: int, denominator: int) -> Optional[float]:
    """numerator / denominator * 100, guarding against a zero (or
    missing) denominator. Returns None rather than raising or fabricating
    a rate -- a pitcher with zero recorded batters faced has no K%/BB%,
    not a 0% one."""
    if not denominator:
        return None
    return round((numerator / denominator) * 100.0, 1)


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _first_split_stat(raw: Optional[dict]) -> Optional[dict]:
    """MLB Stats API's people/teams stats responses all share this
    shape: {"stats": [{"splits": [{"stat": {...}}]}]}. Returns the first
    split's "stat" dict, or None if the payload is missing/empty (e.g. a
    pitcher with no innings recorded yet this season)."""
    if not raw:
        return None
    stats_list = raw.get("stats") or []
    if not stats_list:
        return None
    splits = stats_list[0].get("splits") or []
    if not splits:
        return None
    return splits[0].get("stat")


def _outs_from_stat(stat: dict) -> Optional[int]:
    """Prefer the API's own `outs` field; fall back to parsing the
    baseball-notation `inningsPitched` string through the innings<->outs
    helper. Never treats "6.2" as an ordinary decimal."""
    if stat.get("outs") is not None:
        return _safe_int(stat["outs"])
    notation = stat.get("inningsPitched")
    if notation is None:
        return None
    try:
        return innings.innings_notation_to_outs(notation)
    except ValueError:
        return None


# ----------------------------------------------------------------------------
# Typed, provenance-tagged stat lines
# ----------------------------------------------------------------------------


@dataclass
class SeasonStatLine:
    player_id: str
    season: str
    outs: int
    innings_pitched: float  # true decimal (outs / 3.0), safe for arithmetic
    batters_faced: int
    strikeouts: int
    walks: int
    earned_runs: int
    hits_allowed: int
    home_runs_allowed: int
    hit_by_pitch: int
    era: Optional[float]
    k_percent: Optional[float]
    bb_percent: Optional[float]
    k_minus_bb_percent: Optional[float]
    fip_without_constant: Optional[float]
    retrieved_at: str
    source: str = "mlb_stats_api"
    stat_scope: str = "season"


@dataclass
class RecentStatLine:
    player_id: str
    season: str
    starts_used: int
    outs: int
    innings_pitched: float
    batters_faced: int
    strikeouts: int
    walks: int
    k_percent: Optional[float]
    bb_percent: Optional[float]
    pitch_count_average: Optional[float]
    retrieved_at: str
    source: str = "mlb_stats_api"
    stat_scope: str = "last_3_starts"
    # The actual calendar dates of the starts counted above (oldest first).
    # research.statcast_collector uses this to scope its Baseball Savant
    # pitch-level pull to exactly the same starts, rather than guessing a
    # date window -- see collect_recent_pitch_level in that module.
    start_dates: List[str] = field(default_factory=list)


@dataclass
class OpponentKRateLine:
    team_id: str
    season: str
    k_percent: float
    split_type: str  # "overall" -- handedness-specific splits come later
    retrieved_at: str
    source: str = "mlb_stats_api"
    stat_scope: str = "season"


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------


def parse_season_pitching_stats(raw: Optional[dict], player_id: str, season: str, retrieved_at: str) -> Optional[SeasonStatLine]:
    stat = _first_split_stat(raw)
    if not stat:
        return None

    outs = _outs_from_stat(stat)
    if outs is None:
        return None
    innings_decimal = round(innings.outs_to_decimal_innings(outs), 3)

    batters_faced = _safe_int(stat.get("battersFaced"))
    strikeouts = _safe_int(stat.get("strikeOuts"))
    walks = _safe_int(stat.get("baseOnBalls"))
    earned_runs = _safe_int(stat.get("earnedRuns"))
    hits_allowed = _safe_int(stat.get("hits"))
    home_runs_allowed = _safe_int(stat.get("homeRuns"))
    hit_by_pitch = _safe_int(stat.get("hitBatsmen"))
    era = _safe_float(stat.get("era"))

    k_percent = compute_rate_percent(strikeouts, batters_faced)
    bb_percent = compute_rate_percent(walks, batters_faced)
    k_minus_bb_percent = round(k_percent - bb_percent, 1) if (k_percent is not None and bb_percent is not None) else None

    fip_without_constant = None
    if innings_decimal > 0:
        fip_without_constant = round(
            (13 * home_runs_allowed + 3 * (walks + hit_by_pitch) - 2 * strikeouts) / innings_decimal, 2
        )

    return SeasonStatLine(
        player_id=player_id,
        season=season,
        outs=outs,
        innings_pitched=innings_decimal,
        batters_faced=batters_faced,
        strikeouts=strikeouts,
        walks=walks,
        earned_runs=earned_runs,
        hits_allowed=hits_allowed,
        home_runs_allowed=home_runs_allowed,
        hit_by_pitch=hit_by_pitch,
        era=era,
        k_percent=k_percent,
        bb_percent=bb_percent,
        k_minus_bb_percent=k_minus_bb_percent,
        fip_without_constant=fip_without_constant,
        retrieved_at=retrieved_at,
    )


def parse_recent_pitching_stats(
    raw_game_log: Optional[dict], player_id: str, season: str, retrieved_at: str, num_starts: int = 3
) -> Optional[RecentStatLine]:
    if not raw_game_log:
        return None
    stats_list = raw_game_log.get("stats") or []
    if not stats_list:
        return None
    splits = stats_list[0].get("splits") or []
    if not splits:
        return None

    # Game logs are chronological (oldest first); a pitcher can appear in
    # relief too, so prefer starts, but fall back to whatever's there
    # rather than discarding a rookie's very first appearances.
    start_splits = [s for s in splits if _safe_int((s.get("stat") or {}).get("gamesStarted")) >= 1]
    usable_splits = start_splits if start_splits else splits
    recent_splits = usable_splits[-num_starts:]
    if not recent_splits:
        return None

    total_outs = 0
    batters_faced = 0
    strikeouts = 0
    walks = 0
    pitch_total = 0
    pitch_samples = 0

    for split in recent_splits:
        stat = split.get("stat") or {}
        outs = _outs_from_stat(stat)
        if outs is not None:
            total_outs += outs
        batters_faced += _safe_int(stat.get("battersFaced"))
        strikeouts += _safe_int(stat.get("strikeOuts"))
        walks += _safe_int(stat.get("baseOnBalls"))
        pitches = stat.get("numberOfPitches")
        if pitches is not None:
            pitch_total += _safe_int(pitches)
            pitch_samples += 1

    innings_decimal = round(innings.outs_to_decimal_innings(total_outs), 3)
    k_percent = compute_rate_percent(strikeouts, batters_faced)
    bb_percent = compute_rate_percent(walks, batters_faced)
    pitch_count_average = round(pitch_total / pitch_samples, 1) if pitch_samples else None
    start_dates = [split.get("date") for split in recent_splits if split.get("date")]

    starts_used = len(recent_splits)
    return RecentStatLine(
        player_id=player_id,
        season=season,
        starts_used=starts_used,
        outs=total_outs,
        innings_pitched=innings_decimal,
        start_dates=start_dates,
        batters_faced=batters_faced,
        strikeouts=strikeouts,
        walks=walks,
        k_percent=k_percent,
        bb_percent=bb_percent,
        pitch_count_average=pitch_count_average,
        retrieved_at=retrieved_at,
        stat_scope=f"last_{starts_used}_starts",
    )


def parse_team_k_rate(raw: Optional[dict], team_id: str, season: str, retrieved_at: str) -> Optional[OpponentKRateLine]:
    stat = _first_split_stat(raw)
    if not stat:
        return None

    strikeouts = _safe_int(stat.get("strikeOuts"))
    plate_appearances = stat.get("plateAppearances")
    if not plate_appearances:
        return None

    k_percent = compute_rate_percent(strikeouts, _safe_int(plate_appearances))
    if k_percent is None:
        return None

    return OpponentKRateLine(
        team_id=team_id,
        season=season,
        k_percent=k_percent,
        split_type="overall",
        retrieved_at=retrieved_at,
    )


# ----------------------------------------------------------------------------
# Merge into PitcherInput
# ----------------------------------------------------------------------------


def apply_stats_to_pitcher_inputs(
    pitcher_inputs: List[PitcherInput],
    raw_stats: RawPitcherStats,
    player_to_opponent_team_id: Dict[str, str],
    retrieved_at: str,
) -> Tuple[List[PitcherInput], List[dict]]:
    """Enrich each PitcherInput's season/recent/opponent_stats with real
    numbers parsed from `raw_stats`. Missing data stays None -- nothing
    here invents a value for a pitcher/team we couldn't fetch.

    Returns (enriched_pitcher_inputs, provenance_records) where
    provenance_records is a flat list of plain dicts (one per stat line
    successfully parsed) suitable for saving alongside the research
    package.
    """
    enriched: List[PitcherInput] = []
    provenance: List[dict] = []

    for p in pitcher_inputs:
        season_line = parse_season_pitching_stats(
            raw_stats.season_pitching.get(p.player_id), p.player_id, raw_stats.season, retrieved_at
        )
        recent_line = parse_recent_pitching_stats(
            raw_stats.game_log_pitching.get(p.player_id), p.player_id, raw_stats.season, retrieved_at
        )

        opponent_team_id = player_to_opponent_team_id.get(p.player_id)
        opponent_line = None
        if opponent_team_id is not None:
            opponent_line = parse_team_k_rate(
                raw_stats.team_hitting.get(opponent_team_id), opponent_team_id, raw_stats.season, retrieved_at
            )

        new_season = p.season
        if season_line:
            new_season = replace(
                p.season,
                innings=season_line.innings_pitched,
                era=season_line.era,
                k_percent=season_line.k_percent,
                bb_percent=season_line.bb_percent,
                k_minus_bb_percent=season_line.k_minus_bb_percent,
                batters_faced=season_line.batters_faced,
                strikeouts=season_line.strikeouts,
                walks=season_line.walks,
                earned_runs=season_line.earned_runs,
                hits_allowed=season_line.hits_allowed,
                home_runs_allowed=season_line.home_runs_allowed,
                hit_by_pitch=season_line.hit_by_pitch,
            )
            provenance.append({"type": "season_pitching", **season_line.__dict__})

        new_recent = p.recent
        if recent_line:
            new_recent = replace(
                p.recent,
                innings=recent_line.innings_pitched,
                k_percent=recent_line.k_percent,
                bb_percent=recent_line.bb_percent,
                pitch_count_average=recent_line.pitch_count_average,
                batters_faced=recent_line.batters_faced,
                strikeouts=recent_line.strikeouts,
                walks=recent_line.walks,
            )
            provenance.append({"type": "recent_pitching", **recent_line.__dict__})

        new_opponent_stats = p.opponent_stats
        if opponent_line:
            new_opponent_stats = replace(
                p.opponent_stats,
                team=p.opponent,
                strikeout_percent=opponent_line.k_percent,
                strikeout_percent_split_type=opponent_line.split_type,
            )
            provenance.append({"type": "opponent_team_k_rate", **opponent_line.__dict__})

        enriched.append(replace(p, season=new_season, recent=new_recent, opponent_stats=new_opponent_stats))

    return enriched, provenance
