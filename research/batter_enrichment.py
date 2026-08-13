"""Enrichment stage for real MLB Stats hitting data (season, last-14-days
recent form, and vs-RHP/vs-LHP platoon splits).

Pure data transformation on top of what research.collector already
fetched -- no network calls here. Mirrors research/enrichment.py's role
for pitchers exactly.

Formulas (batters-faced-equivalent denominator = plate appearances, same
philosophy as research/enrichment.py's pitcher K%/BB%):

    K%  = strikeouts / plate_appearances
    BB% = walks / plate_appearances
    ISO = SLG - AVG

Season wOBA is NOT computed here -- research.statcast_batter_enrichment
pulls Baseball Savant's own real wOBA (their internal linear weights,
season-specific), which is more trustworthy than a hand-rolled
approximation. Platoon-split wOBA has no such authoritative per-split
source, so it IS approximated here from the split's own real counting
stats using a fixed, published, historical-average linear-weight set
(see `_WOBA_WEIGHTS`) -- documented clearly as an approximation, not
presented as Savant's real number.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from models.batter import BatterInput
from research.collector import RawBatterStats

# Fixed, widely-published historical-average wOBA linear weights (roughly
# 2013-2023 FanGraphs constants). NOT season-specific -- Baseball Savant's
# season-level `woba`/`est_woba` (used in research/statcast_batter_enrichment.py)
# is preferred wherever available; this is only a fallback for platoon
# splits, which have no direct wOBA field from any source we use.
_WOBA_WEIGHTS = {"bb": 0.69, "hbp": 0.72, "single": 0.89, "double": 1.27, "triple": 1.62, "home_run": 2.10}


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value) -> Optional[int]:
    f = _safe_float(value)
    return int(f) if f is not None else None


def compute_rate_percent(numerator: int, denominator: Optional[int]) -> Optional[float]:
    if not denominator:
        return None
    return round((numerator / denominator) * 100.0, 1)


def _first_split_stat(raw: Optional[dict]) -> Optional[dict]:
    if not raw:
        return None
    stats_list = raw.get("stats") or []
    if not stats_list:
        return None
    splits = stats_list[0].get("splits") or []
    if not splits:
        return None
    return splits[0].get("stat")


def _approximate_woba(stat: dict) -> Optional[float]:
    ab = _safe_int(stat.get("atBats"))
    if not ab:
        return None
    bb = _safe_int(stat.get("baseOnBalls")) or 0
    ibb = _safe_int(stat.get("intentionalWalks")) or 0
    hbp = _safe_int(stat.get("hitByPitch")) or 0
    sf = _safe_int(stat.get("sacFlies")) or 0
    hits = _safe_int(stat.get("hits")) or 0
    doubles = _safe_int(stat.get("doubles")) or 0
    triples = _safe_int(stat.get("triples")) or 0
    hr = _safe_int(stat.get("homeRuns")) or 0
    singles = max(hits - doubles - triples - hr, 0)

    denominator = ab + bb - ibb + sf + hbp
    if denominator <= 0:
        return None
    numerator = (
        _WOBA_WEIGHTS["bb"] * (bb - ibb) + _WOBA_WEIGHTS["hbp"] * hbp
        + _WOBA_WEIGHTS["single"] * singles + _WOBA_WEIGHTS["double"] * doubles
        + _WOBA_WEIGHTS["triple"] * triples + _WOBA_WEIGHTS["home_run"] * hr
    )
    return round(numerator / denominator, 3)


# ----------------------------------------------------------------------------
# Typed, provenance-tagged lines
# ----------------------------------------------------------------------------


@dataclass
class SeasonBattingLine:
    player_id: str
    season: str
    plate_appearances: Optional[int] = None
    at_bats: Optional[int] = None
    hits: Optional[int] = None
    doubles: Optional[int] = None
    triples: Optional[int] = None
    home_runs: Optional[int] = None
    walks: Optional[int] = None
    strikeouts: Optional[int] = None
    stolen_bases: Optional[int] = None
    avg: Optional[float] = None
    obp: Optional[float] = None
    slg: Optional[float] = None
    ops: Optional[float] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    iso: Optional[float] = None
    retrieved_at: str = ""
    source: str = "mlb_stats_api"
    stat_scope: str = "season"


@dataclass
class RecentBattingLine:
    player_id: str
    season: str
    plate_appearances: int = 0
    strikeouts: int = 0
    walks: int = 0
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    games_sampled: int = 0
    days_sampled: int = 14
    retrieved_at: str = ""
    source: str = "mlb_stats_api"
    stat_scope: str = "last_14_days"


@dataclass
class PlatoonLine:
    player_id: str
    season: str
    sit_code: str  # "vr" or "vl"
    plate_appearances: Optional[int] = None
    k_percent: Optional[float] = None
    bb_percent: Optional[float] = None
    iso: Optional[float] = None
    woba: Optional[float] = None  # approximated -- see module docstring
    ops: Optional[float] = None
    retrieved_at: str = ""
    source: str = "mlb_stats_api"
    stat_scope: str = "season_split"


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------


def parse_season_batting_stats(raw: Optional[dict], player_id: str, season: str, retrieved_at: str) -> Optional[SeasonBattingLine]:
    stat = _first_split_stat(raw)
    if not stat:
        return None

    pa = _safe_int(stat.get("plateAppearances"))
    k = _safe_int(stat.get("strikeOuts")) or 0
    bb = _safe_int(stat.get("baseOnBalls")) or 0
    avg = _safe_float(stat.get("avg"))
    slg = _safe_float(stat.get("slg"))

    return SeasonBattingLine(
        player_id=player_id,
        season=season,
        plate_appearances=pa,
        at_bats=_safe_int(stat.get("atBats")),
        hits=_safe_int(stat.get("hits")),
        doubles=_safe_int(stat.get("doubles")),
        triples=_safe_int(stat.get("triples")),
        home_runs=_safe_int(stat.get("homeRuns")),
        walks=bb,
        strikeouts=k,
        stolen_bases=_safe_int(stat.get("stolenBases")),
        avg=avg,
        obp=_safe_float(stat.get("obp")),
        slg=slg,
        ops=_safe_float(stat.get("ops")),
        k_percent=compute_rate_percent(k, pa),
        bb_percent=compute_rate_percent(bb, pa),
        iso=round(slg - avg, 3) if (slg is not None and avg is not None) else None,
        retrieved_at=retrieved_at,
    )


def parse_recent_batting_stats(
    raw_game_log: Optional[dict], player_id: str, season: str, retrieved_at: str,
    reference_date: str, window_days: int = 14,
) -> Optional[RecentBattingLine]:
    if not raw_game_log:
        return None
    stats_list = raw_game_log.get("stats") or []
    if not stats_list:
        return None
    splits = stats_list[0].get("splits") or []
    if not splits:
        return None

    ref = datetime.strptime(reference_date, "%Y-%m-%d")
    window_start = ref - timedelta(days=window_days)

    recent_splits = []
    for split in splits:
        date_str = split.get("date")
        if not date_str:
            continue
        try:
            game_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        if window_start <= game_date < ref:
            recent_splits.append(split)

    if not recent_splits:
        return None

    pa = k = bb = 0
    for split in recent_splits:
        stat = split.get("stat") or {}
        pa += _safe_int(stat.get("plateAppearances")) or 0
        k += _safe_int(stat.get("strikeOuts")) or 0
        bb += _safe_int(stat.get("baseOnBalls")) or 0

    return RecentBattingLine(
        player_id=player_id,
        season=season,
        plate_appearances=pa,
        strikeouts=k,
        walks=bb,
        k_percent=compute_rate_percent(k, pa),
        bb_percent=compute_rate_percent(bb, pa),
        games_sampled=len(recent_splits),
        days_sampled=window_days,
        retrieved_at=retrieved_at,
    )


def parse_platoon_split(raw: Optional[dict], player_id: str, season: str, sit_code: str, retrieved_at: str) -> Optional[PlatoonLine]:
    stat = _first_split_stat(raw)
    if not stat:
        return None

    pa = _safe_int(stat.get("plateAppearances"))
    k = _safe_int(stat.get("strikeOuts")) or 0
    bb = _safe_int(stat.get("baseOnBalls")) or 0
    avg = _safe_float(stat.get("avg"))
    slg = _safe_float(stat.get("slg"))

    return PlatoonLine(
        player_id=player_id,
        season=season,
        sit_code=sit_code,
        plate_appearances=pa,
        k_percent=compute_rate_percent(k, pa),
        bb_percent=compute_rate_percent(bb, pa),
        iso=round(slg - avg, 3) if (slg is not None and avg is not None) else None,
        woba=_approximate_woba(stat),
        ops=_safe_float(stat.get("ops")),
        retrieved_at=retrieved_at,
    )


# ----------------------------------------------------------------------------
# Merge into BatterInput
# ----------------------------------------------------------------------------


def apply_stats_to_batter_inputs(
    batter_inputs: List[BatterInput],
    raw_stats: RawBatterStats,
    reference_date: str,
    retrieved_at: str,
) -> Tuple[List[BatterInput], List[dict]]:
    enriched: List[BatterInput] = []
    provenance: List[dict] = []

    for p in batter_inputs:
        season_line = parse_season_batting_stats(raw_stats.season_hitting.get(p.player_id), p.player_id, raw_stats.season, retrieved_at)
        recent_line = parse_recent_batting_stats(
            raw_stats.game_log_hitting.get(p.player_id), p.player_id, raw_stats.season, retrieved_at, reference_date
        )
        vs_rhp_line = parse_platoon_split(raw_stats.platoon_vs_rhp.get(p.player_id), p.player_id, raw_stats.season, "vr", retrieved_at)
        vs_lhp_line = parse_platoon_split(raw_stats.platoon_vs_lhp.get(p.player_id), p.player_id, raw_stats.season, "vl", retrieved_at)

        new_season = p.season
        if season_line:
            new_season = replace(
                p.season,
                plate_appearances=season_line.plate_appearances,
                at_bats=season_line.at_bats,
                hits=season_line.hits,
                doubles=season_line.doubles,
                triples=season_line.triples,
                home_runs=season_line.home_runs,
                walks=season_line.walks,
                strikeouts=season_line.strikeouts,
                stolen_bases=season_line.stolen_bases,
                avg=season_line.avg,
                obp=season_line.obp,
                slg=season_line.slg,
                ops=season_line.ops,
                k_percent=season_line.k_percent,
                bb_percent=season_line.bb_percent,
                iso=season_line.iso,
            )
            provenance.append({"type": "season_batting", **season_line.__dict__})

        new_recent = p.recent
        if recent_line:
            new_recent = replace(
                p.recent,
                plate_appearances=recent_line.plate_appearances,
                k_percent=recent_line.k_percent,
                bb_percent=recent_line.bb_percent,
            )
            provenance.append({"type": "recent_batting", **recent_line.__dict__})

        new_vs_rhp = p.vs_rhp
        if vs_rhp_line:
            new_vs_rhp = replace(
                p.vs_rhp,
                plate_appearances=vs_rhp_line.plate_appearances,
                k_percent=vs_rhp_line.k_percent,
                bb_percent=vs_rhp_line.bb_percent,
                iso=vs_rhp_line.iso,
                woba=vs_rhp_line.woba,
                ops=vs_rhp_line.ops,
                split_type="vs_hand",
            )
            provenance.append({"type": "platoon_vs_rhp", **vs_rhp_line.__dict__})

        new_vs_lhp = p.vs_lhp
        if vs_lhp_line:
            new_vs_lhp = replace(
                p.vs_lhp,
                plate_appearances=vs_lhp_line.plate_appearances,
                k_percent=vs_lhp_line.k_percent,
                bb_percent=vs_lhp_line.bb_percent,
                iso=vs_lhp_line.iso,
                woba=vs_lhp_line.woba,
                ops=vs_lhp_line.ops,
                split_type="vs_hand",
            )
            provenance.append({"type": "platoon_vs_lhp", **vs_lhp_line.__dict__})

        enriched.append(replace(p, season=new_season, recent=new_recent, vs_rhp=new_vs_rhp, vs_lhp=new_vs_lhp))

    return enriched, provenance


def apply_bios_to_batter_inputs(batter_inputs: List[BatterInput], people: Dict[str, dict]) -> List[BatterInput]:
    """Fill in `batting_hand` from research.collector.collect_batter_bios'
    output. Pure merge, no network -- mirrors how pitcher throwing_hand
    ends up on PitcherInput, just resolved one stage later since
    batters.json doesn't carry it the way pitchers.json carries `throws`."""
    enriched = []
    for p in batter_inputs:
        person = people.get(p.player_id)
        if person:
            bats = (person.get("batSide") or {}).get("code")
            if bats:
                p = replace(p, batting_hand=bats)
        enriched.append(p)
    return enriched
