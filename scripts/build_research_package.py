"""CLI entry point: build the shared MLB research package for one slate date.

Usage:
    python scripts/build_research_package.py --date YYYY-MM-DD
    python scripts/build_research_package.py --date YYYY-MM-DD --output research_output
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.engine import build_research_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the MLB research package for a slate date.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--output", default="research_output", help="Output root directory (default: research_output)")
    args = parser.parse_args()

    report = build_research_package(args.date, output_root=args.output)

    print("=" * 70)
    print(f"MLB RESEARCH PACKAGE -- {report.slate_date}")
    print("=" * 70)
    print(f"Games found:    {report.games_found}")
    print(f"Teams found:    {report.teams_found}")
    print(f"Pitchers found: {report.pitchers_found}")
    print(f"Batters found:  {report.batters_found}")
    print()

    if report.warnings:
        print(f"Warnings ({len(report.warnings)}):")
        for w in report.warnings:
            print(f"  - {w}")
    else:
        print("Warnings: none")
    print()

    if report.errors:
        print(f"Errors ({len(report.errors)}):")
        for e in report.errors:
            print(f"  - {e}")
    else:
        print("Errors: none")
    print()

    print("Files written:")
    for name, path in report.files_written.items():
        print(f"  - {name}: {path}")
    print()

    print(f"Execution time: {report.duration_seconds}s")


if __name__ == "__main__":
    main()
