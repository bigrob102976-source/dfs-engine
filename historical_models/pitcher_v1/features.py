"""Milestone 32.2 -- pitcher feature allowlist + feature audit.

The allowlist is DERIVED from historical_mlb.manifest.pitcher_manifest()
(never redefined) -- every column here is ALWAYS_PREGAME per that
manifest, which is itself the enforcement point M32.1 built specifically
so a training pipeline like this one never has to re-litigate "is this
column safe." A few ALWAYS_PREGAME columns are still excluded here for
reasons OTHER than leakage (see FeatureAuditRow.reason for each) --
bookkeeping identity columns, columns confirmed 100% null (salary/Vegas,
per M32.1's own findings), and player identity (explicitly forbidden
from being one-hotted, per this milestone's own instruction).
"""

from dataclasses import dataclass
from typing import List

import pandas as pd

from historical_mlb.manifest import TARGET, hitter_manifest, pitcher_manifest

# Columns that ARE ALWAYS_PREGAME per the manifest but are excluded from
# the MODEL's feature matrix for a reason other than leakage risk.
_BOOKKEEPING_ONLY = {"season", "game_date", "game_pk", "game_number", "player_id", "player_name", "game_start_time"}
_CONFIRMED_EMPTY = {"draftkings_salary", "vegas_moneyline", "vegas_total"}  # M32.1: always null, never fabricated
_REDUNDANT = {"weather_source"}  # redundant with weather_available (same information, one is boolean the other a constant string)
_IDENTITY_RISK = set()  # player_id/player_name already caught by _BOOKKEEPING_ONLY; nothing else in the pitcher manifest identifies a specific player

CATEGORICAL_FEATURE_COLUMNS = ["team", "opponent", "home_away", "throw_hand", "bat_hand", "venue_roof_type", "venue_id"]

NUMERIC_FEATURE_COLUMNS = [
    f.name for f in pitcher_manifest()
    if f.availability_class == "ALWAYS_PREGAME"
    and f.name not in _BOOKKEEPING_ONLY
    and f.name not in _CONFIRMED_EMPTY
    and f.name not in _REDUNDANT
    and f.name not in CATEGORICAL_FEATURE_COLUMNS
    and f.name != "weather_available"  # boolean, handled separately below (kept, just listed explicitly for clarity)
] + ["weather_available"]

FEATURE_COLUMNS = NUMERIC_FEATURE_COLUMNS + CATEGORICAL_FEATURE_COLUMNS


@dataclass
class FeatureAuditRow:
    column: str
    family: str
    dtype: str
    missing_pct: float
    allowed_pregame: bool
    included: bool
    reason: str


def _family_of(column: str) -> str:
    if column.startswith("rolling_"):
        return "rolling"
    if column.startswith("statcast_"):
        return "statcast"
    if column.startswith("platoon_"):
        return "platoon"
    if column.startswith("opponent_"):
        return "opponent"
    if column.startswith("weather_") or column == "venue_roof_type":
        return "weather"
    if column in ("days_rest", "previous_start_pitch_count", "starts_last_30d", "innings_last_30d"):
        return "workload"
    if column in ("team", "opponent_team", "venue_id", "home_away"):
        return "venue"
    if column in ("throw_hand", "bat_hand"):
        return "handedness"
    if column.startswith("actual_"):
        return "target" if column == "actual_dk_points" else "outcome"
    if column in ("draftkings_salary", "vegas_moneyline", "vegas_total"):
        return "unavailable_source"
    return "core"


def build_feature_audit(df: pd.DataFrame) -> List[FeatureAuditRow]:
    """One row per column ACTUALLY present in the warehouse's pitcher
    table (not per manifest entry -- some manifest entries, e.g.
    Statcast metrics under a since-renamed key, would silently vanish
    from an audit keyed the other way around). Every warehouse column
    gets an explicit included/excluded verdict and a reason -- nothing
    is silently dropped."""
    manifest_by_name = {f.name: f for f in pitcher_manifest()}
    rows: List[FeatureAuditRow] = []
    for column in df.columns:
        f = manifest_by_name.get(column)
        allowed_pregame = f is not None and f.availability_class == "ALWAYS_PREGAME"
        missing_pct = round(float(df[column].isna().mean()) * 100, 2)
        included = column in FEATURE_COLUMNS

        if column == "starter_flag":
            reason = "dataset FILTER (starter_flag == True), not a model feature -- constant True after filtering, zero information"
        elif f is None:
            reason = "not in the pitcher feature manifest (unexpected column)"
        elif f.availability_class == TARGET:
            reason = "TARGET column -- the model's prediction target, never a feature"
        elif f.availability_class == "HISTORICAL_OUTCOME_ONLY":
            reason = "actual (postgame) outcome -- never knowable before first pitch"
        elif f.availability_class == "PREGAME_AFTER_LINEUPS":
            reason = "only safe after lineups post -- excluded from this pregame-only V1"
        elif column in _BOOKKEEPING_ONLY:
            reason = "identity/bookkeeping column, not a skill feature"
        elif column in _CONFIRMED_EMPTY:
            reason = "M32.1 confirmed this source is unavailable (100% null) -- never fabricated, excluded rather than imputed"
        elif column in _REDUNDANT:
            reason = "redundant with weather_available"
        elif included:
            reason = "ALWAYS_PREGAME and genuinely available -- included"
        else:
            reason = "excluded for an unlisted reason -- audit this"

        rows.append(FeatureAuditRow(
            column=column, family=_family_of(column), dtype=str(df[column].dtype),
            missing_pct=missing_pct, allowed_pregame=allowed_pregame, included=included, reason=reason,
        ))
    return rows


def assert_no_leakage(columns: List[str]) -> None:
    """Hard, structural guard: raises if any forbidden column name ever
    makes it into a feature list. Called at the start of both training
    and inference, not just tested in isolation."""
    forbidden_prefixes = ("actual_", "target", "result", "final", "postgame")
    violations = [c for c in columns if any(c.lower().startswith(p) for p in forbidden_prefixes)]
    if violations:
        raise ValueError(f"Leakage guard: forbidden column(s) in feature list: {violations}")
    if "draftkings_salary" in columns or "vegas_moneyline" in columns or "vegas_total" in columns:
        raise ValueError("Leakage guard: unavailable-source column (salary/Vegas) must never be a feature.")
