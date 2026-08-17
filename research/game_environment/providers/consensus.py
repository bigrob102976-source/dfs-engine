"""Deterministic market consensus across sportsbooks (Milestone 24).

Never trusts a single book -- every consensus figure here is a robust
statistic (median) across whichever books actually returned that
specific market, so one outlier/stale book can't dominate the number a
projection or the dashboard reads. Only books that ACTUALLY returned
data for a given market are counted; a missing book is never imputed or
treated as agreeing with the rest.

--------------------------------------------------------------------------
No-vig (vig-removal) methodology -- documented, not guessed
--------------------------------------------------------------------------
For one sportsbook's two-sided moneyline (home_ml, away_ml):

    raw_home = moneyline_to_probability(home_ml)
    raw_away = moneyline_to_probability(away_ml)

Because a sportsbook builds in its own margin (the "vig"/"juice"),
raw_home + raw_away is always slightly > 1.0. This module uses the
PROPORTIONAL (multiplicative) de-vig method -- the simplest, most
commonly published two-way de-vig technique, and the only one this
project uses (never silently swapped for a more elaborate method like
Shin's method, which needs betting-volume data this project doesn't
have):

    overround = raw_home + raw_away
    no_vig_home = raw_home / overround
    no_vig_away = raw_away / overround

De-vig happens PER BOOK first (each book has its own vig), and the
CONSENSUS win probability is the median of the individual books'
already-de-vigged probabilities -- not a de-vig of an already-averaged
moneyline, which would blend different books' vig levels together
before removing any of it.
"""

from dataclasses import asdict, dataclass, field
from statistics import median
from typing import List, Optional, Tuple

from research.game_environment.providers.models import BookLine


@dataclass
class ConsensusMarket:
    total: Optional[float] = None
    total_books_used: int = 0
    home_moneyline: Optional[int] = None  # median raw American moneyline (informational only -- win probability below is what's actually used downstream)
    away_moneyline: Optional[int] = None
    home_win_probability: Optional[float] = None  # median of each book's own no-vig probability
    away_win_probability: Optional[float] = None
    moneyline_books_used: int = 0
    home_run_line: Optional[float] = None
    run_line_books_used: int = 0
    books_used: List[str] = field(default_factory=list)
    method: str = "median_total; per_book_proportional_no_vig_then_median_win_probability; median_run_line"

    def to_dict(self) -> dict:
        return asdict(self)


def moneyline_to_probability(moneyline: int) -> float:
    if moneyline < 0:
        return (-moneyline) / ((-moneyline) + 100)
    return 100 / (moneyline + 100)


def devig_two_way(home_ml: int, away_ml: int) -> Tuple[float, float]:
    """Returns (no_vig_home_probability, no_vig_away_probability),
    always summing to exactly 1.0. See this module's docstring for the
    exact proportional method."""
    raw_home = moneyline_to_probability(home_ml)
    raw_away = moneyline_to_probability(away_ml)
    overround = raw_home + raw_away
    if overround <= 0:
        return 0.5, 0.5
    return raw_home / overround, raw_away / overround


def build_consensus(books: List[BookLine]) -> ConsensusMarket:
    totals = [b.total for b in books if b.total is not None]
    ml_pairs = [(b.home_moneyline, b.away_moneyline) for b in books if b.home_moneyline is not None and b.away_moneyline is not None]
    run_lines = [b.home_run_line for b in books if b.home_run_line is not None]

    books_used = sorted(
        {
            b.book
            for b in books
            if b.total is not None or (b.home_moneyline is not None and b.away_moneyline is not None) or b.home_run_line is not None
        }
    )

    consensus_total = round(median(totals), 2) if totals else None

    home_probs: List[float] = []
    for home_ml, away_ml in ml_pairs:
        home_prob, _ = devig_two_way(home_ml, away_ml)
        home_probs.append(home_prob)
    home_win_probability = round(median(home_probs), 4) if home_probs else None
    away_win_probability = round(1.0 - home_win_probability, 4) if home_win_probability is not None else None

    consensus_home_ml = int(round(median([p[0] for p in ml_pairs]))) if ml_pairs else None
    consensus_away_ml = int(round(median([p[1] for p in ml_pairs]))) if ml_pairs else None

    consensus_run_line = round(median(run_lines), 2) if run_lines else None

    return ConsensusMarket(
        total=consensus_total,
        total_books_used=len(totals),
        home_moneyline=consensus_home_ml,
        away_moneyline=consensus_away_ml,
        home_win_probability=home_win_probability,
        away_win_probability=away_win_probability,
        moneyline_books_used=len(ml_pairs),
        home_run_line=consensus_run_line,
        run_line_books_used=len(run_lines),
        books_used=books_used,
    )
