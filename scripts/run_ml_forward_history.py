"""CLI entry point: cumulative Big Money ML forward-history windows
(1/3/5/10/all completed slates) -- see evaluation/ml_forward_history.py.

    python scripts/run_ml_forward_history.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.ml_forward_history import build_cumulative_forward_history  # noqa: E402


def main() -> None:
    history = build_cumulative_forward_history()
    print(f"Total completed slates: {history['total_slates_completed']}")
    if history["early_sample"]:
        print(history["early_sample_warning"])
    print(json.dumps({"status": "ok", "history": history}, default=str))


if __name__ == "__main__":
    main()
