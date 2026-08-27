"""Milestone 33.3/33.4: standalone Python runtime smoke test -- NOT a
pytest file, deliberately runnable with zero test-framework dependency
(only requirements.txt, never requirements-dev.txt) so it can double as
a container/CI "is this environment actually usable" gate before
serving real traffic, independent of whatever the full test suite
validates.

Checks, in order, each printing PASS/FAIL and continuing (never stopping
early) so one failure doesn't hide a second, unrelated one:

  1. Every requirements.txt package imports cleanly.
  2. The real trained PITCHER model loads and produces a real
     prediction (proves joblib/scikit-learn pickle compatibility with
     the pinned versions -- see requirements.txt's own docstring on why
     this is version-sensitive).
  3. The real trained HITTER model loads and produces a real
     prediction -- checked separately from the pitcher model even
     though both share the exact same load_model() implementation
     (confirmed by identity check, Milestone 33.4), because a
     model-artifact problem (a missing/corrupt file, a genuinely
     divergent schema) is per-artifact, not per-function.
  4. OR-Tools CP-SAT can solve a trivial toy problem (proves the solver
     backend itself works in this environment, independent of the whole
     DFS pipeline).
  5. The optimizer CLI entry point (scripts/optimize_dk_lineups.py)
     starts and completes a real --validate-only run against a tiny
     synthetic pool file -- proves the full CLI argument-parsing and
     coverage-diagnostics path is reachable as a subprocess, the same
     way lib/orchestrator/pythonRunner.ts invokes it. Synthetic pool
     data only (never a real slate) -- this validates the CLI mechanism,
     not any projection.
  6. The artifact storage abstraction resolves to LocalArtifactStorage in
     a non-production environment with no OBJECT_STORAGE_* configured
     (proves the storage import surface -- boto3 included -- is sound;
     never touches a real network).

Usage:
    python scripts/smoke_test_runtime.py

Exit code 0 only if every check passes.
"""

import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

RESULTS = []


def check(name):
    def decorator(fn):
        try:
            fn()
            RESULTS.append((name, True, None))
        except Exception as exc:  # noqa: BLE001 -- a smoke test must report every kind of failure, not just expected ones
            RESULTS.append((name, False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))
        return fn

    return decorator


@check("import every requirements.txt package")
def _check_imports():
    import boto3  # noqa: F401
    import joblib  # noqa: F401
    import numpy  # noqa: F401
    import pandas  # noqa: F401
    import pyarrow  # noqa: F401
    import scipy  # noqa: F401
    import sklearn  # noqa: F401
    from ortools.sat.python import cp_model  # noqa: F401


@check("pitcher model (v1) loads and runs inference")
def _check_pitcher_model_inference():
    from historical_models.pitcher_v1.persistence import load_model
    from historical_models.pitcher_v1.config import DEFAULT_ARTIFACT_DIR
    import pandas as pd
    from historical_models.pitcher_v1.features import CATEGORICAL_FEATURE_COLUMNS, NUMERIC_FEATURE_COLUMNS

    model = load_model(DEFAULT_ARTIFACT_DIR)
    row = {col: 0.0 for col in NUMERIC_FEATURE_COLUMNS}
    for col in CATEGORICAL_FEATURE_COLUMNS:
        row[col] = "UNKNOWN"
    prediction = model.predict(pd.DataFrame([row]))
    assert len(prediction) == 1, f"expected 1 prediction, got {len(prediction)}"
    assert prediction[0] == prediction[0], "prediction is NaN"  # NaN != NaN


