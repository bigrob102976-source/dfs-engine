"""NFL M8 -- targeted tests for nfl/projection_features.py's DK identity
join and feature-record construction. Synthetic fixtures, no network."""

from historical_nfl.identity_models import NflCrosswalkRow
from historical_nfl.usage_models import NflUsageRecord
from nfl.game_context_models import NflGameContext
from nfl.models import NflPlayer
from nfl.projection_features import build_projection_features

DG_ID = 151307
DATE = "2026-09-13"


def _player(pid, position="WR", game_id="100", is_team_entity=False, team="PHI"):
    return NflPlayer(
        draftkings_player_id=pid, draftkings_dk_id=f"dk{pid}", draftable_ids=[f"d{pid}"], name=f"Player {pid}",
        first_name=None, last_name=None, is_team_entity=is_team_entity, position=position, roster_slots=[position],
        team=team, opponent="DAL", game_id=game_id, game_description="DAL @ PHI", game_start_time="2026-09-13T17:00:00Z",
        salary=6000, status="None", injury_status=None, draft_group_id=DG_ID, slate_date=DATE, slate_name="Featured",
        source="draftkings_unofficial", source_provenance="DRAFTKINGS_UNOFFICIAL_LIVE",
    )


def _crosswalk_row(dk_id, gsis_id):
    return NflCrosswalkRow(canonical_player_id=f"gsis:{gsis_id}", draftkings_player_id=dk_id, gsis_id=gsis_id, team="PHI", position="WR")


def _usage(gsis_id, week, targets=8):
    return NflUsageRecord(canonical_player_id=f"gsis:{gsis_id}", gsis_id=gsis_id, season=2025, week=week, game_id="g1", team="PHI", opponent="DAL", position="WR", targets=targets)


def test_dst_players_are_skipped_never_get_a_fake_gsis_row():
    players = [_player("dst1", is_team_entity=True)]
    result = build_projection_features(players, {}, [], [], as_of_season=2025, as_of_week=6)
    assert result.features == []
    assert result.unresolved_ids == []


def test_unresolved_when_no_crosswalk_row():
    players = [_player("1")]
    result = build_projection_features(players, {}, [], [], as_of_season=2025, as_of_week=6)
    assert result.unresolved_ids == ["1"]
    assert result.features == []


def test_resolved_no_history_when_gsis_found_but_no_usage_records():
    players = [_player("1")]
    crosswalk = {"1": _crosswalk_row("1", "00-1")}
    result = build_projection_features(players, crosswalk, [], [], as_of_season=2025, as_of_week=6)
    assert result.gsis_resolved_ids == ["1"]
    assert result.resolved_no_history_ids == ["1"]
    assert result.history_found_ids == []
    assert len(result.features) == 1
    assert result.features[0].gsis_id == "00-1"


def test_history_found_when_usage_records_exist_before_as_of_week():
    players = [_player("1")]
    crosswalk = {"1": _crosswalk_row("1", "00-1")}
    usage = [_usage("00-1", week=5, targets=8)]
    result = build_projection_features(players, crosswalk, usage, [], as_of_season=2025, as_of_week=6)
    assert result.history_found_ids == ["1"]
    feature = result.features[0]
    assert feature.rolling["targets_mean_last1"] == 8.0


def test_leakage_respected_through_the_join():
    """Usage from the as_of week itself must not leak through even
    though it's present in the input list."""
    players = [_player("1")]
    crosswalk = {"1": _crosswalk_row("1", "00-1")}
    usage = [_usage("00-1", week=6, targets=999)]  # as_of_week itself
    result = build_projection_features(players, crosswalk, usage, [], as_of_season=2025, as_of_week=6)
    assert result.resolved_no_history_ids == ["1"]  # week 6 doesn't count as history for itself
    assert result.features[0].rolling["weeks_of_history"] == 0


def test_game_context_attached_when_available():
    players = [_player("1", game_id="100")]
    crosswalk = {"1": _crosswalk_row("1", "00-1")}
    game = NflGameContext(sport="NFL", draft_group_id=DG_ID, slate_date=DATE, canonical_game_id="100", draftkings_game_id="100", home_team="PHI", away_team="DAL", spread=-2.5, total=48.5)
    result = build_projection_features(players, crosswalk, [], [game], as_of_season=2025, as_of_week=6)
    assert result.features[0].game_context is not None
    assert result.features[0].game_context["spread"] == -2.5


def test_game_context_none_when_not_matched():
    players = [_player("1", game_id="999")]
    crosswalk = {"1": _crosswalk_row("1", "00-1")}
    result = build_projection_features(players, crosswalk, [], [], as_of_season=2025, as_of_week=6)
    assert result.features[0].game_context is None


def test_feature_as_of_recorded_on_every_record():
    players = [_player("1")]
    crosswalk = {"1": _crosswalk_row("1", "00-1")}
    result = build_projection_features(players, crosswalk, [], [], as_of_season=2025, as_of_week=6)
    assert result.features[0].feature_as_of_season == 2025
    assert result.features[0].feature_as_of_week == 6
