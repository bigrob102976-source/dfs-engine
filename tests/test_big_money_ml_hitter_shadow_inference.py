"""Milestone 32.3B -- end-to-end HITTER shadow-inference orchestration
tests. Live fetchers are monkeypatched (zero network calls); a tiny
frozen model artifact and fake research_output/dfs_input/
ml_projection_snapshots directories are built under tmp_path for full
isolation. Mirrors tests/test_big_money_ml_shadow_inference.py exactly."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import big_money_ml.hitter_shadow_inference as hitter_shadow_inference
import big_money_ml.live_hitter_features as live_hitter_features
from big_money_ml.hitter_shadow_inference import run_ml_hitter_shadow_inference
from big_money_ml.live_features import LiveStatcastBuffer
from big_money_ml.persistence import load_latest_ml_hitter_projection_snapshot
from historical_models.hitter_v1.features import AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS, AFTER_LINEUP_FEATURE_COLUMNS, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS
from historical_models.hitter_v1.metadata import ModelMetadata
from historical_models.hitter_v1.model import CANDIDATES, build_pipeline
from historical_models.hitter_v1.persistence import save_all_artifacts


@pytest.fixture()
def frozen_artifact_dir(tmp_path):
    rng = np.random.default_rng(0)
    n = 20
    data = {col: rng.uniform(0, 1, size=n) for col in AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS}
    for col in AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice([15, 22], size=n) if col == "venue_id" else rng.choice(["A", "B"], size=n)
    X = pd.DataFrame(data)
    y = pd.Series(rng.uniform(0, 30, size=n))
    spec = next(c for c in CANDIDATES if c.name == "hist_gradient_boosting")
    pipeline = build_pipeline(spec, spec.param_grid[0], AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS, AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS)
    pipeline.fit(X, y)
    metadata = ModelMetadata(
        feature_availability_class="AFTER_LINEUP", feature_list=AFTER_LINEUP_FEATURE_COLUMNS,
        model_type="hist_gradient_boosting", hyperparameters={}, seed=42,
    ).to_dict()
    artifact_dir = tmp_path / "artifact"
    save_all_artifacts(artifact_dir, pipeline, metadata, AFTER_LINEUP_FEATURE_COLUMNS, validation_metrics={"mae": 5.0})
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


def _write_pitchers(root, date, pitchers):
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pitchers.json").write_text(json.dumps(pitchers), encoding="utf-8")


def _hitter_row(mlb_player_id, **overrides):
    row = {
        "dk_player_id": f"dk{mlb_player_id}", "name": f"Hitter {mlb_player_id}", "team": "NYY", "player_type": "hitter",
        "salary": 4500, "mlb_player_id": mlb_player_id, "opponent": "BOS", "game_id": "g1", "batting_order": 3,
        "batting_hand": "R", "eligibility_status": "STARTING_HITTER", "optimizer_eligible": True,
    }
    row.update(overrides)
    return row


def _probable_pitcher(mlb_player_id, team_abbr="BOS", game_id="g1", throws="R"):
    return {"player_id": mlb_player_id, "name": f"Pitcher {mlb_player_id}", "team_abbr": team_abbr, "opponent_team_abbr": "NYY", "game_id": game_id, "throws": throws, "status": "probable"}


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
    monkeypatch.setattr(live_hitter_features, "fetch_batter_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_pitcher_game_log", lambda player_id, season: None)
    monkeypatch.setattr(live_hitter_features, "fetch_person", lambda player_id: {"batSide": {"code": "R"}, "pitchHand": {"code": "R"}})
    monkeypatch.setattr(hitter_shadow_inference, "build_live_statcast_buffer", lambda as_of_date: LiveStatcastBuffer())


def test_generates_projection_for_eligible_starting_hitter_with_confirmed_opponent(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("1")])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    from datetime import datetime, timezone
    now = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir, now_utc=now,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 1
    assert doc.players[0].projection_status == "LIVE_PREGAME"
    assert doc.players[0].projection is not None
    assert doc.players[0].batting_order == 3
    assert doc.players[0].feature_timestamp is not None
    assert doc.players[0].feature_timestamp < doc.players[0].game_scheduled_start_utc  # pregame timestamp requirement


def test_bench_hitter_never_projected(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("2", eligibility_status="BENCH", optimizer_eligible=False)])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_eligible_hitter_count == 0
    assert doc.players == []


def test_no_confirmed_opposing_starter_yields_no_valid_live_ml_projection(tmp_path, frozen_artifact_dir):
    """AFTER_LINEUP gate: a hitter whose opponent has no probable
    starter resolvable in pitchers.json must NOT get a fabricated
    projection -- must report NO VALID LIVE ML PROJECTION."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("3")])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [])  # no probable starters at all

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 0
    assert doc.ml_projections_missing == 1
    assert doc.players[0].projection_status == "MISSING"
    assert any("NO VALID LIVE ML PROJECTION" in w for w in doc.players[0].warnings)


