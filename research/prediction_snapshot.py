"""Pregame prediction snapshots: the immutable historical record of
exactly what an agent said, before any game results exist.

This module is part of the PREGAME path. It must never import anything
from evaluation/ (which only exists to read POSTGAME results) -- see
tests/test_architecture_separation.py, which enforces this at import
level so the lookahead-bias boundary can't quietly erode.

Each call to `save_snapshot` writes a NEW timestamped file. Nothing here
ever opens an existing snapshot file in write mode -- once written, a
snapshot is never touched again. Historical snapshots already on disk
are never rewritten by code changes here (see the timezone-metadata note
below) -- only new snapshots gain new fields.
"""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config.scoring_config import PITCHER_MODEL_VERSION
from models.batter import BatterBoardEntry, BatterInput
from models.pitcher import PitcherBoardEntry, PitcherInput
from research import engine as research_engine
from research.quality_report import (
    BatterQualityReport,
    QualityReport,
    batter_data_status,
    pitcher_data_status,
)
from research.storage import save_json

DEFAULT_PREDICTIONS_ROOT = Path(__file__).resolve().parent.parent / "predictions"

# Milestone 7 timezone fix: prediction metadata must be unambiguous about
# WHEN it was generated. `tzdata` (pip) is required on Windows, which has
# no built-in IANA time zone database for zoneinfo to read.
LOCAL_TIMEZONE_NAME = "America/Chicago"


def _timezone_metadata(generated_at_iso: str) -> dict:
    """Given a UTC ISO-8601 timestamp, return the three explicit fields
    every NEW snapshot (pitcher or batter) carries: generated_at_utc,
    generated_at_local, timezone."""
    from zoneinfo import ZoneInfo  # imported lazily so a missing tzdata install fails loudly only when actually needed

    dt_utc = datetime.fromisoformat(generated_at_iso)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_local = dt_utc.astimezone(ZoneInfo(LOCAL_TIMEZONE_NAME))
    return {
        "generated_at_utc": dt_utc.isoformat(),
        "generated_at_local": dt_local.isoformat(),
        "timezone": LOCAL_TIMEZONE_NAME,
    }


# ----------------------------------------------------------------------------
# Pitcher snapshots
# ----------------------------------------------------------------------------


def _pitcher_snapshot_record(entry: PitcherBoardEntry, p: PitcherInput) -> dict:
    return {
        "player_id": entry.player_id,
        "name": entry.name,
        "team": entry.team,
        "opponent": entry.opponent,
        "game_id": p.game_id,
        "venue": p.venue_name,

        "projection": entry.projection,
        "ceiling": entry.ceiling,
        "floor": entry.floor,

        "overall_score": entry.overall_score,
        "strikeout_score": entry.strikeout_score,
        "run_prevention_score": entry.run_prevention_score,
        "matchup_score": entry.matchup_score,
        "workload_score": entry.workload_score,
        "contact_score": entry.contact_score,
        "environment_score": entry.environment_score,
        "value_score": entry.value_score,

        "risk_score": entry.risk_score,
        "confidence": entry.confidence,

        "tags": list(entry.tags),
        "reasons": list(entry.reasons),

        "season_metrics": asdict(p.season),
        "recent_metrics": asdict(p.recent),
        "trend_metrics": asdict(p.trends),
        "opponent_metrics": asdict(p.opponent_stats),
        # Milestone 23: previously omitted here (nothing before this milestone
        # needed a full PitcherInput reconstructed FROM a saved snapshot --
        # projection_engine/scoring.py reads the metrics dicts above directly
        # rather than rebuilding a PitcherInput). native_projections/ does
        # need a full reconstruction, so these are now saved too -- purely
        # additive, changes nothing for any existing snapshot reader.
        "availability_metrics": asdict(p.availability),
        "game_metrics": asdict(p.game),

        "data_status": pitcher_data_status(p),
    }


def build_snapshot(
    slate_date: str,
    board: List[PitcherBoardEntry],
    pitchers_by_id: Dict[str, PitcherInput],
    quality_report: QualityReport,
    source_metadata: Dict[str, List[str]],
    generated_at: Optional[str] = None,
) -> dict:
    """Assemble the full PITCHER snapshot document. `board` order is
    preserved as-is (already the Pitcher Agent's ranked order) -- every
    pitcher on the slate is included, not just the top N."""
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    return {
        "slate_date": slate_date,
        "generated_at": generated_at,
        **_timezone_metadata(generated_at),
        "model_version": PITCHER_MODEL_VERSION,
        "research_package_version": research_engine.VERSION,
        "source_metadata": source_metadata,
        "pitcher_count": len(board),
        "pitchers": [_pitcher_snapshot_record(entry, pitchers_by_id[entry.player_id]) for entry in board],
        "research_quality_report": quality_report.to_dict(),
    }


# ----------------------------------------------------------------------------
# Batter snapshots (Milestone 7)
# ----------------------------------------------------------------------------


