"""Milestone 32.3 -- hitter feature allowlists + feature audit.

Two allowlists, both DERIVED from historical_mlb.manifest.hitter_manifest()
(never redefined):

  ALWAYS_PREGAME_FEATURE_COLUMNS  -- every ALWAYS_PREGAME column, safe to
      use even before a lineup has posted (an "EARLY HITTER ML" model).
  AFTER_LINEUP_FEATURE_COLUMNS    -- ALWAYS_PREGAME_FEATURE_COLUMNS PLUS
      the 5 PREGAME_AFTER_LINEUPS columns (minus the opposing pitcher's
      raw identity, which is excluded as an identity-risk field, same
      discipline as player_id -- see _AFTER_LINEUP_IDENTITY_RISK), safe
      only once the actual lineup/opposing starter is confirmed (a
      "CONFIRMED-LINEUP HITTER ML" model).

A handful of ALWAYS_PREGAME columns are still excluded from both lists
for reasons OTHER than leakage -- bookkeeping identity columns, columns
confirmed 100% null (salary/Vegas, per M32.1's own findings), and one
column that is constant (zero information) across the entire warehouse
(lineup_availability -- every hitter row in this warehouse already
represents a confirmed lineup appearance, by construction; see
FeatureAuditRow.reason for each).
"""

from dataclasses import dataclass
from typing import List

import pandas as pd

from historical_mlb.manifest import TARGET, hitter_manifest

# Columns that ARE ALWAYS_PREGAME per the manifest but are excluded from
# the MODEL's feature matrix for a reason other than leakage risk.
_BOOKKEEPING_ONLY = {"season", "game_date", "game_pk", "game_number", "player_id", "player_name", "game_start_time"}
_CONFIRMED_EMPTY = {"draftkings_salary", "vegas_team_total"}  # M32.1: always/effectively null, never fabricated
_REDUNDANT = {"weather_source"}  # redundant with weather_available (same information)
_CONSTANT = {"lineup_availability"}  # always "confirmed" in this warehouse (hitter rows only exist for confirmed appearances) -- zero information

# The opposing starter's raw MLBAM id is an identity field, not a skill
# feature -- same "do NOT one-hot player ID as a shortcut" discipline
# the pitcher model applies to its own player_id/player_name.
_AFTER_LINEUP_IDENTITY_RISK = {"opposing_starting_pitcher_id"}

CATEGORICAL_FEATURE_COLUMNS = ["team", "opponent", "home_away", "bat_hand", "throw_hand", "venue_roof_type", "venue_id"]
AFTER_LINEUP_CATEGORICAL_ADDITIONS = ["opposing_starting_pitcher_hand"]
AFTER_LINEUP_NUMERIC_ADDITIONS = ["opposing_pitcher_era_season", "opposing_pitcher_k_pct_season", "batting_order_actual"]

_ALWAYS_PREGAME_EXCLUDED = _BOOKKEEPING_ONLY | _CONFIRMED_EMPTY | _REDUNDANT | _CONSTANT

NUMERIC_FEATURE_COLUMNS = [
    f.name for f in hitter_manifest()
    if f.availability_class == "ALWAYS_PREGAME"
    and f.name not in _ALWAYS_PREGAME_EXCLUDED
    and f.name not in CATEGORICAL_FEATURE_COLUMNS
    and f.name != "weather_available"
] + ["weather_available"]

ALWAYS_PREGAME_FEATURE_COLUMNS = NUMERIC_FEATURE_COLUMNS + CATEGORICAL_FEATURE_COLUMNS

AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS = NUMERIC_FEATURE_COLUMNS + AFTER_LINEUP_NUMERIC_ADDITIONS
AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS = CATEGORICAL_FEATURE_COLUMNS + AFTER_LINEUP_CATEGORICAL_ADDITIONS
AFTER_LINEUP_FEATURE_COLUMNS = AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS + AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS


def feature_columns_for(availability_class: str) -> List[str]:
    if availability_class == "ALWAYS_PREGAME":
        return ALWAYS_PREGAME_FEATURE_COLUMNS
    if availability_class == "AFTER_LINEUP":
        return AFTER_LINEUP_FEATURE_COLUMNS
    raise ValueError(f"Unknown feature availability class: {availability_class!r}")


def numeric_columns_for(availability_class: str) -> List[str]:
    if availability_class == "ALWAYS_PREGAME":
        return NUMERIC_FEATURE_COLUMNS
    if availability_class == "AFTER_LINEUP":
        return AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS
    raise ValueError(f"Unknown feature availability class: {availability_class!r}")


