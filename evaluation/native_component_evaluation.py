"""Component-level evaluation for the Native Projection Model.

Milestone 23 explicitly asks for more than "was the final DK-points
number close" -- it asks WHICH underlying component (projected K,
projected IP, projected HR rate, ...) is actually wrong. This module
compares native_projections' individual projected COMPONENTS (the same
ComponentValue.expected_count figures shown in the player detail
breakdown, native_projections/dk_scoring.py) against the corresponding
REAL postgame stat, aggregated across however many players/slates are
available.

Deliberately reuses the same {player_id: value} + MAE pattern as
evaluation/projection_source_comparison.py (mean_predicted vs mean_actual
on the same record doubles as a simple calibration check -- e.g. for a
rare event like home runs, "mean predicted HR count 0.15 vs mean actual
0.14" tells you the rate is well-calibrated in aggregate even though no
single player's HR outcome is well-predicted by MAE alone) rather than
inventing a second metric methodology.

No backtesting: only ever call this against dates where BOTH a native
snapshot and postgame results actually exist -- same discipline as every
other evaluation module in this codebase.
"""

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from research import innings


@dataclass
class ComponentComparison:
    component: str
    n: int
    mae: Optional[float]
    mean_predicted: Optional[float]
    mean_actual: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


def _compare_component(component: str, predicted_by_id: Dict[str, float], actual_by_id: Dict[str, float]) -> ComponentComparison:
    shared_ids = [pid for pid in predicted_by_id if pid in actual_by_id]
    if not shared_ids:
        return ComponentComparison(component=component, n=0, mae=None, mean_predicted=None, mean_actual=None)

    predicted = [predicted_by_id[pid] for pid in shared_ids]
    actual = [actual_by_id[pid] for pid in shared_ids]
    n = len(shared_ids)
    mae = round(sum(abs(p - a) for p, a in zip(predicted, actual)) / n, 3)
    return ComponentComparison(
        component=component, n=n, mae=mae,
        mean_predicted=round(sum(predicted) / n, 3),
        mean_actual=round(sum(actual) / n, 3),
    )


def _native_pitcher_component_maps(native_players: List[dict]) -> Dict[str, Dict[str, float]]:
    maps: Dict[str, Dict[str, float]] = {
        "strikeouts": {}, "walks": {}, "hits_allowed": {}, "earned_runs": {}, "innings_pitched": {},
    }
    for p in native_players:
        if p.get("player_type") != "pitcher":
            continue
        components = p.get("pitcher_components") or {}
        player_id = str(p["player_id"])
        for key in maps:
            component = components.get(key)
            if component and component.get("expected_count") is not None:
                maps[key][player_id] = component["expected_count"]
    return maps


def _actual_pitcher_component_maps(actual_results: List[dict]) -> Dict[str, Dict[str, float]]:
    maps: Dict[str, Dict[str, float]] = {
        "strikeouts": {}, "walks": {}, "hits_allowed": {}, "earned_runs": {}, "innings_pitched": {},
    }
    for r in actual_results:
        if r.get("status") not in ("completed_start", "did_not_start"):
            continue
        player_id = str(r["player_id"])
        if r.get("strikeouts") is not None:
            maps["strikeouts"][player_id] = r["strikeouts"]
        if r.get("walks") is not None:
            maps["walks"][player_id] = r["walks"]
        if r.get("hits_allowed") is not None:
            maps["hits_allowed"][player_id] = r["hits_allowed"]
        if r.get("earned_runs") is not None:
            maps["earned_runs"][player_id] = r["earned_runs"]
        if r.get("outs") is not None:
            maps["innings_pitched"][player_id] = innings.outs_to_decimal_innings(r["outs"])
    return maps


def evaluate_pitcher_components(native_players: List[dict], actual_results: List[dict]) -> List[ComponentComparison]:
    predicted = _native_pitcher_component_maps(native_players)
    actual = _actual_pitcher_component_maps(actual_results)
    return [_compare_component(component, predicted[component], actual[component]) for component in predicted]


def _native_hitter_component_maps(native_players: List[dict]) -> Dict[str, Dict[str, float]]:
    maps: Dict[str, Dict[str, float]] = {"home_runs": {}, "walks": {}, "stolen_bases": {}}
    for p in native_players:
        if p.get("player_type") != "hitter":
            continue
        components = p.get("hitter_components") or {}
        player_id = str(p["player_id"])
        for key in maps:
            component = components.get(key)
            if component and component.get("expected_count") is not None:
                maps[key][player_id] = component["expected_count"]
    return maps


def _actual_hitter_component_maps(actual_results: List[dict]) -> Dict[str, Dict[str, float]]:
    maps: Dict[str, Dict[str, float]] = {"home_runs": {}, "walks": {}, "stolen_bases": {}}
    for r in actual_results:
        if r.get("status") != "appeared":
            continue
        player_id = str(r["player_id"])
        if r.get("home_runs") is not None:
            maps["home_runs"][player_id] = r["home_runs"]
        if r.get("walks") is not None:
            maps["walks"][player_id] = r["walks"]
        if r.get("stolen_bases") is not None:
            maps["stolen_bases"][player_id] = r["stolen_bases"]
    return maps


def evaluate_hitter_components(native_players: List[dict], actual_results: List[dict]) -> List[ComponentComparison]:
    predicted = _native_hitter_component_maps(native_players)
    actual = _actual_hitter_component_maps(actual_results)
    return [_compare_component(component, predicted[component], actual[component]) for component in predicted]