def test_missing_batting_order_yields_no_valid_live_ml_projection(tmp_path, frozen_artifact_dir):
    """AFTER_LINEUP gate: even with a confirmed opposing starter, a
    hitter with no confirmed batting_order must not get a projection."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("4", batting_order=None)])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 0
    assert doc.players[0].projection_status == "MISSING"
    assert any("NO VALID LIVE ML PROJECTION" in w for w in doc.players[0].warnings)


def test_post_start_inference_blocked_and_no_backfill(tmp_path, frozen_artifact_dir):
    from datetime import datetime, timezone

    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-21", [_hitter_row("5")])
    _write_games(research_root, "2026-08-21", [_game(start_utc="2026-08-21T23:00:00Z")])
    _write_pitchers(research_root, "2026-08-21", [_probable_pitcher("999")])

    now_after_start = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)  # well after the game started
    doc = run_ml_hitter_shadow_inference(
        "2026-08-21", artifact_dir=frozen_artifact_dir, now_utc=now_after_start,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 0
    assert doc.ml_projections_missing == 1
    assert doc.players[0].projection_status == "MISSING"
    assert "NO VALID LIVE ML PROJECTION" in doc.players[0].warnings


def test_frozen_pregame_snapshot_is_preserved_after_game_starts(tmp_path, frozen_artifact_dir):
    from datetime import datetime, timezone

    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("6")])
    _write_games(research_root, "2026-08-22", [_game(start_utc="2026-08-22T23:00:00Z")])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    before_start = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    first_doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir, now_utc=before_start,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    original_projection = first_doc.players[0].projection
    original_timestamp = first_doc.players[0].feature_timestamp
    assert first_doc.players[0].projection_status == "LIVE_PREGAME"

    after_start = datetime(2026, 8, 23, 2, 0, tzinfo=timezone.utc)  # after the game has started
    second_doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir, now_utc=after_start,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert second_doc.players[0].projection_status == "PREGAME_FROZEN"
    assert second_doc.players[0].projection == original_projection  # never recomputed
    assert second_doc.players[0].feature_timestamp == original_timestamp  # never updated with post-lock data


def test_unmatched_hitter_excluded_from_inference(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    row = _hitter_row("7", eligibility_status="UNMATCHED", optimizer_eligible=False)
    row["mlb_player_id"] = None
    _write_pool(dfs_root, "2026-08-22", [row])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.players == []


def test_snapshot_persisted_and_reloadable(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("8")])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    reloaded = load_latest_ml_hitter_projection_snapshot("2026-08-22", output_root=ml_root)
    assert reloaded is not None
    assert reloaded["players"][0]["player_id"] == "8"


def test_identity_keyed_by_mlb_player_id_and_game_id_protects_against_same_name(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [
        _hitter_row("9", name="Will Smith", team="ATL", opponent="NYM", game_id="gA"),
        _hitter_row("10", name="Will Smith", team="BOS", opponent="TB", game_id="gB"),
    ])
    _write_games(research_root, "2026-08-22", [
        _game(game_id="gA", home="ATL", away="NYM"), _game(game_id="gB", home="BOS", away="TB"),
    ])
    _write_pitchers(research_root, "2026-08-22", [
        _probable_pitcher("991", team_abbr="NYM", game_id="gA"), _probable_pitcher("992", team_abbr="TB", game_id="gB"),
    ])

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_projections_generated == 2
    ids = {(p.player_id, p.game_id, p.team) for p in doc.players}
    assert ids == {("9", "gA", "ATL"), ("10", "gB", "BOS")}


def test_no_dk_pool_returns_empty_document_not_an_error(tmp_path, frozen_artifact_dir):
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.ml_eligible_hitter_count == 0
    assert doc.players == []


def test_actual_dk_points_never_enters_the_prediction_features(tmp_path, frozen_artifact_dir, monkeypatch):
    """Even if a caller somehow injected actual_dk_points into the live
    feature dict, the leakage guard inside hitter_shadow_inference must
    reject it before the model ever sees it."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("11")])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    original = hitter_shadow_inference.build_live_pregame_hitter_features

    def tampered(**kwargs):
        result = original(**kwargs)
        result.features["actual_dk_points"] = 999.0
        return result

    monkeypatch.setattr(hitter_shadow_inference, "build_live_pregame_hitter_features", tampered)

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
    )
    assert doc.players[0].projection_status == "INVALID_FEATURE_PARITY"
    assert doc.players[0].projection is None


