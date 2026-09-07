"""NFL M9 -- the real supervised-learning dataset schema and builder for
a future Big Money Native NFL projection model. DATASET ONLY -- nothing
here trains a model.

One row = one real player, one real game/week, features strictly from
before that week (historical_nfl/usage_rolling.py's leakage boundary),
target = that week's own real observed DraftKings points
(historical_nfl/dk_actual_scoring.py). Offense (QB/RB/WR/TE) and DST are
built as two separate row types -- DST has no GSIS identity and a
narrower, separate feature set (M8's dst_usage_models.py), never forced
into the offensive schema just to look rectangular.

SPLIT METHODOLOGY (Phase 12): deterministic, temporal, by week --
never a random shuffle across weeks (that would leak the season's
overall temporal regime, e.g. a late-season injury wave or weather
pattern, into "training" a model that's supposed to generalize
forward). Within one season:
  weeks 1-13  -> train
  weeks 14-15 -> validation
  weeks 16-18 -> test
Chosen to leave a real multi-week holdout at the end of the season
(where "does this generalize to games the model has never seen" is the
actual production question) while keeping enough training weeks for
rolling/season-to-date features to have real depth by mid-season.
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from historical_nfl.dk_actual_scoring import calculate_actual_dst_dk_points, calculate_actual_offense_dk_points
from historical_nfl.dst_rolling import compute_dst_rolling_features
from historical_nfl.dst_usage_models import NflDstUsageRecord
from historical_nfl.injury_status import build_injury_status_lookup
from historical_nfl.team_offense_models import NflTeamOffenseRecord
from historical_nfl.team_offense_rolling import compute_team_offense_rolling_features
from historical_nfl.usage_models import NflUsageRecord
from historical_nfl.usage_rolling import compute_player_rolling_features, compute_season_to_date_features

SCHEMA_VERSION = "nfl_projection_training_v1"
TARGET_SCORING_VERSION = "dk_nfl_classic_v1"  # matches config/nfl_dk_scoring.py

SPLIT_TRAIN = "train"
SPLIT_VALIDATION = "validation"
SPLIT_TEST = "test"


def assign_split(week: int) -> str:
    if week <= 13:
        return SPLIT_TRAIN
    if week <= 15:
        return SPLIT_VALIDATION
    return SPLIT_TEST


@dataclass
class NflOffenseTrainingRow:
    schema_version: str
    target_scoring_version: str

    season: int
    week: int
    game_id: Optional[str]
    gsis_id: str
    canonical_player_id: Optional[str]
    position: str
    team: str
    opponent: Optional[str]
    home_away: Optional[str]
    rest_days: Optional[int]

    feature_as_of_season: int
    feature_as_of_week: int
    rolling_features: Dict[str, Optional[float]]
    season_to_date_features: Dict[str, Optional[float]]

    has_prior_week: bool
    weeks_of_history: int

    salary: Optional[int]  # always None -- see module docstring, Phase 5 (no real historical DK salary source exists)
    injury_report_status: Optional[str]  # real report_status, PARTIAL signal -- see historical_nfl/injury_status.py

    target_dk_points: Optional[float]
    target_scored: bool

    split: str
    source_provenance: str = "nflverse_weekly_player_stats+snap_counts+play_by_play+schedules"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NflDstTrainingRow:
    schema_version: str
    target_scoring_version: str

    season: int
    week: int
    game_id: Optional[str]
    canonical_player_id: str  # "dst:{team}" -- never a fake GSIS id
    team: str
    opponent: Optional[str]
    home_away: Optional[str]

    feature_as_of_season: int
    feature_as_of_week: int
    rolling_features: Dict[str, Optional[float]]

    has_prior_week: bool
    weeks_of_history: int

    target_dk_points: Optional[float]
    target_scored: bool

    split: str
    source_provenance: str = "nflverse_team_stats+play_by_play+schedules"

    def to_dict(self) -> dict:
        return asdict(self)


def _home_away_and_rest(team: str, game_id: Optional[str], schedule_by_game: Dict[str, dict]) -> tuple:
    if not game_id or game_id not in schedule_by_game:
        return None, None
    sched = schedule_by_game[game_id]
    if team == sched.get("home_team"):
        return "home", sched.get("home_rest")
    if team == sched.get("away_team"):
        return "away", sched.get("away_rest")
    return None, None


def build_offense_training_rows(
    season: int, week: int,
    weekly_stats_rows: List[dict], all_usage_records: List[NflUsageRecord],
    schedule_rows: List[dict], injury_rows: List[dict],
) -> List[NflOffenseTrainingRow]:
    """One row per real offensive (QB/RB/WR/TE) weekly_stats row for
    `week`. Features are computed as-of `week` (i.e. from weeks strictly
    before it, via historical_nfl/usage_rolling.py's leakage boundary);
    target is `week`'s own real observed stat line."""
    schedule_by_game = {r["game_id"]: r for r in schedule_rows if r.get("game_id")}
    injury_lookup = build_injury_status_lookup(injury_rows, week)

    rows: List[NflOffenseTrainingRow] = []
    for stat_row in weekly_stats_rows:
        if stat_row.get("position") not in ("QB", "RB", "WR", "TE"):
            continue
        gsis_id = stat_row.get("player_id")
        if not gsis_id:
            continue

        team = stat_row.get("team")
        game_id = stat_row.get("game_id")
        home_away, rest_days = _home_away_and_rest(team, game_id, schedule_by_game)

        rolling = compute_player_rolling_features(all_usage_records, gsis_id, week)
        season_to_date = compute_season_to_date_features(all_usage_records, gsis_id, week)
        weeks_of_history = rolling.get("weeks_of_history", 0)

        target = calculate_actual_offense_dk_points(stat_row)

        rows.append(NflOffenseTrainingRow(
            schema_version=SCHEMA_VERSION, target_scoring_version=TARGET_SCORING_VERSION,
            season=season, week=week, game_id=game_id, gsis_id=gsis_id, canonical_player_id=None,
            position=stat_row.get("position"), team=team, opponent=stat_row.get("opponent_team"),
            home_away=home_away, rest_days=rest_days,
            feature_as_of_season=season, feature_as_of_week=week,
            rolling_features=rolling, season_to_date_features=season_to_date,
            has_prior_week=weeks_of_history > 0, weeks_of_history=weeks_of_history,
            salary=None, injury_report_status=injury_lookup.get(gsis_id),
            target_dk_points=target["dfs_points"], target_scored=target["scored"],
            split=assign_split(week),
        ))
    return rows


def build_dst_training_rows(
    season: int, week: int,
    team_stats_rows: List[dict], all_dst_records: List[NflDstUsageRecord],
    pbp_rows: List[dict], schedule_rows: List[dict],
    all_team_offense_records: Optional[List[NflTeamOffenseRecord]] = None,
) -> List[NflDstTrainingRow]:
    """NFL M11: `all_team_offense_records` (optional, backward compatible)
    attaches the row's UPCOMING OPPONENT's own trailing offensive form
    (opponent_* keys merged into rolling_features) -- see historical_nfl/
    team_offense_rolling.py's module docstring for why M10's DST model
    was missing this real, leakage-safe signal."""
    schedule_by_game = {r["game_id"]: r for r in schedule_rows if r.get("game_id")}
    scores_by_game = {r["game_id"]: (r.get("home_score"), r.get("away_score")) for r in schedule_rows if r.get("game_id")}
    by_team_stats = {r["team"]: r for r in team_stats_rows if r.get("team")}

    rows: List[NflDstTrainingRow] = []
    for team, stats_row in by_team_stats.items():
        game_id = stats_row.get("game_id")
        home_away, _ = _home_away_and_rest(team, game_id, schedule_by_game)
        opponent = stats_row.get("opponent_team")

        points_allowed = None
        if game_id in schedule_by_game and game_id in scores_by_game:
            sched = schedule_by_game[game_id]
            home_score, away_score = scores_by_game[game_id]
            if team == sched.get("home_team"):
                points_allowed = away_score
            elif team == sched.get("away_team"):
                points_allowed = home_score

        rolling = dict(compute_dst_rolling_features(all_dst_records, team, week))
        if all_team_offense_records is not None and opponent:
            rolling.update(compute_team_offense_rolling_features(all_team_offense_records, opponent, week))
        weeks_of_history = rolling.get("weeks_of_history", 0)

        target = calculate_actual_dst_dk_points(team, stats_row, pbp_rows, points_allowed)

        rows.append(NflDstTrainingRow(
            schema_version=SCHEMA_VERSION, target_scoring_version=TARGET_SCORING_VERSION,
            season=season, week=week, game_id=game_id, canonical_player_id=f"dst:{team}",
            team=team, opponent=opponent, home_away=home_away,
            feature_as_of_season=season, feature_as_of_week=week,
            rolling_features=rolling, has_prior_week=weeks_of_history > 0, weeks_of_history=weeks_of_history,
            target_dk_points=target["dfs_points"], target_scored=target["scored"],
            split=assign_split(week),
        ))
    return rows
