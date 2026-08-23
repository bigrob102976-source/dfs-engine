"""CLI entry point: run the Game Environment Engine for one slate date
and persist an immutable snapshot.

    Research Package -> Game Environment Engine -> Immutable Snapshot

    python scripts/build_game_environment_report.py --date YYYY-MM-DD

Weather defaults to the REAL, live Open-Meteo Forecast provider
(Milestone 32.6 -- no API key required; set GAME_ENVIRONMENT_PROVIDER=mock
to opt into mock weather for local dev/testing). Vegas/Bullpen default
to the clearly-labeled mock providers unless a real odds/bullpen-usage
API is configured -- see research/game_environment/collector.py's
module docstring. Umpire data defaults to UNKNOWN for every game unless
GAME_ENVIRONMENT_UMPIRE_PROVIDER=mock is set, since the milestone
requires honest UNKNOWN rather than a guess.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.game_environment.engine import GameEnvironmentEngineError, build_slate_environment_report  # noqa: E402
from research.game_environment.storage import save_environment_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and persist a Game Environment report for one slate date.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--research-output-root", default="research_output")
    args = parser.parse_args()

    try:
        report = build_slate_environment_report(args.date, research_output_root=args.research_output_root)
    except GameEnvironmentEngineError as e:
        print(json.dumps({"status": "no_research", "reason": str(e)}))
        return

    path = save_environment_report(report.to_dict())

    print(f"Slate: {args.date}")
    print(f"Games scored: {len(report.games)}")
    if report.warnings:
        print(f"Warnings ({len(report.warnings)}):")
        for w in report.warnings:
            print(f"  - {w}")
    for g in report.games:
        print(f"  {g.away_team} @ {g.home_team}: overall={g.environment_score.overall} hitter={g.environment_score.hitter} pitcher={g.environment_score.pitcher} stack={g.environment_score.stack}")
    print(f"\nSaved: {path}")
    print(json.dumps({"status": "ready", "path": str(path), "game_count": len(report.games)}))


if __name__ == "__main__":
    main()
