"""Centralized environment-variable loading for Python entry points
(Milestone 24).

The Next.js dashboard automatically loads dashboard/.env.local (a
built-in Next.js convention) -- but Python entry points (research/,
scripts/, tests) are separate processes that Next.js does not always
spawn (e.g. a developer running `python scripts/build_game_environment_report.py`
directly from a terminal), so without this module a secret like
SPORTSGAMEODDS_API_KEY would have to be exported manually in every
shell session.

This module gives Python the SAME automatic behavior by reading the
SAME file Next.js already reads -- dashboard/.env.local. No secret is
duplicated into a second committed file, and dashboard/.env.local
remains the single source of truth for local secrets on both sides.

Real environment variables that are already set (e.g. exported by a
shell profile, CI, or Docker) always take precedence and are never
overwritten -- this only fills in values that are not already present.
"""

import os
from pathlib import Path
from typing import Optional

DASHBOARD_ENV_LOCAL_PATH = Path(__file__).resolve().parent.parent / "dashboard" / ".env.local"

_loaded_default = False


def _parse_env_line(line: str) -> Optional[tuple]:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    if not key:
        return None
    return key, value


def load_dashboard_env(path: Optional[Path] = None) -> None:
    """Reads KEY=VALUE lines from dashboard/.env.local into os.environ,
    skipping any key that's already set. Safe to call multiple times
    (idempotent) and safe to call when the file doesn't exist yet (no-op).
    Never raises, never prints/logs the values it loads."""
    global _loaded_default
    target = path if path is not None else DASHBOARD_ENV_LOCAL_PATH
    if path is None:
        if _loaded_default:
            return
        _loaded_default = True

    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in os.environ:
            os.environ[key] = value
