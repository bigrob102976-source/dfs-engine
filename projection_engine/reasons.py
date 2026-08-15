"""Deterministic, human-readable explanation generation for the AI
Projection Engine -- no LLM, same "rank by salience, cap at N" pattern
as agents/pitcher_agent.py and agents/batter_agent.py's own _reasons()
functions (candidates ranked by magnitude, top N kept, every sentence
cites the real number behind it).
"""

from typing import List, Optional

from config.projection_engine_config import MAX_REASONS_PER_PLAYER, MAX_SIGNALS_IN_AI_SUMMARY
from projection_engine.models import SignalContribution


def format_signal_reason(signal: SignalContribution) -> str:
    """'Weather +0.42: Wind Out 14 MPH' -- matches the milestone's own
    worked example format (category, signed point delta, then reason)."""
    sign = "+" if signal.delta >= 0 else ""
    return f"{signal.label} {sign}{signal.delta:.2f}: {signal.reason}"


def build_reasons_list(signals: List[SignalContribution]) -> List[str]:
    """Every fired signal, ranked by |delta| (largest impact first),
    capped at MAX_REASONS_PER_PLAYER. A signal that weighted out to
    exactly 0.00 has nothing to report and is dropped."""
    nonzero = [s for s in signals if round(s.delta, 2) != 0.0]
    ranked = sorted(nonzero, key=lambda s: abs(s.delta), reverse=True)
    return [format_signal_reason(s) for s in ranked[:MAX_REASONS_PER_PLAYER]]


def build_ai_summary(
    name: str,
    ai_projection: Optional[float],
    ai_confidence: Optional[float],
    ai_risk: Optional[float],
    signals: List[SignalContribution],
) -> str:
    """One deterministic sentence per player, matching the milestone's
    worked example (name, AI Projection, Confidence, Risk, then the
    signals that moved it) -- e.g. 'Aaron Judge projects to 13.6 AI
    points (confidence 91, risk 28) with positive Weather, Vegas, and
    Park signals offset by Ownership.'"""
    if ai_projection is None:
        return f"{name}: no AI Projection available yet -- refresh today's research."

    nonzero = [s for s in signals if round(s.delta, 2) != 0.0]
    ranked = sorted(nonzero, key=lambda s: abs(s.delta), reverse=True)[:MAX_SIGNALS_IN_AI_SUMMARY]
    positives = [s.label for s in ranked if s.delta > 0]
    negatives = [s.label for s in ranked if s.delta < 0]

    def _join(labels: List[str]) -> str:
        if len(labels) == 1:
            return labels[0]
        if len(labels) == 2:
            return f"{labels[0]} and {labels[1]}"
        return f"{', '.join(labels[:-1])}, and {labels[-1]}"

    stats = f"{ai_projection:.1f} AI points"
    if ai_confidence is not None and ai_risk is not None:
        stats += f" (confidence {ai_confidence:.0f}, risk {ai_risk:.0f})"

    if not positives and not negatives:
        return f"{name} projects to {stats} with no material signal adjustments."
    if positives and not negatives:
        return f"{name} projects to {stats} with positive {_join(positives)} signals."
    if negatives and not positives:
        return f"{name} projects to {stats} with negative {_join(negatives)} signals."
    return f"{name} projects to {stats} with positive {_join(positives)} signals offset by {_join(negatives)}."
