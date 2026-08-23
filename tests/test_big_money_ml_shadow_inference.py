"""Milestone 32.2B -- end-to-end shadow-inference orchestration tests.
Live fetchers are monkeypatched (zero network calls); a tiny frozen
model artifact and fake research_output/dfs_input/ml_projection_snapshots
directories are built under tmp_path for full isolation."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import big_money_ml.live_features as live_features
import big_money_ml.shadow_inference as shadow_inference
from big_money_ml.persistence import load_latest_ml_projection_snapshot
from big_money_ml.shadow_inference import run_ml_shadow_inference
from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
from historical_models.pitcher_v1.metadata import ModelMetadata
from historical_models.pitcher_v1.model import CANDIDATES, build_pipeline
from historical_models.pitcher_v1.persistence import save_all_artifacts


@pytest.fixture()
def frozen_artifact_dir(tmp_path):
    rng = np.random.default_rng(0)
    n = 20
    data = {col: rng.uniform(0, 1, size=n) for col in NUMERIC_FEATURE_COLUMNS}
    for col in CATEGORICAL_FEATURE_COLUMNS:
        # venue_id is int64 in the real warehouse (see shadow_inference.
        # _coerce_venue_id) -- match that dtype here so this fixture
        # exercises the same live/train type-consistency path production does.
        data[col] = rng.choice([15, 22], size=n) if col == "venue_id" else rng.choice(["A", "B"], size=n)
    X = pd.DataFrame(data)
    y = pd.Series(rng.uniform(0, 30, size=n))
    spec = next(c for c in CANDIDATES if c.name == "hist_gradient_boosting")
    pipeline = build_pipeline(spec, spec.param_grid[0])
    pipeline.fit(X, y)
    metadata = ModelMetadata(feature_list=FEATURE_COLUMNS, model_type="hist_gradient_boosting", hyperparameters={}, seed=42).to_dict()
    artifact_dir = tmp_path / "artifact"
    save_all_artifacts(artifact_dir, pipeline, metadata, FEATURE_COLUMNS, validation_metrics={"mae": 5.0})
    return artifact_dir


def _write_pool(root, date, players):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {"slate_date": date, "generated_at_utc": f"{date}T12:00:00Z", "player_count": len(players), "players": players}
    (folder / "dk_player_pool_20260822T120000.json").write_text(json.dumps(doc), encoding="utf-8")


def _write_games(root, date, games):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "games.json").write_text(json.dumps({"games": games}), encoding="utf-8")


def _pitcher_row(mlb_player_id, **overrides):
    row = {
        "dk_player_id": f"dk{mlb_player_id}", "name": f"Pitcher {mlb_player_id}", "team": "NYY", "player_type": "pitcher",
        "salary": 9000, "mlb_player_id": mlb_player_id, "opponent": "BOS", "game_id": "g1",
        "throwing_hand": "R", "eligibility_status": "STARTING_PITCHER", "optimizer_eligible": True,
    }
    row.update(overrides)
    return row


def _game(game_id="g1", home="NYY", away="BOS", start_utc=None, status="Scheduled"):
    # Default computed relative to "now" (never a hardcoded date) so
    # tests that don't pass their own now_utc stay correct regardless of
    # which real calendar moment the suite runs at -- a hardcoded future
    # start_utc eventually becomes the past.
    if start_utc is None:
        start_utc = (datetime.now(timezone.utc) + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"game_id": game_id, "home_team_abbr": home, "away_team_abbr": away, "venue_id": 15, "game_datetime_utc": start_utc, "status": status}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(live_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_features, "fetch_person", lambda player_id: {"batSide": {"code": "R"}, "pitchHand": {"code": "R"}})
    monkeypatch.setattr(shadow_inference, "build_live_statcast_buffer", lambda as_of_date: live_features.LiveStatcastBuffer())


def test_coerce_venue_id_matches_training_dtype():
    """Regression test: research_output/<date>/games.json serializes
    venue_id as a JSON string ("32"), but the model trained on it as an
    int64 warehouse column -- must be coerced, not passed through raw."""
    from big_money_ml.shadow_inference import _coerce_venue_id

    assert _coerce_venue_id("32") == 32
    assert isinstance(_coerce_venue_id("32"), int)
    assert _coerce_venue_id(32) == 32
    assert _coerce_venue_id(None) is None
    assert _coerce_venue_id("") is None
    assert _coerce_venue_id("not-a-number") is None


def test_generates_projection_for_eligible_starting_pitcher(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_pitcher_row("1")])
    _write_games(research_root, "2026-08-22", [_game()])

    from datetime import datetime, timezone
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)

    doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir, now_utc=now,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 1
    assert doc.players[0].projection_status == "LIVE_PREGAME"
    assert doc.players[0].projection is not None
    assert doc.players[0].feature_timestamp is not None
    assert doc.players[0].feature_timestamp < doc.players[0].game_scheduled_start_utc  # pregame timestamp requirement


def test_relief_pitcher_never_projected(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_pitcher_row("2", eligibility_status="RELIEF_PITCHER", optimizer_eligible=False)])
    _write_games(research_root, "2026-08-22", [_game()])

    doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_eligible_pitcher_count == 0
    assert doc.players == []


def test_post_start_inference_blocked_and_no_backfill(tmp_path, frozen_artifact_dir):
    from datetime import datetime, timezone

    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-21", [_pitcher_row("3")])
    _write_games(research_root, "2026-08-21", [_game(start_utc="2026-08-21T23:00:00Z")])

    now_after_start = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)  # well after the game started
    doc = run_ml_shadow_inference(
        "2026-08-21", artifact_dir=frozen_artifact_dir, now_utc=now_after_start,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 0
    assert doc.ml_projections_missing == 1
    assert doc.players[0].projection_status == "MISSING"
    assert "NO VALID PREGAME ML PROJECTION" in doc.players[0].warnings


def test_frozen_pregame_snapshot_is_preserved_after_game_starts(tmp_path, frozen_artifact_dir):
    from datetime import datetime, timezone

    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_pitcher_row("4")])
    _write_games(research_root, "2026-08-22", [_game(start_utc="2026-08-22T23:00:00Z")])

    before_start = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    first_doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir, now_utc=before_start,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    original_projection = first_doc.players[0].projection
    original_timestamp = first_doc.players[0].feature_timestamp
    assert first_doc.players[0].projection_status == "LIVE_PREGAME"

    after_start = datetime(2026, 8, 23, 2, 0, tzinfo=timezone.utc)  # after the game has started
    second_doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir, now_utc=after_start,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert second_doc.players[0].projection_status == "PREGAME_FROZEN"
    assert second_doc.players[0].projection == original_projection  # never recomputed
    assert second_doc.players[0].feature_timestamp == original_timestamp  # never updated with post-lock data


def test_unmatched_pitcher_excluded_from_inference(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    row = _pitcher_row("5", eligibility_status="UNMATCHED", optimizer_eligible=False)
    row["mlb_player_id"] = None
    _write_pool(dfs_root, "2026-08-22", [row])
    _write_games(research_root, "2026-08-22", [_game()])

    doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.players == []


def test_snapshot_persisted_and_reloadable(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_pitcher_row("6")])
    _write_games(research_root, "2026-08-22", [_game()])

    run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    reloaded = load_latest_ml_projection_snapshot("2026-08-22", output_root=ml_root)
    assert reloaded is not None
    assert reloaded["players"][0]["player_id"] == "6"


def test_identity_keyed_by_mlb_player_id_and_game_id_protects_against_same_name(tmp_path, frozen_artifact_dir):
    """Two different pitchers sharing a name, on different teams/games,
    must never be conflated -- identity is mlb_player_id + game_id, never name."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [
        _pitcher_row("7", name="Chris Sale", team="ATL", opponent="NYM", game_id="gA"),
        _pitcher_row("8", name="Chris Sale", team="BOS", opponent="TB", game_id="gB"),
    ])
    _write_games(research_root, "2026-08-22", [
        _game(game_id="gA", home="ATL", away="NYM"), _game(game_id="gB", home="BOS", away="TB"),
    ])

    doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 2
    ids = {(p.player_id, p.game_id, p.team) for p in doc.players}
    assert ids == {("7", "gA", "ATL"), ("8", "gB", "BOS")}


def test_no_dk_pool_returns_empty_document_not_an_error(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_eligible_pitcher_count == 0
    assert doc.players == []


def test_actual_dk_points_never_enters_the_prediction_features(tmp_path, frozen_artifact_dir, monkeypatch):
    """Even if a caller somehow injected actual_dk_points into the live
    feature dict, the leakage guard inside shadow_inference must reject
    it before the model ever sees it."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_pitcher_row("9")])
    _write_games(research_root, "2026-08-22", [_game()])

    original = shadow_inference.build_live_pregame_pitcher_features

    def tampered(**kwargs):
        result = original(**kwargs)
        result.features["actual_dk_points"] = 999.0
        return result

    monkeypatch.setattr(shadow_inference, "build_live_pregame_pitcher_features", tampered)

    doc = run_ml_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.players[0].projection_status == "INVALID_FEATURE_PARITY"
    assert doc.players[0].projection is None
