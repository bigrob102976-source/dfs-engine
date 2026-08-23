"""Milestone 32.5 -- Big Money ML forward RESULTS + LINEUP GRADING.

Grades the M32.3B live shadow ML projections and the M32.4 optimizer
lineups against REAL, postgame MLB results -- never a CSV, never mock/
synthetic data. Reuses every existing postgame primitive rather than
duplicating them:

    evaluation.results_collector.collect_actual_results   (MLB Stats API)
    evaluation.results_enrichment / hitter_results_enrichment  (FINAL gating)
    evaluation.dk_actual_scoring                           (actual DK points)
    evaluation.projection_source_loader                    (per-source loaders)
    evaluation.projection_source_comparison                (pure metric math)
    evaluation.big_money_ml_evaluation                      (ceiling/zero/disaster monitors)

This module is POSTGAME evaluation tooling (same package as every other
evaluator here) -- it is allowed to import big_money_ml/optimizer's
read-only persistence loaders; the reverse direction remains forbidden
(see tests/test_architecture_separation.py). It NEVER imports
historical_models.*.train (no retraining), NEVER modifies a frozen
pregame ML snapshot, and NEVER modifies a saved lineup set.

A game's boxscore is only ever fetched/cached once it is confirmed
FINAL by a FRESH schedule call -- never for a still-in-progress game --
so the disk cache in evaluation.results_collector (research.cache) can
never lock in a stale, incomplete boxscore for a game that later
finishes (see this module's own test suite for the reasoning).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from evaluation.big_money_ml_evaluation import (
    build_all_combined_projection_sources,
    compute_ceiling_magnitude_monitor,
    compute_disaster_start_bucket,
    compute_zero_game_monitor,
    load_pregame_ml_hitter_projections,
    load_pregame_ml_pitcher_projections,
)
from evaluation.dk_actual_scoring import calculate_actual_dk_points, calculate_actual_hitter_dk_points
from evaluation.hitter_results_enrichment import STATUS_APPEARED, parse_all_hitter_results
from evaluation.projection_source_comparison import compare_projection_sources
from evaluation.projection_source_loader import (
    DEFAULT_RESULTS_ROOT,
    build_hitter_projection_sources,
    build_pitcher_projection_sources,
    load_actual_hitter_points,
    load_actual_pitcher_points,
)
from evaluation.results_collector import collect_actual_results
from evaluation.results_enrichment import STATUS_COMPLETED, STATUS_DID_NOT_START, parse_all_results
from research.collector import fetch_schedule
from research.storage import save_json

from big_money_ml.persistence import DEFAULT_ML_PROJECTION_ROOT, load_latest_ml_hitter_projection_snapshot, load_latest_ml_projection_snapshot

DEFAULT_DFS_INPUT_ROOT = Path(__file__).resolve().parent.parent / "dfs_input"
DEFAULT_LINEUPS_ROOT = Path(__file__).resolve().parent.parent / "lineups"

_PITCHER_SCOREABLE = {STATUS_COMPLETED, STATUS_DID_NOT_START}
_HITTER_SCOREABLE = {STATUS_APPEARED}


# ---------------------------------------------------------------------------
# Slate resolution + FINAL status gating
# ---------------------------------------------------------------------------


def load_slate_pool(slate_date: str, slate_id: str, dfs_input_root: Path = DEFAULT_DFS_INPUT_ROOT) -> Optional[dict]:
    """The LATEST dk_player_pool_<ts>.json for `slate_date` whose own
    selected_slate_id matches `slate_id` -- mirrors
    dashboard/lib/loaders.ts::loadLatestDKPlayerPool's slate-scoped
    lookup exactly (scans oldest-to-newest, returns the last match)."""
    folder = Path(dfs_input_root) / slate_date
    if not folder.exists():
        return None
    files = sorted(folder.glob("dk_player_pool_*.json"))
    for path in reversed(files):
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
        if doc.get("selected_slate_id") == slate_id:
            return doc
    return None


def slate_game_ids(pool_doc: dict) -> List[str]:
    game_ids = set()
    for p in pool_doc.get("players", []):
        if p.get("game_id"):
            game_ids.add(str(p["game_id"]))
    return sorted(game_ids)


def check_slate_final_status(slate_date: str, slate_id: str, dfs_input_root: Path = DEFAULT_DFS_INPUT_ROOT) -> dict:
    """Fresh (never cached) MLB status per game in this slate. A game
    only ever counts as `final` when its MLB detailedState literally
    starts with "Final" -- pregame/in-play/suspended/delayed all count
    as NOT final, exactly per this milestone's explicit gating rule."""
    pool_doc = load_slate_pool(slate_date, slate_id, dfs_input_root=dfs_input_root)
    if pool_doc is None:
        return {"slate_id": slate_id, "games_total": 0, "games_final": 0, "all_final": False, "games": []}

    game_ids = slate_game_ids(pool_doc)
    schedule = fetch_schedule(slate_date)
    status_by_game: Dict[str, str] = {}
    for date_block in schedule.get("dates", []):
        for g in date_block.get("games", []):
            gid = str(g.get("gamePk"))
            if gid in game_ids:
                status_by_game[gid] = (g.get("status") or {}).get("detailedState") or "Unknown"

    games = []
    final_count = 0
    for gid in game_ids:
        detailed_state = status_by_game.get(gid, "Unknown")
        is_final = detailed_state.startswith("Final")
        if is_final:
            final_count += 1
        games.append({"game_id": gid, "detailed_state": detailed_state, "final": is_final})

    return {
        "slate_id": slate_id,
        "games_total": len(game_ids),
        "games_final": final_count,
        "all_final": len(game_ids) > 0 and final_count == len(game_ids),
        "games": games,
    }


