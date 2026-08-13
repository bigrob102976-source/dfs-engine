"""CLI entry point: load the sample slate, score it, print a ranked board.

Usage:
    python scripts/run_pitcher_agent.py [path/to/pitchers.json]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.pitcher_agent import analyze_slate
from services.pitcher_data import load_pitchers_from_json, DEFAULT_SAMPLE_PATH


def _print_board(board) -> None:
    print("=" * 78)
    print("MLB DFS PITCHER BOARD")
    print("=" * 78)
    print()

    for rank, entry in enumerate(board, start=1):
        print(f"{rank}. {entry.name} ({entry.team} vs {entry.opponent})")
        print(f"   Projection: {entry.projection:<6} Ceiling: {entry.ceiling:<6} Floor: {entry.floor}")
        print(f"   Salary: ${entry.salary:,}")
        print(
            f"   Overall: {entry.overall_score:<5} K Upside: {entry.strikeout_score:<5} "
            f"Run Prevention: {entry.run_prevention_score:<5} Matchup: {entry.matchup_score:<5}"
        )
        print(
            f"   Workload: {entry.workload_score:<5} Contact: {entry.contact_score:<5} "
            f"Environment: {entry.environment_score:<5} Value: {entry.value_score:<5}"
        )
        print(f"   Risk: {entry.risk_score:<5} Confidence: {entry.confidence}")
        print()
        print(f"   Tags: {', '.join(entry.tags) if entry.tags else '(none)'}")
        print()
        print("   Why:")
        for reason in entry.reasons:
            print(f"   - {reason}")
        print()
        print("-" * 78)

    print()
    print("SUMMARY TABLE")
    header = f"{'Rk':<3} {'Pitcher':<28} {'Salary':>8} {'Proj':>6} {'Ceil':>6} {'Value':>6} {'Ovr':>5} {'Risk':>5} {'Conf':>5}"
    print(header)
    print("-" * len(header))
    for rank, entry in enumerate(board, start=1):
        print(
            f"{rank:<3} {entry.name:<28} ${entry.salary:>7,} {entry.projection:>6} {entry.ceiling:>6} "
            f"{entry.value_score:>6} {entry.overall_score:>5} {entry.risk_score:>5} {entry.confidence:>5}"
        )


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE_PATH
    pitchers = load_pitchers_from_json(path)
    board = analyze_slate(pitchers)
    _print_board(board)


if __name__ == "__main__":
    main()