def test_frozen_artifact_must_be_after_lineup_class(tmp_path, monkeypatch):
    """The live hitter path only supports the approved AFTER_LINEUP
    artifact -- an artifact frozen as ALWAYS_PREGAME must be refused,
    never silently run."""
    rng = np.random.default_rng(0)
    n = 20
    from historical_models.hitter_v1.features import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS
    data = {col: rng.uniform(0, 1, size=n) for col in NUMERIC_FEATURE_COLUMNS}
    for col in CATEGORICAL_FEATURE_COLUMNS:
        data[col] = rng.choice([15, 22], size=n) if col == "venue_id" else rng.choice(["A", "B"], size=n)
    X = pd.DataFrame(data)
    y = pd.Series(rng.uniform(0, 30, size=n))
    spec = next(c for c in CANDIDATES if c.name == "ridge")
    from historical_models.hitter_v1.features import ALWAYS_PREGAME_FEATURE_COLUMNS
    pipeline = build_pipeline(spec, {"alpha": 1.0}, NUMERIC_FEATURE_COLUMNS, CATEGORICAL_FEATURE_COLUMNS)
    pipeline.fit(X, y)
    metadata = ModelMetadata(
        feature_availability_class="ALWAYS_PREGAME", feature_list=ALWAYS_PREGAME_FEATURE_COLUMNS,
        model_type="ridge", hyperparameters={"alpha": 1.0}, seed=42,
    ).to_dict()
    artifact_dir = tmp_path / "artifact"
    save_all_artifacts(artifact_dir, pipeline, metadata, ALWAYS_PREGAME_FEATURE_COLUMNS, validation_metrics={"mae": 5.0})

    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("12")])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    with pytest.raises(hitter_shadow_inference.HitterShadowInferenceError, match="AFTER_LINEUP"):
        run_ml_hitter_shadow_inference(
            "2026-08-22", artifact_dir=artifact_dir,
            dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
        )


# ---------------------------------------------------------------------------
# M32.7A -- real weather threaded from a persisted SlateEnvironmentReport
# into the live hitter feature builder via game_id.
# ---------------------------------------------------------------------------


def _reading(temperature_f=72.0, wind_speed_mph=8.0, wind_direction_degrees=180.0, precipitation_amount_mm=0.0, humidity_percent=55.0):
    return {
        "temperature_f": temperature_f, "humidity_percent": humidity_percent, "wind_speed_mph": wind_speed_mph,
        "wind_direction_degrees": wind_direction_degrees, "feels_like_f": None, "rain_percent": None,
        "air_density": None, "precipitation_probability_percent": None,
        "precipitation_amount_mm": precipitation_amount_mm, "weather_code": None, "wind_gusts_mph": None,
    }


def _weather_snapshot(game_id, is_mock=False, roof_status="open", first_pitch=None, current=None):
    return {
        "game_id": game_id, "provider_name": "open_meteo", "is_mock": is_mock,
        "retrieved_at": "2026-08-22T10:00:00Z", "roof_status": roof_status,
        "delay_risk_percent": None, "postponement_risk_percent": None,
        "current": current or _reading(temperature_f=999.0),  # decoy -- must never be read
        "first_pitch": first_pitch if first_pitch is not None else _reading(),
        "mid_game": _reading(), "late_game": _reading(),
        "weather_risk_percent": None, "weather_status": None,
    }