# ---------------------------------------------------------------------------
# Results collection -- writes the SAME results/<date>/{pitcher,hitter}_
# results.json shape scripts/collect_pitcher_results.py / collect_hitter_
# results.py already produce (never duplicating their record schema),
# but scoped to ONLY the game_ids already confirmed FINAL -- a boxscore
# is never fetched (and therefore never cached) for a non-final game.
# ---------------------------------------------------------------------------


def collect_and_score_final_games(
    slate_date: str, final_game_ids: List[str], expected_pitchers: List[dict], expected_hitters: List[dict],
    results_root: Path = DEFAULT_RESULTS_ROOT,
) -> dict:
    """`expected_pitchers`/`expected_hitters` -- {player_id, name, team,
    game_id} records (from the ML snapshots -- see build_expected_player_
    lists below). Only players whose game_id is in `final_game_ids` are
    ever scored; everyone else is skipped here (never marked "missing"
    -- they simply aren't part of this collection pass yet, and a later
    re-run once their game finishes will pick them up). Idempotent:
    calling this again with the same inputs overwrites results/<date>/
    *.json with the identical content (research.storage.save_json
    already allows overwrite -- this file was never immutable)."""
    final_set = set(final_game_ids)
    pitchers_to_grade = [p for p in expected_pitchers if str(p.get("game_id")) in final_set]
    hitters_to_grade = [h for h in expected_hitters if str(h.get("game_id")) in final_set]

    raw = collect_actual_results(slate_date, final_game_ids)
    retrieved_at = datetime.now(timezone.utc).isoformat()

    pitcher_records = []
    for result in parse_all_results(raw, pitchers_to_grade, retrieved_at):
        scoring = calculate_actual_dk_points(result)
        record = _dataclass_to_dict(result)
        record["dfs_points"] = scoring["dfs_points"]
        record["dfs_breakdown"] = scoring["breakdown"]
        pitcher_records.append(record)

    hitter_records = []
    for result in parse_all_hitter_results(raw, hitters_to_grade, retrieved_at):
        scoring = calculate_actual_hitter_dk_points(result)
        record = _dataclass_to_dict(result)
        record["dfs_points"] = scoring["dfs_points"]
        record["dfs_breakdown"] = scoring["breakdown"]
        hitter_records.append(record)

    pitcher_doc = {
        "slate_date": slate_date, "generated_at": retrieved_at, "source_metadata": {"mlb_stats_sources": raw.sources_used},
        "result_count": len(pitcher_records), "results": pitcher_records,
    }
    hitter_doc = {
        "slate_date": slate_date, "generated_at": retrieved_at, "source_metadata": {"mlb_stats_sources": raw.sources_used},
        "result_count": len(hitter_records), "results": hitter_records,
    }
    save_json(Path(results_root) / slate_date / "pitcher_results.json", pitcher_doc)
    save_json(Path(results_root) / slate_date / "hitter_results.json", hitter_doc)

    return {
        "pitchers_graded": sum(1 for r in pitcher_records if r["dfs_points"] is not None),
        "hitters_graded": sum(1 for r in hitter_records if r["dfs_points"] is not None),
        "warnings": raw.warnings, "errors": raw.errors,
    }


