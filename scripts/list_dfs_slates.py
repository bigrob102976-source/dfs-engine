"""CLI entry point: read-only discovery of every DFS slate the
configured provider (dfs/providers/config.py) currently exposes for a
date, WITHOUT selecting one and WITHOUT writing any artifact -- safe to
call as often as the dashboard needs to populate/refresh a slate
dropdown (unlike scripts/fetch_dfs_slate.py, which always saves a new
immutable provider_slate_<timestamp>.json).

Always prints exactly one line of JSON to stdout and exits 0, even when
no provider is configured or the provider call fails -- callers branch
on the "status" field, never on exit code or stderr.

Usage:
    python scripts/list_dfs_slates.py --date YYYY-MM-DD
    python scripts/list_dfs_slates.py --date YYYY-MM-DD --sport MLB --site draftkings
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.providers.base import ProviderAuthenticationError, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.config import get_configured_provider


def _status_doc(status, reason, provider, source, slates=None, warnings=None):
    is_mock = provider is not None and provider.name == "mock_dev_provider"
    slates = slates or []
    return {
        "status": status,
        "reason": reason,
        "provider_name": provider.name if provider is not None else None,
        "provider_type": "mock" if is_mock else ("real" if provider is not None else None),
        "is_mock": is_mock,
        "is_connected": provider is not None and status == "ready",
        "source": source,
        "slates": slates,
        "slates_available": len(slates),
        "warnings": warnings or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="List every DFS slate the configured provider exposes for a date (read-only).")
    parser.add_argument("--date", required=True)
    parser.add_argument("--sport", default="MLB")
    parser.add_argument("--site", default="draftkings")
    args = parser.parse_args()

    provider, reason, source = get_configured_provider(args.date)
    if provider is None:
        print(json.dumps(_status_doc("not_connected", reason, None, source)))
        return

    try:
        result = provider.get_slate(args.date, sport=args.sport, site=args.site)
    except ProviderAuthenticationError as e:
        print(json.dumps(_status_doc("auth_failed", str(e), provider, source)))
        return
    except ProviderUnavailableError as e:
        print(json.dumps(_status_doc("unavailable", str(e), provider, source)))
        return
    except ProviderNoSlateError as e:
        print(json.dumps(_status_doc("no_slate", str(e), provider, source)))
        return

    status = "ready" if result.slates else "no_slate"
    reason = None if result.slates else "Provider returned zero slates for this date."
    print(json.dumps(_status_doc(
        status, reason, provider, source,
        slates=[s.to_dict() for s in result.slates], warnings=result.warnings,
    )))


if __name__ == "__main__":
    main()
