"""CLI entry point: read whether Mock Mode is currently enabled
(Milestone 19, config/runtime_settings.py). OFF by default.

    python scripts/get_mock_mode.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.runtime_settings import is_mock_mode_enabled  # noqa: E402


def main() -> None:
    print(json.dumps({"enabled": is_mock_mode_enabled()}))


if __name__ == "__main__":
    main()