def _dataclass_to_dict(obj) -> dict:
    from dataclasses import asdict

    return asdict(obj)


def build_expected_player_lists(slate_date: str, ml_root: Path = DEFAULT_ML_PROJECTION_ROOT):
    """{player_id, name, team, game_id} for every ML-eligible pitcher/
    hitter (regardless of projection_status) -- the canonical identity
    source for this module's grading (richest metadata: team/opponent/
    game_id/batting_order already resolved by M32.3B)."""
    pitcher_doc = load_latest_ml_projection_snapshot(slate_date, output_root=ml_root)
    hitter_doc = load_latest_ml_hitter_projection_snapshot(slate_date, output_root=ml_root)
    pitchers = [{"player_id": p["player_id"], "name": p["name"], "team": p["team"], "game_id": p["game_id"]} for p in (pitcher_doc or {}).get("players", [])]
    hitters = [{"player_id": p["player_id"], "name": p["name"], "team": p["team"], "game_id": p["game_id"]} for p in (hitter_doc or {}).get("players", [])]
    return pitchers, hitters


# ---------------------------------------------------------------------------
# Player-level grading records (PLAYER RESULTS)
# ---------------------------------------------------------------------------


def _identity_map(slate_date: str, ml_root: Path = DEFAULT_ML_PROJECTION_ROOT) -> Dict[str, dict]:
    pitcher_doc = load_latest_ml_projection_snapshot(slate_date, output_root=ml_root)
    hitter_doc = load_latest_ml_hitter_projection_snapshot(slate_date, output_root=ml_root)
    out: Dict[str, dict] = {}
    for p in (pitcher_doc or {}).get("players", []):
        out[str(p["player_id"])] = {"name": p.get("name"), "team": p.get("team"), "opponent": p.get("opponent"), "game_id": p.get("game_id"), "player_type": "pitcher"}
    for p in (hitter_doc or {}).get("players", []):
        out[str(p["player_id"])] = {"name": p.get("name"), "team": p.get("team"), "opponent": p.get("opponent"), "game_id": p.get("game_id"), "player_type": "hitter"}
    return out


def build_player_grading_records(
    slate_date: str, player_type: str, sources_by_label: Dict[str, Dict[str, float]], actual_by_id: Dict[str, float],
    identity_by_id: Dict[str, dict],
) -> List[dict]:
    """One record per (source, player) pair where BOTH a pregame
    projection AND an actual DK result exist -- "for every player with
    a valid pregame projection persist Player/Team/Opponent/Game ID/
    Projection Source/Pregame Projection/Actual DK/Error/Absolute
    Error." Never invents identity for a player this module doesn't
    recognize (falls back to the bare player_id as the name)."""
    records: List[dict] = []
    for source, projections in sources_by_label.items():
        for player_id, projection in projections.items():
            if player_id not in actual_by_id:
                continue
            actual = actual_by_id[player_id]
            identity = identity_by_id.get(player_id, {})
            error = round(actual - projection, 3)
            records.append({
                "player_id": player_id,
                "name": identity.get("name", player_id),
                "team": identity.get("team"),
                "opponent": identity.get("opponent"),
                "game_id": identity.get("game_id"),
                "player_type": player_type,
                "projection_source": source,
                "pregame_projection": projection,
                "actual_dk": actual,
                "error": error,
                "absolute_error": abs(error),
            })
    return records


def build_all_player_grading_records(slate_date: str, ml_root: Path = DEFAULT_ML_PROJECTION_ROOT, results_root: Path = DEFAULT_RESULTS_ROOT, **source_roots) -> dict:
    identity = _identity_map(slate_date, ml_root=ml_root)

    pitcher_sources = build_pitcher_projection_sources(slate_date, **source_roots)
    ml_pitcher = load_pregame_ml_pitcher_projections(slate_date, ml_root=ml_root)
    if ml_pitcher:
        pitcher_sources["big_money_ml"] = ml_pitcher
    actual_pitchers = load_actual_pitcher_points(slate_date, results_root=results_root)
    pitcher_records = build_player_grading_records(slate_date, "pitcher", pitcher_sources, actual_pitchers, identity)

    hitter_sources = build_hitter_projection_sources(slate_date, **source_roots)
    ml_hitter = load_pregame_ml_hitter_projections(slate_date, ml_root=ml_root)
    if ml_hitter:
        hitter_sources["big_money_ml"] = ml_hitter
    actual_hitters = load_actual_hitter_points(slate_date, results_root=results_root)
    hitter_records = build_player_grading_records(slate_date, "hitter", hitter_sources, actual_hitters, identity)

    return {"pitchers": pitcher_records, "hitters": hitter_records, "combined": pitcher_records + hitter_records}


