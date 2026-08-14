"""Mutable, dashboard-controlled runtime settings -- distinct from every
other config/*.py module (which are fixed, checked-in tuning constants).
Today this holds exactly one setting: Mock Mode (Milestone 19).

    runtime_settings/
      mock_mode.json     {"enabled": true|false}

Mock Mode is OFF by default and must be explicitly enabled by the user
(dashboard Settings page, or the "Enable Mock Mode" button shown when no
live DraftKings salary provider is configured -- see
dfs/providers/config.py). This file is the single source of truth for
that toggle on both sides: the dashboard writes it via
scripts/set_mock_mode.py, and every Python entry point that needs to
know whether mock data is allowed (dfs/providers/config.py) reads it via
is_mock_mode_enabled() below. Never checked into git (see .gitignore) --
this is live local state, not a reproducible artifact.
"""

import json
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "runtime_settings" / "mock_mode.json"


def is_mock_mode_enabled(settings_path: Path = DEFAULT_SETTINGS_PATH) -> bool:
    """Never raises: a missing or corrupt settings file simply means
    Mock Mode is OFF (the safe default), not an error."""
    try:
        with Path(settings_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("enabled", False))
    except (OSError, ValueError):
        return False


def set_mock_mode_enabled(enabled: bool, settings_path: Path = DEFAULT_SETTINGS_PATH) -> None:
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"enabled": bool(enabled)}, f)
