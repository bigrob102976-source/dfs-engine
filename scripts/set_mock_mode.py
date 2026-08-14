"""CLI entry point: explicitly enable/disable Mock Mode (Milestone 19,
config/runtime_settings.py). This is the dashboard's ONLY way to turn
mock data on -- there is no automatic fallback anymore.

    python scripts/set_mock_mode.py --enabled true
    python scripts/set_mock_mode.py --enabled false
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.runtime_settings import set_mock_mode_enabled  # noqa: E402


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("true", "1", "yes", "on")


def main() -> None:
    parser = argparse.ArgumentParser(description="Enable or disable Mock Mode.")
    parser.add_argument("--enabled", required=True, choices=["true", "false"])
    args = parser.parse_args()

    enabled = _parse_bool(args.enabled)
    set_mock_mode_enabled(enabled)
    print(json.dumps({"status": "ok", "enabled": enabled}))


if __name__ == "__main__":
    main()