# ---------------------------------------------------------------------------
# Combined (hitter + pitcher pooled) forward performance -- correctly
# recomputed from POOLED raw (predicted, actual) pairs, never derived by
# algebraically averaging separately-computed hitter/pitcher metrics
# (valid for MAE/RMSE with proper N-weighting, but NOT valid for
# Pearson/Spearman/top-N, which must be computed on the pooled sample).
# ---------------------------------------------------------------------------


def load_actual_combined_points(slate_date: str, results_root: Path = DEFAULT_RESULTS_ROOT) -> Dict[str, float]:
    merged = dict(load_actual_pitcher_points(slate_date, results_root=results_root))
    merged.update(load_actual_hitter_points(slate_date, results_root=results_root))
    return merged


def evaluate_forward_combined_performance(slate_dates: List[str], results_root: Path = DEFAULT_RESULTS_ROOT, ml_root: Path = DEFAULT_ML_PROJECTION_ROOT) -> dict:
    from evaluation.big_money_ml_evaluation import _simple_mean, _weighted_mean
    from evaluation.projection_source_comparison import ProjectionSourceMetrics

    per_source_metrics: Dict[str, List[ProjectionSourceMetrics]] = {}
    dates_evaluated = 0

    for date in slate_dates:
        actual = load_actual_combined_points(date, results_root=results_root)
        if not actual:
            continue
        dates_evaluated += 1
        sources = build_all_combined_projection_sources(date, ml_root=ml_root)
        for metrics in compare_projection_sources(sources, actual):
            per_source_metrics.setdefault(metrics.source, []).append(metrics)

    source_results = []
    for source, metric_list in sorted(per_source_metrics.items()):
        valid = [m for m in metric_list if m.n > 0]
        if not valid:
            continue
        source_results.append({
            "source": source,
            "shared_sample_n": sum(m.n for m in valid),
            "dates_included": len(valid),
            "mae": _weighted_mean([m.mae for m in valid], [m.n for m in valid]),
            "rmse": _weighted_mean([m.rmse for m in valid], [m.n for m in valid]),
            "pearson": _weighted_mean([m.correlation for m in valid], [m.n for m in valid]),
            "spearman": _weighted_mean([m.rank_correlation for m in valid], [m.n for m in valid]),
            "avg_top5_hit_rate": _simple_mean([m.top5_hit_rate for m in valid]),
            "avg_top10_hit_rate": _simple_mean([m.top10_hit_rate for m in valid]),
            "avg_top20_hit_rate": _simple_mean([m.top20_hit_rate for m in valid]),
        })

    return {"slates_requested": len(slate_dates), "slates_with_actual_results": dates_evaluated, "source_metrics": source_results}


# ---------------------------------------------------------------------------
# ML lineup grading (M32.4 lineup sets)
# ---------------------------------------------------------------------------


def load_lineup_sets_for_slate(slate_date: str, slate_id: str, projection_source: Optional[str] = None, lineups_root: Path = DEFAULT_LINEUPS_ROOT) -> List[dict]:
    """Every persisted dk_lineups_<ts>.json for `slate_date` whose
    provenance slate_id matches (see M32.4's optimizer/persistence.py).
    A lineup set built before M32.4 (no slate_id field at all) is never
    matched -- there is nothing to grade for it under this slate."""
    folder = Path(lineups_root) / slate_date
    if not folder.exists():
        return []
    matched = []
    for path in sorted(folder.glob("dk_lineups_*.json")):
        with path.open("r", encoding="utf-8") as f:
            doc = json.load(f)
        if doc.get("slate_id") != slate_id:
            continue
        if projection_source is not None and doc.get("projection_source") != projection_source:
            continue
        doc["_source_path"] = str(path)
        matched.append(doc)
    return matched


