import pytest

from research.game_environment.providers.consensus import build_consensus, devig_two_way, moneyline_to_probability
from research.game_environment.providers.models import BookLine


def test_moneyline_to_probability_negative_favorite():
    assert moneyline_to_probability(-150) == pytest.approx(150 / 250, abs=1e-9)


def test_moneyline_to_probability_positive_underdog():
    assert moneyline_to_probability(130) == pytest.approx(100 / 230, abs=1e-9)


def test_moneyline_to_probability_even():
    assert moneyline_to_probability(100) == pytest.approx(0.5, abs=1e-9)


def test_devig_two_way_removes_vig_and_sums_to_one():
    home_prob, away_prob = devig_two_way(-150, 130)
    assert home_prob + away_prob == pytest.approx(1.0, abs=1e-9)
    # Raw (vigged) probabilities sum to > 1.0; de-vigged should be strictly less than raw.
    raw_home = moneyline_to_probability(-150)
    assert home_prob < raw_home


def test_devig_two_way_symmetric_line_gives_fifty_fifty():
    home_prob, away_prob = devig_two_way(-110, -110)
    assert home_prob == pytest.approx(0.5, abs=1e-6)
    assert away_prob == pytest.approx(0.5, abs=1e-6)


def test_build_consensus_median_total():
    books = [
        BookLine(book="draftkings", total=8.5),
        BookLine(book="fanduel", total=9.0),
        BookLine(book="betmgm", total=8.5),
    ]
    consensus = build_consensus(books)
    assert consensus.total == 8.5
    assert consensus.total_books_used == 3


def test_build_consensus_win_probability_is_median_of_per_book_devig():
    books = [
        BookLine(book="draftkings", home_moneyline=-150, away_moneyline=130),
        BookLine(book="fanduel", home_moneyline=-145, away_moneyline=125),
        BookLine(book="betmgm", home_moneyline=-155, away_moneyline=135),
    ]
    consensus = build_consensus(books)
    assert consensus.home_win_probability is not None
    assert consensus.home_win_probability + consensus.away_win_probability == pytest.approx(1.0, abs=1e-6)
    assert consensus.moneyline_books_used == 3


def test_build_consensus_skips_books_missing_that_specific_market():
    books = [
        BookLine(book="draftkings", total=8.5, home_moneyline=-150, away_moneyline=130),
        BookLine(book="fanduel", total=9.0),  # no moneyline
        BookLine(book="betmgm", home_moneyline=-145, away_moneyline=125),  # no total
    ]
    consensus = build_consensus(books)
    assert consensus.total_books_used == 2
    assert consensus.moneyline_books_used == 2


def test_build_consensus_run_line_median():
    books = [
        BookLine(book="draftkings", home_run_line=-1.5),
        BookLine(book="fanduel", home_run_line=-1.5),
        BookLine(book="betmgm", home_run_line=-1.0),
    ]
    consensus = build_consensus(books)
    assert consensus.home_run_line == -1.5
    assert consensus.run_line_books_used == 3


def test_build_consensus_empty_books_returns_all_none():
    consensus = build_consensus([])
    assert consensus.total is None
    assert consensus.home_win_probability is None
    assert consensus.home_run_line is None
    assert consensus.books_used == []


def test_build_consensus_books_used_deduplicated_and_sorted():
    books = [
        BookLine(book="fanduel", total=8.5),
        BookLine(book="draftkings", total=9.0, home_moneyline=-150, away_moneyline=130),
    ]
    consensus = build_consensus(books)
    assert consensus.books_used == ["draftkings", "fanduel"]


def test_single_book_consensus_equals_that_book():
    books = [BookLine(book="draftkings", total=8.5, home_moneyline=-150, away_moneyline=130, home_run_line=-1.5)]
    consensus = build_consensus(books)
    assert consensus.total == 8.5
    assert consensus.home_run_line == -1.5
    assert consensus.total_books_used == 1
