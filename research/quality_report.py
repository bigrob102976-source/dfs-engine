"""Research Quality Report: a per-slate count of how many probable
pitchers actually have each metric populated.

This exists purely to make gaps visible -- CLAUDE.md's "fail loudly when
critical data is missing" applied to a whole slate at once, instead of
having to open 30 individual pitcher records to notice a source didn't
return anything. It performs no scoring and makes no judgment about
whether a gap matters; it just counts.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

from models.batter import BatterInput
from models.pitcher import PitcherInput

# (label, predicate) -- predicate receives one PitcherInput and returns
# whether that category is populated for it. Order here is the print
# order. Add a new metric by adding one line; nothing else to touch.
_CATEGORIES = [
    ("Season Stats", lambda p: p.season.k_percent is not None),
    ("Recent Stats", lambda p: p.recent.k_percent is not None),
    ("Velocity", lambda p: p.recent.season_velocity is not None),
    ("CSW", lambda p: p.recent.csw_percent is not None),
    ("Swinging Strike %", lambda p: p.season.swinging_strike_percent is not None),
    ("Ground Ball %", lambda p: p.season.ground_ball_percent is not None),
    ("Hard Hit %", lambda p: p.season.hard_hit_percent is not None),
    ("Barrel %", lambda p: p.season.barrel_percent is not None),
    ("xERA", lambda p: p.season.xera is not None),
    ("xwOBA", lambda p: p.season.xwoba_allowed is not None),
    ("Opponent K Rate", lambda p: p.opponent_stats.strikeout_percent_vs_hand is not None or p.opponent_stats.strikeout_percent is not None),
    ("Weather", lambda p: p.game.weather_pitching_factor is not None),
    ("Vegas", lambda p: p.opponent_stats.implied_runs is not None),
    ("Salary", lambda p: p.salary is not None),
]


@dataclass
class QualityReport:
    total_pitchers: int
    rows: List[Tuple[str, int]]  # (label, count_populated), in a fixed, meaningful order

    def to_dict(self) -> dict:
        return {"total_pitchers": self.total_pitchers, "counts": {label: count for label, count in self.rows}}


def build_quality_report(pitcher_inputs: List[PitcherInput]) -> QualityReport:
    total = len(pitcher_inputs)
    rows = [(label, sum(1 for p in pitcher_inputs if predicate(p))) for label, predicate in _CATEGORIES]
    return QualityReport(total_pitchers=total, rows=rows)


def pitcher_data_status(p: PitcherInput) -> Dict[str, bool]:
    """Per-pitcher version of the same categories used above -- the
    "data completeness/status" a prediction snapshot preserves for each
    pitcher individually, built from the exact same predicates so the
    per-pitcher and slate-level views can never silently drift apart."""
    return {label: predicate(p) for label, predicate in _CATEGORIES}


def render_quality_report(report: QualityReport) -> str:
    lines = ["RESEARCH QUALITY REPORT", "", f"Pitchers  {report.total_pitchers} / {report.total_pitchers}"]
    for label, count in report.rows:
        lines.append(f"{label}  {count} / {report.total_pitchers}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# Batters (Milestone 7) -- a separate, parallel dataclass rather than
# reworking QualityReport above: QualityReport.to_dict()'s "total_pitchers"
# key is already baked into existing immutable pitcher snapshots on disk,
# so its shape must never change.
# ----------------------------------------------------------------------------

_BATTER_CATEGORIES = [
    ("Season Batting Stats", lambda b: b.season.k_percent is not None),
    ("xwOBA", lambda b: b.season.xwoba is not None),
    ("xSLG", lambda b: b.season.xslg is not None),
    ("Hard Hit", lambda b: b.season.hard_hit_percent is not None),
    ("Barrel", lambda b: b.season.barrel_percent is not None),
    ("Recent Data", lambda b: b.recent.plate_appearances is not None),
    ("Platoon Splits", lambda b: b.vs_rhp.woba is not None or b.vs_lhp.woba is not None),
    ("Batting Order", lambda b: b.batting_order is not None),
    ("Opposing Pitcher Context", lambda b: b.opposing_pitcher.player_id is not None),
    ("Salary", lambda b: b.salary is not None),
    # Not built yet this milestone -- always 0, per instruction to make
    # the gap obvious rather than omitting the row.
    ("Weather", lambda b: False),
    ("Vegas", lambda b: False),
]


@dataclass
class BatterQualityReport:
    total_hitters: int
    rows: List[Tuple[str, int]]

    def to_dict(self) -> dict:
        return {"total_hitters": self.total_hitters, "counts": {label: count for label, count in self.rows}}


def build_batter_quality_report(batter_inputs: List[BatterInput]) -> BatterQualityReport:
    total = len(batter_inputs)
    rows = [(label, sum(1 for b in batter_inputs if predicate(b))) for label, predicate in _BATTER_CATEGORIES]
    return BatterQualityReport(total_hitters=total, rows=rows)


def batter_data_status(b: BatterInput) -> Dict[str, bool]:
    """Per-hitter version of the same categories -- what a batter
    prediction snapshot preserves for each hitter individually."""
    return {label: predicate(b) for label, predicate in _BATTER_CATEGORIES}


def render_batter_quality_report(report: BatterQualityReport) -> str:
    lines = ["RESEARCH QUALITY REPORT (Hitters)", "", f"Starting Hitters  {report.total_hitters} / {report.total_hitters}"]
    for label, count in report.rows:
        lines.append(f"{label}  {count} / {report.total_hitters}")
    return "\n".join(lines)