def _write_environment_report(root, date, games):
    """games: list of (game_id, weather_snapshot_dict_or_None)."""
    folder = root / date
    folder.mkdir(parents=True, exist_ok=True)
    doc = {
        "slate_date": date, "generated_at": f"{date}T09:00:00Z", "engine_version": "test",
        "games": [
            {
                "game_id": game_id, "home_team": "NYY", "away_team": "BOS", "game_datetime_utc": None,
                "venue_name": None, "environment_score": {"overall": 50, "pitcher": 50, "hitter": 50, "stack": 50},
                "summary": {"headline": "", "bullet_points": []},
                "future_adjustment_preview": {"weather_points": None, "vegas_points": None, "bullpen_points": None, "enabled": False},
                "weather": weather, "weather_analysis": None, "vegas": None, "ballpark": None, "umpire": None,
                "bullpen_home": None, "bullpen_away": None, "travel_home": None, "travel_away": None,
                "mlb_game_status": None, "game_status": "UNKNOWN", "vegas_live": None,
            }
            for game_id, weather in games
        ],
        "vegas_slate_analysis": None, "warnings": [],
    }
    (folder / "environment_20260822T090000.json").write_text(json.dumps(doc), encoding="utf-8")


def test_real_weather_from_environment_snapshot_reaches_the_live_feature_builder(tmp_path, frozen_artifact_dir, monkeypatch):
    """End-to-end M32.7A proof: a real, persisted SlateEnvironmentReport's
    weather for this hitter's own game_id is passed into
    build_live_pregame_hitter_features -- not omitted, not fabricated."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    env_root = tmp_path / "env_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("20", game_id="g1")])
    _write_games(research_root, "2026-08-22", [_game(game_id="g1")])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999", game_id="g1")])
    snapshot = _weather_snapshot("g1", first_pitch=_reading(temperature_f=81.0, wind_speed_mph=12.5))
    _write_environment_report(env_root, "2026-08-22", [("g1", snapshot)])

    captured = {}
    original = hitter_shadow_inference.build_live_pregame_hitter_features

    def spy(**kwargs):
        captured["weather_snapshot"] = kwargs.get("weather_snapshot")
        return original(**kwargs)

    monkeypatch.setattr(hitter_shadow_inference, "build_live_pregame_hitter_features", spy)

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
        environment_snapshot_root=env_root,
    )
    assert captured["weather_snapshot"] == snapshot
    assert doc.players[0].projection_status == "LIVE_PREGAME"


def test_weather_matched_by_game_id_not_leaked_across_games(tmp_path, frozen_artifact_dir, monkeypatch):
    """Two hitters in two different games must each get their OWN
    game's weather, never the other game's."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    env_root = tmp_path / "env_snap"
    _write_pool(dfs_root, "2026-08-22", [
        _hitter_row("21", team="ATL", opponent="NYM", game_id="gA"),
        _hitter_row("22", team="BOS", opponent="TB", game_id="gB"),
    ])
    _write_games(research_root, "2026-08-22", [
        _game(game_id="gA", home="ATL", away="NYM"), _game(game_id="gB", home="BOS", away="TB"),
    ])
    _write_pitchers(research_root, "2026-08-22", [
        _probable_pitcher("991", team_abbr="NYM", game_id="gA"), _probable_pitcher("992", team_abbr="TB", game_id="gB"),
    ])
    snapshot_a = _weather_snapshot("gA", first_pitch=_reading(temperature_f=60.0))
    snapshot_b = _weather_snapshot("gB", first_pitch=_reading(temperature_f=95.0))
    _write_environment_report(env_root, "2026-08-22", [("gA", snapshot_a), ("gB", snapshot_b)])

    captured = {}
    original = hitter_shadow_inference.build_live_pregame_hitter_features

    def spy(**kwargs):
        captured[kwargs["player_id"]] = kwargs.get("weather_snapshot")
        return original(**kwargs)

    monkeypatch.setattr(hitter_shadow_inference, "build_live_pregame_hitter_features", spy)

    run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
        environment_snapshot_root=env_root,
    )
    assert captured["21"]["first_pitch"]["temperature_f"] == 60.0
    assert captured["22"]["first_pitch"]["temperature_f"] == 95.0


