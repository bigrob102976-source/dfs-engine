"""Milestone 32.1 -- coverage/quality/build reports (Parts 27, 28, 31)
and the feature manifest writer (Part 23)."""

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List

from historical_mlb.manifest import full_manifest, pregame_safe_column_names
from historical_mlb.paths import (
    BUILD_REPORT_PATH, COVERAGE_REPORT_PATH, FEATURE_MANIFEST_PATH, QUALITY_REPORT_PATH,
    WAREHOUSE_VERSION,
)


def _non_null_rate(rows: List[dict], field: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for r in rows if r.get(field) is not None) / len(rows), 4)


def _coverage_block(rows: List[dict], entity: str) -> Dict:
    if not rows:
        return {"rows": 0}
    block = {
        "rows": len(rows),
        "actual_dk_points_coverage": _non_null_rate(rows, "actual_dk_points"),
        "bat_hand_or_throw_hand_coverage": round(sum(1 for r in rows if r.get("bat_hand") or r.get("throw_hand")) / len(rows), 4),
        "rolling_season_games_gt_0": round(sum(1 for r in rows if (r.get("rolling_games_season") or r.get("rolling_starts_season") or 0) > 0) / len(rows), 4),
        "statcast_season_coverage": round(sum(1 for r in rows if (r.get("statcast_batted_balls_season") or r.get("statcast_batted_balls_allowed_season") or 0) > 0) / len(rows), 4),
        "weather_available_rate": _non_null_rate(rows, "weather_temperature_f"),
    }
    if entity == "hitter":
        block["opposing_starter_coverage"] = _non_null_rate(rows, "opposing_starting_pitcher_id")
        block["batting_order_coverage"] = _non_null_rate(rows, "batting_order_actual")
    else:
        block["pitch_count_coverage"] = _non_null_rate(rows, "actual_pitch_count")
        block["opponent_offense_coverage"] = round(sum(1 for r in rows if (r.get("opponent_sample_games") or 0) > 0) / len(rows), 4)
    return block


def build_coverage_report(hitter_rows: List[dict], pitcher_rows: List[dict]) -> dict:
    report = {}
    for season in ("2024", "2025"):
        h = [r for r in hitter_rows if r["game_date"].startswith(season)]
        p = [r for r in pitcher_rows if r["game_date"].startswith(season)]
        report[f"{season}_hitters"] = _coverage_block(h, "hitter")
        report[f"{season}_pitchers"] = _coverage_block(p, "pitcher")
    report["overall_hitters"] = _coverage_block(hitter_rows, "hitter")
    report["overall_pitchers"] = _coverage_block(pitcher_rows, "pitcher")

    pre_lineup_hitter_cols = set(pregame_safe_column_names("hitter", include_after_lineups=False))
    post_lineup_hitter_cols = set(pregame_safe_column_names("hitter", include_after_lineups=True))
    report["pre_lineup_usable_hitter_rows"] = sum(1 for r in hitter_rows if all(r.get(c) is not None for c in ("rolling_games_season",) if c in pre_lineup_hitter_cols))
    report["post_lineup_usable_hitter_rows"] = sum(1 for r in hitter_rows if r.get("batting_order_actual") is not None)
    report["pre_lineup_usable_pitcher_rows"] = sum(1 for r in pitcher_rows if r.get("starter_flag") is True or r.get("rolling_starts_season", 0) is not None)
    report["post_lineup_usable_pitcher_rows"] = sum(1 for r in pitcher_rows if r.get("starter_flag") is True)
    return report


def write_feature_manifest() -> dict:
    fields = full_manifest()
    manifest_doc = {
        "warehouse_version": WAREHOUSE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "field_count": len(fields),
        "fields": [asdict(f) for f in fields],
    }
    FEATURE_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEATURE_MANIFEST_PATH.write_text(json.dumps(manifest_doc, indent=2), encoding="utf-8")
    return manifest_doc


def write_quality_report(findings: List[dict]) -> dict:
    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_findings": len(findings),
        "errors": [f for f in findings if f["severity"] == "error"],
        "warnings": [f for f in findings if f["severity"] == "warning"],
    }
    QUALITY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUALITY_REPORT_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def write_coverage_report(hitter_rows: List[dict], pitcher_rows: List[dict]) -> dict:
    doc = build_coverage_report(hitter_rows, pitcher_rows)
    COVERAGE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE_REPORT_PATH.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def write_build_report(build_result: dict) -> dict:
    doc = {
        "warehouse_version": WAREHOUSE_VERSION,
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        **build_result,
    }
    BUILD_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUILD_REPORT_PATH.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    return doc