@check("hitter model (v1) loads and runs inference")
def _check_hitter_model_inference():
    from historical_models.hitter_v1.persistence import load_model
    from historical_models.hitter_v1.config import DEFAULT_ARTIFACT_DIR
    import pandas as pd
    # The trained hitter_v1 pipeline was fit on the richer AFTER_LINEUP_*
    # feature set (adds opposing-pitcher/batting-order columns available
    # once a lineup posts), not the plainer ALWAYS_PREGAME
    # NUMERIC_FEATURE_COLUMNS/CATEGORICAL_FEATURE_COLUMNS -- confirmed by
    # running this check and reading the exact "columns are missing"
    # error scikit-learn's ColumnTransformer raises when given the wrong
    # set (see historical_models/hitter_v1/features.py's own
    # AFTER_LINEUP_NUMERIC_ADDITIONS / AFTER_LINEUP_CATEGORICAL_ADDITIONS).
    from historical_models.hitter_v1.features import AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS, AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS

    model = load_model(DEFAULT_ARTIFACT_DIR)
    row = {col: 0.0 for col in AFTER_LINEUP_NUMERIC_FEATURE_COLUMNS}
    for col in AFTER_LINEUP_CATEGORICAL_FEATURE_COLUMNS:
        row[col] = "UNKNOWN"
    prediction = model.predict(pd.DataFrame([row]))
    assert len(prediction) == 1, f"expected 1 prediction, got {len(prediction)}"
    assert prediction[0] == prediction[0], "prediction is NaN"  # NaN != NaN


@check("OR-Tools CP-SAT solves a trivial toy problem")
def _check_ortools():
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    x = model.NewIntVar(0, 10, "x")
    model.Add(x == 7)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    assert status == cp_model.OPTIMAL, f"expected OPTIMAL, got {status}"
    assert solver.Value(x) == 7


@check("optimizer CLI (scripts/optimize_dk_lineups.py) starts as a real subprocess")
def _check_optimizer_cli():
    # A minimal, self-contained SYNTHETIC pool -- validates the CLI
    # mechanism (argument parsing, coverage diagnostics), never a real
    # slate/projection. Two starting pitchers + one hitter per required
    # position, all optimizer_eligible, is intentionally NOT enough to
    # fill a legal DK Classic roster (3 OF needed, only 1 given) -- the
    # point of this check is "did the CLI start and run its own
    # diagnostic logic to completion", not "did it find a lineup".
    with tempfile.TemporaryDirectory() as tmp:
        pool_path = Path(tmp) / "pool.json"
        positions = ["P", "P", "C", "1B", "2B", "3B", "SS", "OF"]
        players = []
        for i, pos in enumerate(positions):
            player_type = "pitcher" if pos == "P" else "hitter"
            players.append({
                "dk_player_id": f"d{i}", "mlb_player_id": f"m{i}", "name": f"Player {i}", "team": "AAA",
                "opponent": "BBB", "game_id": "g1", "player_type": player_type,
                "dk_positions": [pos], "salary": 4000, "projection": 10.0, "ceiling": 15.0, "floor": 5.0,
                "risk_score": 30.0, "confidence": 80.0, "optimizer_eligible": True,
            })
        pool_path.write_text(json.dumps({"players": players}), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "optimize_dk_lineups.py"), "--date", "2026-01-01", "--pool", str(pool_path), "--validate-only"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"exit code {result.returncode}, stderr: {result.stderr[-2000:]}"
        doc = json.loads(result.stdout.strip().splitlines()[-1])
        assert "errors" in doc and "coverage" in doc, f"unexpected CLI output shape: {doc}"
        assert doc["coverage"]["pool_size"] == len(players)


@check("artifact storage abstraction resolves without touching a real network")
def _check_storage():
    import os

    os.environ.pop("NODE_ENV", None)
    for key in ("OBJECT_STORAGE_REGION", "OBJECT_STORAGE_BUCKET", "OBJECT_STORAGE_ACCESS_KEY", "OBJECT_STORAGE_SECRET_KEY"):
        os.environ.pop(key, None)
    from research.artifact_storage import ARTIFACT_ROOT, LocalArtifactStorage, resolve_artifact_storage

    storage = resolve_artifact_storage(ARTIFACT_ROOT)
    assert isinstance(storage, LocalArtifactStorage), f"expected LocalArtifactStorage, got {type(storage).__name__}"


def main() -> int:
    print("=" * 70)
    print("BIG MONEY DFS -- PYTHON RUNTIME SMOKE TEST")
    print("=" * 70)
    ok = True
    for name, passed, error in RESULTS:
        print(f"\n[{'PASS' if passed else 'FAIL'}] {name}")
        if not passed:
            ok = False
            print(error)
    print("\n" + "=" * 70)
    print("ALL CHECKS PASSED" if ok else "ONE OR MORE CHECKS FAILED")
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
