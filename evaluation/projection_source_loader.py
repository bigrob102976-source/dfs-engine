"""IO layer that wires evaluation/projection_source_comparison.py's pure
metric math to real, already-persisted snapshots: the Independent
projection (predictions/), External baseline + Big Money Adjusted
(external_projection_snapshots/ / adjusted_projection_snapshots/), the
AI Projection (ai_projection_snapshots/), the Native Projection
(native_projection_snapshots/, Milestone 23), the live BlueCollar DFS
projection (bluecollar_projection_snapshots/, BlueCollar Live Projection
Integration), and actual postgame results (results/).

BlueCollar is the one source here that's slate-scoped, not date-only
(see bluecollar/persistence.py) -- its loaders take an explicit
`dk_slate_id` and simply omit the source (return {}) when no slate id is
given or no snapshot exists for that (date, slate). Only MATCHED players
with a genuinely usable_projection (never a fabricated 0.0 -- see
bluecollar/build.py) ever appear in the returned map.

Milestone 23 added a hitter equivalent of every pitcher loader below
(results/<date>/hitter_results.json via scripts/collect_hitter_results.py,
batter_board snapshots, hitter-filtered adjusted/AI/native records) --
before this milestone, hitters could never appear in any comparison here.
Every loader degrades gracefully (returns {} / None) when a source
doesn't exist for a date rather than raising -- comparing whatever
sources happen to be available for that slate is a normal, expected
state, not a failure.

This module only ever reads a PREGAME snapshot against POSTGAME results
collected after that snapshot was taken -- same lookahead-bias
discipline as evaluation/pitcher_evaluator.py.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from bluecollar.persistence import DEFAULT_BLUECOLLAR_ROOT, load_latest_bluecollar_snapshot
from bluecollar.player_matcher import _PITCHER_POSITIONS as BLUECOLLAR_PITCHER_POSITIONS
from external_projections.persistence import DEFAULT_ADJUSTED_SNAPSHOT_ROOT, load_latest_adjusted_snapshot
from projection_engine.persistence import DEFAULT_AI_PROJECTION_ROOT, load_latest_ai_projection_snapshot
from research.prediction_snapshot import DEFAULT_PREDICTIONS_ROOT, list_snapshots, load_snapshot

from native_projections.persistence import (
    DEFAULT_NATIVE_PROJECTION_ROOT,
    list_native_projection_snapshots,
    load_native_projection_snapshot,
)

DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results"


def load_actual_pitcher_points(slate_date: str, results_root: Path = DEFAULT_RESULTS_ROOT) -> Dict[str, float]:
    """{player_id: dfs_points} from results/<date>/pitcher_results.json --
    the only actual-results source this codebase has (pitcher-only).
    Returns {} (never raises) when no results have been collected yet."""
    path = Path(results_root) / slate_date / "pitcher_results.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    return {
        str(r["player_id"]): r["dfs_points"]
        for r in doc.get("results", [])
        if r.get("player_id") is not None and r.get("dfs_points") is not None
    }


def load_independent_pitcher_projections(slate_date: str, predictions_root: Path = DEFAULT_PREDICTIONS_ROOT) -> Tuple[Dict[str, float], Optional[str]]:
    """{player_id: projection} from the latest pitcher_board snapshot for
    `slate_date`. Returns ({}, None) when no snapshot exists yet."""
    snapshots = list_snapshots(slate_date, predictions_root, filename_prefix="pitcher_board")
    if not snapshots:
        return {}, None
    snapshot_path = snapshots[-1]
    snapshot = load_snapshot(snapshot_path)
    return {
        str(p["player_id"]): p["projection"]
        for p in snapshot.get("pitchers", [])
        if p.get("projection") is not None
    }, str(snapshot_path)


def load_external_and_adjusted_pitcher_projections(
    slate_date: str, adjusted_root: Path = DEFAULT_ADJUSTED_SNAPSHOT_ROOT,
) -> Tuple[Dict[str, float], Dict[str, float], Optional[str]]:
    """(external_by_id, adjusted_by_id, adjusted_snapshot_path) -- both
    maps built from the SAME latest adjusted-projection snapshot's own
    independent_player_id/external_projection/adjusted_projection fields
    (already merged and keyed to the mlb player_id space by
    external_projections/projection_merge.py), filtered to pitchers
    only. Returns ({}, {}, None) when no adjusted snapshot exists yet."""
    snapshot = load_latest_adjusted_snapshot(slate_date, output_root=adjusted_root)
    if snapshot is None:
        return {}, {}, None

    external_by_id: Dict[str, float] = {}
    adjusted_by_id: Dict[str, float] = {}
    for record in snapshot.get("records", []):
        if record.get("player_type") != "pitcher":
            continue
        player_id = record.get("independent_player_id")
        if player_id is None:
            continue
        if record.get("external_projection") is not None:
            external_by_id[str(player_id)] = record["external_projection"]
        if record.get("adjusted_projection") is not None:
            adjusted_by_id[str(player_id)] = record["adjusted_projection"]

    return external_by_id, adjusted_by_id, None


def load_ai_pitcher_projections(slate_date: str, ai_root: Path = DEFAULT_AI_PROJECTION_ROOT) -> Tuple[Dict[str, float], Optional[str]]:
    """{player_id: ai_projection} from the latest AI Projection snapshot
    for `slate_date`, filtered to pitchers only. Returns ({}, None) when
    no AI Projection snapshot exists yet."""
    snapshot = load_latest_ai_projection_snapshot(slate_date, output_root=ai_root)
    if snapshot is None:
        return {}, None
    return {
        str(p["player_id"]): p["ai_projection"]
        for p in snapshot.get("players", [])
        if p.get("player_type") == "pitcher" and p.get("ai_projection") is not None
    }, None


def _load_latest_native_projection_document(slate_date: str, native_root: Path) -> Optional[dict]:
    snapshots = list_native_projection_snapshots(slate_date, output_root=native_root)
    if not snapshots:
        return None
    return load_native_projection_snapshot(snapshots[-1])


def load_native_pitcher_projections(slate_date: str, native_root: Path = DEFAULT_NATIVE_PROJECTION_ROOT) -> Tuple[Dict[str, float], Optional[str]]:
    """{player_id: native_projection} from the latest Native Projection
    snapshot for `slate_date`, filtered to pitchers only. Returns ({}, None)
    when no native snapshot exists yet."""
    document = _load_latest_native_projection_document(slate_date, native_root)
    if document is None:
        return {}, None
    return {
        str(p["player_id"]): p["native_projection"]
        for p in document.get("players", [])
        if p.get("player_type") == "pitcher" and p.get("native_projection") is not None
    }, None


def load_native_hitter_projections(slate_date: str, native_root: Path = DEFAULT_NATIVE_PROJECTION_ROOT) -> Tuple[Dict[str, float], Optional[str]]:
    """Hitter equivalent of load_native_pitcher_projections()."""
    document = _load_latest_native_projection_document(slate_date, native_root)
    if document is None:
        return {}, None
    return {
        str(p["player_id"]): p["native_projection"]
        for p in document.get("players", [])
        if p.get("player_type") == "hitter" and p.get("native_projection") is not None
    }, None


def _load_bluecollar_projections_by_position(
    slate_date: str, dk_slate_id: Optional[str], bluecollar_root: Path, pitcher_side: bool,
) -> Tuple[Dict[str, float], Optional[str]]:
    if not dk_slate_id:
        return {}, None
    snapshot = load_latest_bluecollar_snapshot(slate_date, dk_slate_id, output_root=bluecollar_root)
    if snapshot is None:
        return {}, None
    result: Dict[str, float] = {}
    for p in snapshot.get("players", []):
        if p.get("match_status") != "matched":
            continue
        player_id = p.get("mlb_player_id")
        usable = p.get("usable_projection")
        if player_id is None or usable is None:
            continue
        is_pitcher = str(p.get("position", "")).upper() in BLUECOLLAR_PITCHER_POSITIONS
        if is_pitcher != pitcher_side:
            continue
        result[str(player_id)] = usable
    return result, None


def load_bluecollar_pitcher_projections(
    slate_date: str, dk_slate_id: Optional[str], bluecollar_root: Path = DEFAULT_BLUECOLLAR_ROOT,
) -> Tuple[Dict[str, float], Optional[str]]:
    """{player_id: usable_projection} from the latest BlueCollar snapshot
    for (slate_date, dk_slate_id), pitchers only. Returns ({}, None) when
    no dk_slate_id is given or no snapshot exists yet -- BlueCollar is
    always slate-scoped, never date-only (see bluecollar/persistence.py)."""
    return _load_bluecollar_projections_by_position(slate_date, dk_slate_id, bluecollar_root, pitcher_side=True)


def load_bluecollar_hitter_projections(
    slate_date: str, dk_slate_id: Optional[str], bluecollar_root: Path = DEFAULT_BLUECOLLAR_ROOT,
) -> Tuple[Dict[str, float], Optional[str]]:
    """Hitter equivalent of load_bluecollar_pitcher_projections()."""
    return _load_bluecollar_projections_by_position(slate_date, dk_slate_id, bluecollar_root, pitcher_side=False)


def build_pitcher_projection_sources(
    slate_date: str,
    predictions_root: Path = DEFAULT_PREDICTIONS_ROOT,
    adjusted_root: Path = DEFAULT_ADJUSTED_SNAPSHOT_ROOT,
    ai_root: Path = DEFAULT_AI_PROJECTION_ROOT,
    native_root: Path = DEFAULT_NATIVE_PROJECTION_ROOT,
    dk_slate_id: Optional[str] = None,
    bluecollar_root: Path = DEFAULT_BLUECOLLAR_ROOT,
) -> Dict[str, Dict[str, float]]:
    """{source_label: {player_id: value}} for every source that actually
    has data for `slate_date` -- a source with no data for this slate is
    simply omitted, never included as an empty/fabricated entry."""
    sources: Dict[str, Dict[str, float]] = {}

    independent, _ = load_independent_pitcher_projections(slate_date, predictions_root=predictions_root)
    if independent:
        sources["independent"] = independent

    external, adjusted, _ = load_external_and_adjusted_pitcher_projections(slate_date, adjusted_root=adjusted_root)
    if external:
        sources["external"] = external
    if adjusted:
        sources["adjusted"] = adjusted

    ai, _ = load_ai_pitcher_projections(slate_date, ai_root=ai_root)
    if ai:
        sources["ai"] = ai

    native, _ = load_native_pitcher_projections(slate_date, native_root=native_root)
    if native:
        sources["native"] = native

    bluecollar, _ = load_bluecollar_pitcher_projections(slate_date, dk_slate_id, bluecollar_root=bluecollar_root)
    if bluecollar:
        sources["bluecollar"] = bluecollar

    return sources


# ----------------------------------------------------------------------------
# Hitters (Milestone 23)
# ----------------------------------------------------------------------------


def load_actual_hitter_points(slate_date: str, results_root: Path = DEFAULT_RESULTS_ROOT) -> Dict[str, float]:
    """Hitter equivalent of load_actual_pitcher_points() -- reads
    results/<date>/hitter_results.json (scripts/collect_hitter_results.py)."""
    path = Path(results_root) / slate_date / "hitter_results.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    return {
        str(r["player_id"]): r["dfs_points"]
        for r in doc.get("results", [])
        if r.get("player_id") is not None and r.get("dfs_points") is not None
    }


def load_independent_hitter_projections(slate_date: str, predictions_root: Path = DEFAULT_PREDICTIONS_ROOT) -> Tuple[Dict[str, float], Optional[str]]:
    """{player_id: projection} from the latest batter_board snapshot for
    `slate_date`. Returns ({}, None) when no snapshot exists yet."""
    snapshots = list_snapshots(slate_date, predictions_root, filename_prefix="batter_board")
    if not snapshots:
        return {}, None
    snapshot_path = snapshots[-1]
    snapshot = load_snapshot(snapshot_path)
    return {
        str(h["player_id"]): h["projection"]
        for h in snapshot.get("hitters", [])
        if h.get("projection") is not None
    }, str(snapshot_path)


def load_external_and_adjusted_hitter_projections(
    slate_date: str, adjusted_root: Path = DEFAULT_ADJUSTED_SNAPSHOT_ROOT,
) -> Tuple[Dict[str, float], Dict[str, float], Optional[str]]:
    """Hitter equivalent of load_external_and_adjusted_pitcher_projections()."""
    snapshot = load_latest_adjusted_snapshot(slate_date, output_root=adjusted_root)
    if snapshot is None:
        return {}, {}, None

    external_by_id: Dict[str, float] = {}
    adjusted_by_id: Dict[str, float] = {}
    for record in snapshot.get("records", []):
        if record.get("player_type") != "hitter":
            continue
        player_id = record.get("independent_player_id")
        if player_id is None:
            continue
        if record.get("external_projection") is not None:
            external_by_id[str(player_id)] = record["external_projection"]
        if record.get("adjusted_projection") is not None:
            adjusted_by_id[str(player_id)] = record["adjusted_projection"]

    return external_by_id, adjusted_by_id, None


def load_ai_hitter_projections(slate_date: str, ai_root: Path = DEFAULT_AI_PROJECTION_ROOT) -> Tuple[Dict[str, float], Optional[str]]:
    """Hitter equivalent of load_ai_pitcher_projections()."""
    snapshot = load_latest_ai_projection_snapshot(slate_date, output_root=ai_root)
    if snapshot is None:
        return {}, None
    return {
        str(p["player_id"]): p["ai_projection"]
        for p in snapshot.get("players", [])
        if p.get("player_type") == "hitter" and p.get("ai_projection") is not None
    }, None


def build_hitter_projection_sources(
    slate_date: str,
    predictions_root: Path = DEFAULT_PREDICTIONS_ROOT,
    adjusted_root: Path = DEFAULT_ADJUSTED_SNAPSHOT_ROOT,
    ai_root: Path = DEFAULT_AI_PROJECTION_ROOT,
    native_root: Path = DEFAULT_NATIVE_PROJECTION_ROOT,
    dk_slate_id: Optional[str] = None,
    bluecollar_root: Path = DEFAULT_BLUECOLLAR_ROOT,
) -> Dict[str, Dict[str, float]]:
    """Hitter equivalent of build_pitcher_projection_sources()."""
    sources: Dict[str, Dict[str, float]] = {}

    independent, _ = load_independent_hitter_projections(slate_date, predictions_root=predictions_root)
    if independent:
        sources["independent"] = independent

    external, adjusted, _ = load_external_and_adjusted_hitter_projections(slate_date, adjusted_root=adjusted_root)
    if external:
        sources["external"] = external
    if adjusted:
        sources["adjusted"] = adjusted

    ai, _ = load_ai_hitter_projections(slate_date, ai_root=ai_root)
    if ai:
        sources["ai"] = ai

    native, _ = load_native_hitter_projections(slate_date, native_root=native_root)
    if native:
        sources["native"] = native

    bluecollar, _ = load_bluecollar_hitter_projections(slate_date, dk_slate_id, bluecollar_root=bluecollar_root)
    if bluecollar:
        sources["bluecollar"] = bluecollar

    return sources