def categorical_columns_for(availability_class: str) -> List[str]:
    if availability_class == "ALWAYS_PREGAME":
        return CATEGORICAL_FEATURE_COLUMNS
    if availability_class == "AFTER_LINEUP":
        return AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS
    raise ValueError(f"Unknown feature availability class: {availability_class!r}")


@dataclass
class FeatureAuditRow:
    column: str
    family: str
    dtype: str
    missing_pct: float
    allowed_pregame: bool
    availability_class: str
    included_always_pregame: bool
    included_after_lineup: bool
    reason: str


def _family_of(column: str) -> str:
    if column.startswith("rolling_"):
        return "rolling"
    if column.startswith("statcast_"):
        return "statcast"
    if column.startswith("platoon_"):
        return "platoon"
    if column.startswith("opposing_"):
        return "opposing_pitcher"
    if column.startswith("weather_") or column == "venue_roof_type":
        return "weather"
    if column in ("batting_order_actual", "lineup_availability"):
        return "lineup"
    if column in ("team", "venue_id", "home_away"):
        return "venue"
    if column in ("bat_hand", "throw_hand"):
        return "handedness"
    if column.startswith("actual_"):
        return "target" if column == "actual_dk_points" else "outcome"
    if column in ("draftkings_salary", "vegas_team_total"):
        return "unavailable_source"
    return "core"


def build_feature_audit(df: pd.DataFrame) -> List[FeatureAuditRow]:
    """One row per column ACTUALLY present in the warehouse's hitter
    table. Every warehouse column gets an explicit included/excluded
    verdict (for BOTH feature sets) and a reason -- nothing is silently
    dropped."""
    manifest_by_name = {f.name: f for f in hitter_manifest()}
    rows: List[FeatureAuditRow] = []
    for column in df.columns:
        f = manifest_by_name.get(column)
        allowed_pregame = f is not None and f.availability_class in ("ALWAYS_PREGAME", "PREGAME_AFTER_LINEUPS")
        missing_pct = round(float(df[column].isna().mean()) * 100, 2)
        included_always = column in ALWAYS_PREGAME_FEATURE_COLUMNS
        included_after = column in AFTER_LINEUP_FEATURE_COLUMNS
        availability_class = f.availability_class if f is not None else "UNKNOWN"

        if f is None:
            reason = "not in the hitter feature manifest (unexpected column)"
        elif f.availability_class == TARGET:
            reason = "TARGET column -- the model's prediction target, never a feature"
        elif f.availability_class == "HISTORICAL_OUTCOME_ONLY":
            reason = "actual (postgame) outcome -- never knowable before first pitch"
        elif column in _AFTER_LINEUP_IDENTITY_RISK:
            reason = "opposing starter's raw MLBAM id -- identity field, not a skill feature (never one-hotted)"
        elif column in _BOOKKEEPING_ONLY:
            reason = "identity/bookkeeping column, not a skill feature"
        elif column in _CONFIRMED_EMPTY:
            reason = "M32.1 confirmed this source is unavailable (100% null) -- never fabricated, excluded rather than imputed"
        elif column in _REDUNDANT:
            reason = "redundant with weather_available"
        elif column in _CONSTANT:
            reason = "constant across the entire warehouse (always 'confirmed') -- zero information"
        elif included_after and not included_always:
            reason = "PREGAME_AFTER_LINEUPS and genuinely available -- included in the AFTER_LINEUP feature set only"
        elif included_always:
            reason = "ALWAYS_PREGAME and genuinely available -- included in both feature sets"
        else:
            reason = "excluded for an unlisted reason -- audit this"

        rows.append(FeatureAuditRow(
            column=column, family=_family_of(column), dtype=str(df[column].dtype),
            missing_pct=missing_pct, allowed_pregame=allowed_pregame, availability_class=availability_class,
            included_always_pregame=included_always, included_after_lineup=included_after, reason=reason,
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
    if "draftkings_salary" in columns or "vegas_team_total" in columns:
        raise ValueError("Leakage guard: unavailable-source column (salary/Vegas) must never be a feature.")
    if "player_id" in columns or "player_name" in columns:
        raise ValueError("Leakage guard: player identity must never be a feature.")
    if "opposing_starting_pitcher_id" in columns:
        raise ValueError("Leakage guard: opposing pitcher identity must never be a feature.")
