"""Orchestrates the AI Projection Engine: combines the Independent
Projection baseline (the Pitcher/Batter Agent's own `projection`, never
recomputed) with every reused signal -- weather, Vegas, bullpen, park,
ownership, matchup, recent form, external gap -- into one AI Projection
per player, with reasons and a deterministic summary.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config.projection_engine_config import AI_GRADE_BANDS, AI_GRADE_OVERALL_SCORE_ADJUSTMENT_SCALE, AI_PROJECTION_ENGINE_VERSION
from projection_engine import reasons as reasons_module
from projection_engine import signals as signals_module
from projection_engine.models import AIPlayerProjection, SignalContribution
from projection_engine.weights import apply_weight, blend_confidence, blend_risk, cap_total_adjustment


def grade_for(score: Optional[float]) -> Optional[str]:
    """AI_GRADE_BANDS is checked high-to-low; the first matching band
    wins (same pattern as config/adjustment_config.py's
    CONFIDENCE_ADJUSTMENT_CAPS)."""
    if score is None:
        return None
    for band in AI_GRADE_BANDS:
        if score >= band["min_score"]:
            return band["grade"]
    return AI_GRADE_BANDS[-1]["grade"]


def _collect_signals(
    player_type: str,
    board_record: dict,
    game: Optional[dict],
    is_home: Optional[bool],
    ownership_row: Optional[dict],
    independent_projection: Optional[float],
    external_projection: Optional[float],
) -> List[SignalContribution]:
    raw_signals = []

    if game is not None and is_home is not None:
        weather = signals_module.weather_signal(player_type, game.get("weather"), game.get("weather_analysis"))
        if weather is not None:
            raw_signals.append(weather)
        vegas = signals_module.vegas_signal(player_type, is_home, game.get("vegas"))
        if vegas is not None:
            raw_signals.append(vegas)
        bullpen = signals_module.bullpen_signal(player_type, is_home, game.get("bullpen_home"), game.get("bullpen_away"))
        if bullpen is not None:
            raw_signals.append(bullpen)
        park = signals_module.park_signal(player_type, game.get("ballpark"))
        if park is not None:
            raw_signals.append(park)

    ownership = signals_module.ownership_signal(ownership_row)
    if ownership is not None:
        raw_signals.append(ownership)

    matchup = signals_module.matchup_signal(board_record)
    if matchup is not None:
        raw_signals.append(matchup)

    recent_form = signals_module.recent_form_signal(player_type, board_record)
    if recent_form is not None:
        raw_signals.append(recent_form)

    external = signals_module.external_gap_signal(independent_projection, external_projection)
    if external is not None:
        raw_signals.append(external)

    return [apply_weight(raw, player_type) for raw in raw_signals]


def build_ai_player_projection(
    board_record: dict,
    player_type: str,
    game: Optional[dict] = None,
    ownership_row: Optional[dict] = None,
    adjusted_row: Optional[dict] = None,
    salary: Optional[int] = None,
) -> Optional[AIPlayerProjection]:
    """Returns None (never a fabricated record) when the player has no
    Independent Projection to build from -- see
    projection_engine/validator.py and scripts/run_ai_projection_engine.py
    for how a missing baseline is reported, not silently dropped."""
    independent_projection = board_record.get("projection")
    if independent_projection is None:
        return None

    independent_ceiling = board_record.get("ceiling")
    independent_floor = board_record.get("floor")
    external_projection = adjusted_row.get("external_projection") if adjusted_row else None
    adjusted_projection = adjusted_row.get("adjusted_projection") if adjusted_row else None

    is_home = game.get("home_team") == board_record.get("team") if game is not None else None

    signals = _collect_signals(player_type, board_record, game, is_home, ownership_row, independent_projection, external_projection)

    total_raw = sum(s.delta for s in signals)
    total_adjustment, capped = cap_total_adjustment(total_raw, independent_projection)

    ai_projection = round(max(0.0, independent_projection + total_adjustment), 2)
    ratio = (ai_projection / independent_projection) if independent_projection else 1.0
    ai_ceiling = round(independent_ceiling * ratio, 2) if independent_ceiling is not None else None
    ai_floor = round(independent_floor * ratio, 2) if independent_floor is not None else None

    total_adjustment_percent = round((total_adjustment / independent_projection) * 100.0, 2) if independent_projection else None

    ai_confidence = blend_confidence(
        board_record.get("confidence"),
        ownership_row.get("ownership_confidence") if ownership_row else None,
        adjusted_row.get("adjustment_confidence") if adjusted_row else None,
    )
    ai_risk = blend_risk(
        board_record.get("risk_score"),
        signals,
        game.get("weather_analysis") if game is not None else None,
        total_adjustment_percent,
    )

    overall_score = board_record.get("overall_score")
    grade_score = None
    if overall_score is not None:
        nudge = (total_adjustment_percent or 0.0) * AI_GRADE_OVERALL_SCORE_ADJUSTMENT_SCALE
        grade_score = max(0.0, min(100.0, overall_score + nudge))
    ai_grade = grade_for(grade_score)

    ai_value_score = round((ai_projection / salary) * 1000.0, 2) if salary else None

    reasons_list = reasons_module.build_reasons_list(signals)
    ai_summary = reasons_module.build_ai_summary(board_record.get("name", ""), ai_projection, ai_confidence, ai_risk, signals)

    return AIPlayerProjection(
        player_id=board_record["player_id"],
        name=board_record.get("name", ""),
        team=board_record.get("team", ""),
        player_type=player_type,
        opponent=board_record.get("opponent"),
        game_id=board_record.get("game_id"),
        salary=salary,
        independent_projection=independent_projection,
        independent_ceiling=independent_ceiling,
        independent_floor=independent_floor,
        external_projection=external_projection,
        adjusted_projection=adjusted_projection,
        ai_projection=ai_projection,
        ai_ceiling=ai_ceiling,
        ai_floor=ai_floor,
        ai_confidence=ai_confidence,
        ai_risk=ai_risk,
        ai_grade=ai_grade,
        ai_value_score=ai_value_score,
        total_adjustment=round(total_adjustment, 3),
        total_adjustment_percent=total_adjustment_percent,
        adjustment_capped=capped,
        signals=signals,
        reasons=reasons_list,
        ai_summary=ai_summary,
        model_version=AI_PROJECTION_ENGINE_VERSION,
    )


def build_ai_projection_slate(
    pitcher_snapshot: dict,
    batter_snapshot: dict,
    environment_report: Optional[dict] = None,
    ownership_snapshot: Optional[dict] = None,
    adjusted_snapshot: Optional[dict] = None,
    pool_doc: Optional[dict] = None,
) -> Tuple[List[AIPlayerProjection], List[str]]:
    """Returns (records, warnings). `warnings` names every player who
    was skipped because they had no Independent Projection to start
    from -- never a silent drop."""
    games_by_id: Dict[str, dict] = {}
    if environment_report:
        for g in environment_report.get("games", []):
            if g.get("game_id"):
                games_by_id[g["game_id"]] = g

    ownership_by_mlb_id: Dict[str, dict] = {}
    if ownership_snapshot:
        for p in ownership_snapshot.get("players", []):
            if p.get("mlb_player_id"):
                ownership_by_mlb_id[p["mlb_player_id"]] = p

    adjusted_by_mlb_id: Dict[str, dict] = {}
    if adjusted_snapshot:
        for r in adjusted_snapshot.get("records", []):
            if r.get("independent_player_id"):
                adjusted_by_mlb_id[r["independent_player_id"]] = r

    salary_by_mlb_id: Dict[str, int] = {}
    if pool_doc:
        for p in pool_doc.get("players", []):
            if p.get("mlb_player_id") and p.get("salary") is not None:
                salary_by_mlb_id[p["mlb_player_id"]] = p["salary"]

    records: List[AIPlayerProjection] = []
    warnings: List[str] = []

    all_records = [(r, "pitcher") for r in pitcher_snapshot.get("pitchers", [])] + [(r, "hitter") for r in batter_snapshot.get("hitters", [])]

    for record, player_type in all_records:
        player_id = record.get("player_id")
        game = games_by_id.get(record.get("game_id"))
        ownership_row = ownership_by_mlb_id.get(player_id)
        adjusted_row = adjusted_by_mlb_id.get(player_id)
        salary = salary_by_mlb_id.get(player_id)

        player = build_ai_player_projection(record, player_type, game, ownership_row, adjusted_row, salary)
        if player is None:
            warnings.append(f"Skipped {record.get('name', player_id)}: missing independent projection.")
            continue
        records.append(player)

    return records, warnings


def build_ai_projection_document(
    slate_date: str,
    records: List[AIPlayerProjection],
    warnings: List[str],
    pitcher_snapshot_path: Optional[str] = None,
    batter_snapshot_path: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "slate_date": slate_date,
        "generated_at": generated_at,
        "model_version": AI_PROJECTION_ENGINE_VERSION,
        "pitcher_snapshot_path": pitcher_snapshot_path,
        "batter_snapshot_path": batter_snapshot_path,
        "player_count": len(records),
        "players": [r.to_dict() for r in records],
        "warnings": warnings,
    }