def test_no_environment_snapshot_yet_still_generates_with_honest_missing_weather(tmp_path, frozen_artifact_dir):
    """No environment_snapshot_root data at all for this slate must not
    block inference -- weather stays honestly missing (weather_available
    False), same behavior as before M32.7A, never a hard failure."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    env_root = tmp_path / "env_snap"  # never written -- no environment snapshot exists
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("23")])
    _write_games(research_root, "2026-08-22", [_game()])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999")])

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
        environment_snapshot_root=env_root,
    )
    assert doc.players[0].projection_status == "LIVE_PREGAME"
    assert doc.players[0].projection is not None


def test_mock_weather_snapshot_treated_as_unavailable_not_wired_into_inference(tmp_path, frozen_artifact_dir, monkeypatch):
    """A game whose only persisted weather is from a mock provider
    (is_mock=True) must reach the feature builder as unavailable, not as
    if it were real -- the mapping itself (_map_weather_features) already
    unit-tests this; this proves the orchestration layer does not
    special-case or filter it out before passing it along, either."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    env_root = tmp_path / "env_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("24", game_id="g1")])
    _write_games(research_root, "2026-08-22", [_game(game_id="g1")])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999", game_id="g1")])
    mock_snapshot = _weather_snapshot("g1", is_mock=True)
    _write_environment_report(env_root, "2026-08-22", [("g1", mock_snapshot)])

    captured = {}
    original = hitter_shadow_inference.build_live_pregame_hitter_features

    def spy(**kwargs):
        captured["weather_snapshot"] = kwargs.get("weather_snapshot")
        return original(**kwargs)

    monkeypatch.setattr(hitter_shadow_inference, "build_live_pregame_hitter_features", spy)

    run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
        environment_snapshot_root=env_root,
    )
    assert captured["weather_snapshot"]["is_mock"] is True  # passed through as-is
    assert live_hitter_features._map_weather_features(captured["weather_snapshot"])["weather_available"] is False


def test_weather_influenced_snapshot_still_persists_and_reloads(tmp_path, frozen_artifact_dir):
    """ML snapshot persistence (save/reload round-trip) still works once
    real weather is flowing through the feature vector -- no new field
    breaks the existing MLHitterProjectionDocument serialization."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    env_root = tmp_path / "env_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("25", game_id="g1")])
    _write_games(research_root, "2026-08-22", [_game(game_id="g1")])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999", game_id="g1")])
    _write_environment_report(env_root, "2026-08-22", [("g1", _weather_snapshot("g1"))])

    run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
        environment_snapshot_root=env_root,
    )
    reloaded = load_latest_ml_hitter_projection_snapshot("2026-08-22", output_root=ml_root)
    assert reloaded is not None
    assert reloaded["players"][0]["player_id"] == "25"
    assert reloaded["players"][0]["projection_status"] == "LIVE_PREGAME"


def test_weather_does_not_affect_pregame_timestamp_safety(tmp_path, frozen_artifact_dir):
    """Weather threading must not change the existing pregame-timestamp
    guarantee: feature_timestamp is still strictly before game start."""
    dfs_root, research_root, ml_root = tmp_path / "dfs_input", tmp_path / "research_output", tmp_path / "ml_snap"
    env_root = tmp_path / "env_snap"
    _write_pool(dfs_root, "2026-08-22", [_hitter_row("26", game_id="g1")])
    _write_games(research_root, "2026-08-22", [_game(game_id="g1")])
    _write_pitchers(research_root, "2026-08-22", [_probable_pitcher("999", game_id="g1")])
    _write_environment_report(env_root, "2026-08-22", [("g1", _weather_snapshot("g1"))])

    doc = run_ml_hitter_shadow_inference(
        "2026-08-22", artifact_dir=frozen_artifact_dir,
        dfs_input_root=dfs_root, research_output_root=str(research_root), ml_projection_root=ml_root,
        environment_snapshot_root=env_root,
    )
    assert doc.players[0].feature_timestamp < doc.players[0].game_scheduled_start_utc
    assert not any("not strictly before game start" in w for w in doc.players[0].warnings)
