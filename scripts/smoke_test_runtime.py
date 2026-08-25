"""Milestone 33.3: standalone Python runtime smoke test -- NOT a pytest
file, deliberately runnable with zero test-framework dependency (only
requirements.txt, never requirements-dev.txt) so it can double as a
container/CI "is this environment actually usable" gate before serving
real traffic, independent of whatever the full test suite validates.

Checks, in order, each printing PASS/FAIL and continuing (never stopping
early) so one failure doesn't hide a second, unrelated one:

  1. Every requirements.txt package imports cleanly.
  2. A real trained model loads and produces a real prediction (proves
     joblib/scikit-learn pickle compatibility with the pinned versions --
     see requirements.txt's own docstring on why this is version-sensitive).
  3. OR-Tools CP-SAT can solve a trivial toy problem (proves the solver
     backend itself works in this environment, independent of the whole
     DFS pipeline).
  4. The artifact storage abstraction resolves to LocalArtifactStorage in
     a non-production environment with no OBJECT_STORAGE_* configured
     (proves the storage import surface -- boto3 included -- is sound;
     never touches a real network).

Usage:
    python scripts/smoke_test_runtime.py

Exit code 0 only if every check passes.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


@check("load a real trained model and run inference")
def _check_model_inference():
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