def grade_one_lineup(lineup: dict, actual_by_id: Dict[str, float]) -> dict:
    """A lineup is `fully_graded` only when EVERY assignment has an
    actual result -- a lineup with even one still-ungraded player never
    reports a fabricated partial sum as if it were the real total."""
    assignments = lineup.get("assignments", [])
    players = []
    missing = []
    actual_sum = 0.0
    for a in assignments:
        mlb_id = a.get("mlb_player_id")
        actual = actual_by_id.get(mlb_id) if mlb_id else None
        players.append({
            "name": a.get("name"), "mlb_player_id": mlb_id, "slot": a.get("slot"),
            "projection": a.get("projection"), "actual_dk": actual,
            "difference": round(actual - a.get("projection", 0.0), 3) if actual is not None else None,
        })
        if actual is None:
            missing.append(a.get("name"))
        else:
            actual_sum += actual

    fully_graded = len(missing) == 0 and len(assignments) > 0
    return {
        "lineup_index": lineup.get("index"),
        "salary": lineup.get("salary"),
        "projected": lineup.get("projection"),
        "actual": round(actual_sum, 3) if fully_graded else None,
        "difference": round(actual_sum - lineup.get("projection", 0.0), 3) if fully_graded else None,
        "fully_graded": fully_graded,
        "missing_players": missing,
        "players": players,
    }


def grade_lineup_sets_for_slate(slate_date: str, slate_id: str, projection_source: str = "big_money_ml", results_root: Path = DEFAULT_RESULTS_ROOT, lineups_root: Path = DEFAULT_LINEUPS_ROOT) -> dict:
    lineup_sets = load_lineup_sets_for_slate(slate_date, slate_id, projection_source=projection_source, lineups_root=lineups_root)
    actual_combined = load_actual_combined_points(slate_date, results_root=results_root)

    graded_lineups: List[dict] = []
    for doc in lineup_sets:
        for lineup in doc.get("lineups", []):
            graded_lineups.append(grade_one_lineup(lineup, actual_combined))

    fully_graded = [g for g in graded_lineups if g["fully_graded"]]
    result = {
        "projection_source": projection_source,
        "lineup_sets_found": len(lineup_sets),
        "lineups_total": len(graded_lineups),
        "lineups_fully_graded": len(fully_graded),
        "lineups": graded_lineups,
    }
    if fully_graded:
        actuals = [g["actual"] for g in fully_graded]
        projecteds = [g["projected"] for g in fully_graded]
        errors = [g["difference"] for g in fully_graded]
        result["highest_actual"] = max(actuals)
        result["lowest_actual"] = min(actuals)
        result["average_actual"] = round(sum(actuals) / len(actuals), 3)
        result["average_projected"] = round(sum(projecteds) / len(projecteds), 3)
        result["average_projection_error"] = round(sum(errors) / len(errors), 3)
    else:
        result["highest_actual"] = result["lowest_actual"] = result["average_actual"] = None
        result["average_projected"] = result["average_projection_error"] = None
    return result


def compare_lineup_sources_for_slate(slate_date: str, slate_id: str, sources: List[str], results_root: Path = DEFAULT_RESULTS_ROOT, lineups_root: Path = DEFAULT_LINEUPS_ROOT) -> dict:
    """Never fabricates a comparison for a source with no saved lineup
    set for this slate -- that source is simply absent from the result."""
    out = {}
    for source in sources:
        graded = grade_lineup_sets_for_slate(slate_date, slate_id, projection_source=source, results_root=results_root, lineups_root=lineups_root)
        if graded["lineup_sets_found"] == 0:
            continue
        out[source] = {
            "lineups_total": graded["lineups_total"],
            "lineups_fully_graded": graded["lineups_fully_graded"],
            "average_projected": graded["average_projected"],
            "average_actual": graded["average_actual"],
            "best_actual": graded["highest_actual"],
            "worst_actual": graded["lowest_actual"],
        }
    return out


# ---------------------------------------------------------------------------
# Known monitors -- thin re-exports for a single, discoverable import
# surface (the underlying implementations already live in
# big_money_ml_evaluation.py from M32.2B/M32.3B and are NOT duplicated).
# ---------------------------------------------------------------------------

__all__ = [
    "check_slate_final_status", "collect_and_score_final_games", "build_expected_player_lists",
    "build_all_player_grading_records", "evaluate_forward_combined_performance",
    "grade_lineup_sets_for_slate", "compare_lineup_sources_for_slate",
    "compute_ceiling_magnitude_monitor", "compute_zero_game_monitor", "compute_disaster_start_bucket",
]