def _batter_snapshot_record(entry: BatterBoardEntry, b: BatterInput) -> dict:
    return {
        "player_id": entry.player_id,
        "name": entry.name,
        "team": entry.team,
        "opponent": entry.opponent,
        "game_id": b.game_id,
        "venue": b.venue_name,
        "batting_order": entry.batting_order,
        "position": b.position,
        "batting_hand": b.batting_hand,

        "projection": entry.projection,
        "ceiling": entry.ceiling,
        "floor": entry.floor,

        "overall_score": entry.overall_score,
        "hitting_skill_score": entry.hitting_skill_score,
        "power_score": entry.power_score,
        "contact_score": entry.contact_score,
        "matchup_score": entry.matchup_score,
        "recent_trend_score": entry.recent_trend_score,
        "lineup_position_score": entry.lineup_position_score,
        "environment_score": entry.environment_score,
        "value_score": entry.value_score,

        "risk_score": entry.risk_score,
        "confidence": entry.confidence,

        "tags": list(entry.tags),
        "reasons": list(entry.reasons),

        "season_metrics": asdict(b.season),
        "recent_metrics": asdict(b.recent),
        "vs_rhp": asdict(b.vs_rhp),
        "vs_lhp": asdict(b.vs_lhp),
        "opposing_pitcher": asdict(b.opposing_pitcher),
        "trend_metrics": asdict(b.trends),

        "data_status": batter_data_status(b),
    }


def build_batter_snapshot(
    slate_date: str,
    board: List[BatterBoardEntry],
    batters_by_id: Dict[str, BatterInput],
    quality_report: BatterQualityReport,
    source_metadata: Dict[str, List[str]],
    missing_lineup_game_ids: Optional[List[str]] = None,
    generated_at: Optional[str] = None,
) -> dict:
    """Assemble the full BATTER snapshot document. Every hitter on the
    slate is included, not just the Top 20 displayed on-screen."""
    from config.batter_scoring_config import BATTER_MODEL_VERSION

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    return {
        "slate_date": slate_date,
        "generated_at": generated_at,
        **_timezone_metadata(generated_at),
        "model_version": BATTER_MODEL_VERSION,
        "research_package_version": research_engine.VERSION,
        "source_metadata": source_metadata,
        "hitter_count": len(board),
        "missing_lineup_game_ids": missing_lineup_game_ids or [],
        "hitters": [_batter_snapshot_record(entry, batters_by_id[entry.player_id]) for entry in board],
        "research_quality_report": quality_report.to_dict(),
    }


# ----------------------------------------------------------------------------
# Shared save/load infrastructure -- filename_prefix defaults preserve the
# exact pre-Milestone-7 pitcher behavior; batter callers pass "batter_board".
# ----------------------------------------------------------------------------


def timestamp_tag(generated_at: str) -> str:
    """'2026-08-11T16:55:00.123456+00:00' -> '20260811T165500' -- compact,
    filesystem-safe, second-resolution (matches the milestone's own example)."""
    dt = datetime.fromisoformat(generated_at)
    return dt.strftime("%Y%m%dT%H%M%S")


def save_snapshot(snapshot: dict, output_root: Path = DEFAULT_PREDICTIONS_ROOT, filename_prefix: str = "pitcher_board") -> Path:
    """Write `snapshot` to predictions/<date>/<filename_prefix>_<timestamp>.json.

    Always creates a new file -- never overwrites an existing snapshot.
    Running the agent again later the same day (or the same minute, for
    testing) produces an additional, separate snapshot rather than
    clobbering the last one, since price/lineup/weather information can
    change throughout the day and every version of that story matters.
    """
    slate_date = snapshot["slate_date"]
    timestamp = timestamp_tag(snapshot["generated_at"])
    path = Path(output_root) / slate_date / f"{filename_prefix}_{timestamp}.json"

    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing immutable snapshot: {path}. "
            f"(Two snapshots requested the same second -- this should be astronomically rare.)"
        )

    save_json(path, snapshot)
    return path


def list_snapshots(slate_date: str, output_root: Path = DEFAULT_PREDICTIONS_ROOT, filename_prefix: str = "pitcher_board") -> List[Path]:
    """All snapshot files for a date, oldest first (filenames sort
    chronologically since the timestamp is zero-padded and left-to-right
    significant)."""
    folder = Path(output_root) / slate_date
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{filename_prefix}_*.json"))


def load_latest_snapshot(slate_date: str, output_root: Path = DEFAULT_PREDICTIONS_ROOT, filename_prefix: str = "pitcher_board") -> dict:
    """The most recent snapshot for a date -- what evaluate_pitcher_slate.py
    uses by default when --snapshot isn't given explicitly."""
    snapshots = list_snapshots(slate_date, output_root, filename_prefix)
    if not snapshots:
        raise FileNotFoundError(f"No '{filename_prefix}' prediction snapshots found for {slate_date} under {output_root}/")
    return load_snapshot(snapshots[-1])


def load_snapshot(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)
