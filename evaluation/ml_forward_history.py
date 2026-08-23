"""Milestone 32.5 -- cumulative Big Money ML forward-history windows
(1/3/5/10/all completed slates) built on top of the already-collected,
immutable per-slate documents (ml_forward_persistence.py). Never
recomputes/refetches results itself -- purely aggregates what
evaluate_forward_performance() / evaluate_forward_hitter_performance() /
evaluate_forward_combined_performance() already know how to pool across
a list of dates, applied to the N most recent COMPLETED slate dates.

EARLY SAMPLE gating: fewer than MIN_SLATES_FOR_CONCLUSIONS completed
slates means every window's numbers are still displayed (never hidden),
but the caller is told (via `early_sample: True` and an explicit
warning string) not to draw strong conclusions or declare any source
"best" yet -- see this module's own docstring on `build_cumulative_
forward_history`'s return value.
"""

from typing import List

from evaluation.big_money_ml_evaluation import evaluate_forward_hitter_performance, evaluate_forward_performance
from evaluation.ml_forward_grading import evaluate_forward_combined_performance
from evaluation.ml_forward_persistence import DEFAULT_ML_FORWARD_RESULTS_ROOT, list_all_ml_forward_results_slates

MIN_SLATES_FOR_CONCLUSIONS = 5
EARLY_SAMPLE_WARNING = "EARLY SAMPLE -- DO NOT DRAW STRONG CONCLUSIONS"
_WINDOW_SIZES = (1, 3, 5, 10)


def _unique_dates_most_recent_first(slates: List[dict]) -> List[str]:
    seen = []
    for doc in reversed(slates):  # slates is oldest-first; walk newest-first
        date = doc.get("slate_date")
        if date and date not in seen:
            seen.append(date)
    return seen


def build_cumulative_forward_history(output_root=DEFAULT_ML_FORWARD_RESULTS_ROOT, results_root=None, ml_root=None) -> dict:
    """Returns:
        {
          "total_slates_completed": int,
          "early_sample": bool,
          "early_sample_warning": str | None,   # only when early_sample
          "windows": {"1": {...}, "3": {...}, ...},  # only sizes <= total_slates_completed, plus "all"
        }
    Each window value has "hitters"/"pitchers"/"combined" -- each the
    direct return of the matching evaluate_forward_*_performance()
    call over that window's date list. A window smaller than what's
    actually available is never fabricated (e.g. a "5" window is never
    shown with only 3 completed slates -- see the milestone's own "Only
    show a range when enough data exists" instruction)."""
    slates = list_all_ml_forward_results_slates(output_root=output_root)
    dates_most_recent_first = _unique_dates_most_recent_first(slates)
    total = len(dates_most_recent_first)

    kwargs = {}
    if results_root is not None:
        kwargs["results_root"] = results_root
    if ml_root is not None:
        kwargs["ml_root"] = ml_root

    def _window(dates: List[str]) -> dict:
        return {
            "dates": list(reversed(dates)),  # chronological, oldest-first, for display
            "pitchers": evaluate_forward_performance(dates, **kwargs),
            "hitters": evaluate_forward_hitter_performance(dates, **kwargs),
            "combined": evaluate_forward_combined_performance(dates, **kwargs),
        }

    windows = {}
    for size in _WINDOW_SIZES:
        if total >= size:
            windows[str(size)] = _window(dates_most_recent_first[:size])
    if total > 0:
        windows["all"] = _window(dates_most_recent_first)

    early_sample = total < MIN_SLATES_FOR_CONCLUSIONS
    return {
        "total_slates_completed": total,
        "early_sample": early_sample,
        "early_sample_warning": EARLY_SAMPLE_WARNING if early_sample else None,
        "windows": windows,
    }
