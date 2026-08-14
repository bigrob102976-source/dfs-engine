"""CLI entry point: prints a single JSON line describing Game
Environment report status for a date -- what the dashboard's status
card and Settings page render.

    python scripts/game_environment_status.py --date YYYY-MM-DD
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.game_environment import collector  # noqa: E402
from research.game_environment.storage import load_latest_environment_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Game Environment snapshot status for one date.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    weather_provider, weather_source = collector.get_configured_weather_provider()
    vegas_provider, vegas_source = collector.get_configured_vegas_provider()
    umpire_provider, umpire_source = collector.get_configured_umpire_provider()
    bullpen_provider, bullpen_source = collector.get_configured_bullpen_provider()

    report = load_latest_environment_report(args.date)

    print(json.dumps({
        "slate_date": args.date,
        "providers": {
            "weather": {"provider_name": weather_provider.provider_name(), "is_mock": weather_provider.is_mock, "source": weather_source},
            "vegas": {"provider_name": vegas_provider.provider_name(), "is_mock": vegas_provider.is_mock, "source": vegas_source},
            "umpire": {"provider_name": umpire_provider.provider_name(), "is_mock": umpire_provider.is_mock, "source": umpire_source},
            "bullpen": {"provider_name": bullpen_provider.provider_name(), "is_mock": bullpen_provider.is_mock, "source": bullpen_source},
        },
        "report": {
            "exists": report is not None,
            "generated_at": report.get("generated_at") if report else None,
            "game_count": len(report.get("games", [])) if report else None,
            "engine_version": report.get("engine_version") if report else None,
        },
    }))


if __name__ == "__main__":
    main()
