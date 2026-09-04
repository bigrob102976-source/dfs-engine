"""NFL M8 -- joins the real DK canonical pool (M2) through the real M6B
DK<->GSIS crosswalk to real M8 historical usage features, producing the
normalized NflProjectionFeatures record a future Big Money Native NFL
projection model (M9+) would consume. Offensive players only (QB/RB/WR/
TE) -- DST is intentionally excluded here (see historical_nfl/
dst_usage_normalize.py for DST's own, separate, team-level feature path;
DST never gets a fake GSIS ID or a row in this join).

Never name-matches as a fallback: a DK player whose crosswalk row has no
gsis_id (or has no crosswalk row at all) is reported as UNRESOLVED, not
guessed (mirrors nfl/odds_matching.py's identical discipline for
DK<->odds-provider team matching).

Game context (M7) is attached when available but never blocks feature
construction -- see build_projection_features()'s own docstring."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from historical_nfl.identity_models import NflCrosswalkRow
from historical_nfl.usage_models import NflUsageRecord
from historical_nfl.usage_rolling import compute_player_rolling_features, compute_season_to_date_features
from nfl.game_context_models import NflGameContext
from nfl.models import NflPlayer


@dataclass
class NflProjectionFeatures:
    canonical_player_id: str
    draftkings_player_id: str
    gsis_id: Optional[str]

    position: str
    team: str
    opponent: Optional[str]
    salary: int

    rolling: Dict[str, Optional[float]] = field(default_factory=dict)
    season_to_date: Dict[str, Optional[float]] = field(default_factory=dict)

    # None until real M7 odds credentials exist (see nfl/odds_provider.py) --
    # never blocks feature construction, per this module's docstring.
    game_context: Optional[dict] = None

    feature_as_of_season: int = 0
    feature_as_of_week: int = 0

    def to_dict(self) -> dict:
        return {
            "canonical_player_id": self.canonical_player_id,
            "draftkings_player_id": self.draftkings_player_id,
            "gsis_id": self.gsis_id,
            "position": self.position,
            "team": self.team,
            "opponent": self.opponent,
            "salary": self.salary,
            "rolling": self.rolling,
            "season_to_date": self.season_to_date,
            "game_context": self.game_context,
            "feature_as_of_season": self.feature_as_of_season,
            "feature_as_of_week": self.feature_as_of_week,
        }


@dataclass
class NflFeatureJoinResult:
    features: List[NflProjectionFeatures] = field(default_factory=list)
    gsis_resolved_ids: List[str] = field(default_factory=list)
    history_found_ids: List[str] = field(default_factory=list)
    resolved_no_history_ids: List[str] = field(default_factory=list)
    unresolved_ids: List[str] = field(default_factory=list)


def build_projection_features(
    players: List[NflPlayer],
    crosswalk: Dict[str, NflCrosswalkRow],
    usage_records: List[NflUsageRecord],
    game_contexts: List[NflGameContext],
    as_of_season: int, as_of_week: int,
) -> NflFeatureJoinResult:
    """`players` should be the live DK pool (offense + DST both fine to
    pass in -- DST rows are skipped here, never fabricated a usage
    row). `usage_records` should be one season's worth of real
    NflUsageRecord across every week strictly before `as_of_week`
    (compute_player_rolling_features/compute_season_to_date_features
    enforce the leakage boundary themselves regardless of what's
    passed in, but callers should not rely on that as their only
    safeguard -- see historical_nfl/usage_rolling.py's module
    docstring)."""
    games_by_id = {g.canonical_game_id: g for g in game_contexts}

    result = NflFeatureJoinResult()

    for player in players:
        if player.is_team_entity:
            continue  # DST -- separate path, see module docstring

        crosswalk_row = crosswalk.get(player.draftkings_player_id)
        gsis_id = crosswalk_row.gsis_id if crosswalk_row is not None else None

        if gsis_id is None:
            result.unresolved_ids.append(player.draftkings_player_id)
            continue

        result.gsis_resolved_ids.append(player.draftkings_player_id)

        rolling = compute_player_rolling_features(usage_records, gsis_id, as_of_week)
        season_to_date = compute_season_to_date_features(usage_records, gsis_id, as_of_week)

        has_history = rolling.get("weeks_of_history", 0) > 0
        if has_history:
            result.history_found_ids.append(player.draftkings_player_id)
        else:
            result.resolved_no_history_ids.append(player.draftkings_player_id)

        game = games_by_id.get(player.game_id)

        result.features.append(NflProjectionFeatures(
            canonical_player_id=crosswalk_row.canonical_player_id,
            draftkings_player_id=player.draftkings_player_id,
            gsis_id=gsis_id,
            position=player.position, team=player.team, opponent=player.opponent, salary=player.salary,
            rolling=rolling, season_to_date=season_to_date,
            game_context=game.to_dict() if game is not None else None,
            feature_as_of_season=as_of_season, feature_as_of_week=as_of_week,
        ))

    return result
