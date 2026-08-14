"""CLI entry point: fetch an external projection provider's slate,
validate it, and persist it as an immutable baseline snapshot.

    python scripts/build_external_projection_baseline.py --date YYYY-MM-DD --provider mock
    python scripts/build_external_projection_baseline.py --date YYYY-MM-DD
        (uses EXTERNAL_PROJECTION_PROVIDER from the environment; fails
        clearly if nothing is configured)

BlueCollar cannot be used here yet -- see
external_projections/bluecollar_provider.py. Passing --provider
bluecollar will report "not configured" (documentation/credentials
required), never a network error, since no network call is ever made.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from external_projections.base import (  # noqa: E402
    ProjectionProviderAuthenticationError,
    ProjectionProviderNotConfiguredError,
    ProjectionProviderUnavailableError,
)
from external_projections.persistence import save_baseline_snapshot  # noqa: E402
from external_projections.registry import PROVIDER_FACTORIES  # noqa: E402
from external_projections.registry import get_configured_provider  # noqa: E402
from external_projections.validator import validate_external_players  # noqa: E402


def _resolve_provider(name: str = None):
    if name:
        factory = PROVIDER_FACTORIES.get(name.strip().lower())
        if factory is None:
            return None, f"--provider {name!r} is not a recognized provider. Supported: {sorted(PROVIDER_FACTORIES)}."
        return factory(), None
    provider, reason, source = get_configured_provider()
    if provider is None:
        return None, reason or "No external projection provider is configured (EXTERNAL_PROJECTION_PROVIDER is unset)."
    return provider, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and persist an external projection provider's baseline for one date.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--provider", default=None, help="Provider name (e.g. 'mock'). Defaults to EXTERNAL_PROJECTION_PROVIDER.")
    parser.add_argument("--sport", default="MLB")
    parser.add_argument("--site", default="draftkings")
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()

    provider, error = _resolve_provider(args.provider)
    if provider is None:
        print(json.dumps({"status": "unconfigured", "reason": error}))
        return

    if not provider.is_configured():
        print(json.dumps({"status": "unconfigured", "reason": f"{provider.provider_name()} is not connected yet -- documentation/credentials required.", "provider_name": provider.provider_name()}))
        return

    try:
        slates = provider.list_slates(args.date, sport=args.sport, site=args.site)
    except ProjectionProviderNotConfiguredError as e:
        print(json.dumps({"status": "unconfigured", "reason": str(e), "provider_name": provider.provider_name()}))
        return
    except (ProjectionProviderUnavailableError, ProjectionProviderAuthenticationError) as e:
        print(json.dumps({"status": "unavailable", "reason": str(e), "provider_name": provider.provider_name()}))
        return

    if not slates:
        print(json.dumps({"status": "no_slate", "reason": f"No slates found for {args.date}.", "provider_name": provider.provider_name()}))
        return

    slate = slates[0]
    players = provider.get_projections(slate.slate_id)
    warnings = validate_external_players(players)

    retrieved_at = datetime.now(timezone.utc).isoformat()
    document = {
        "slate_date": args.date,
        "provider": provider.name,
        "provider_name": provider.provider_name(),
        "provider_version": provider.provider_version(),
        "is_mock": provider.is_mock,
        "slate_id": slate.slate_id,
        "slate_name": slate.slate_name,
        "retrieved_at": retrieved_at,
        "player_count": len(players),
        "players": [p.to_dict() for p in players],
        "warnings": warnings,
    }
    path = save_baseline_snapshot(document)

    print(f"Provider: {provider.provider_name()} ({'MOCK' if provider.is_mock else 'real'})")
    print(f"Slate: {slate.slate_name or slate.slate_id}")
    print(f"Players: {len(players)}")
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
    print(f"\nSaved: {path}")
    print(json.dumps({"status": "ready", "provider_name": provider.provider_name(), "is_mock": provider.is_mock, "path": str(path), "player_count": len(players)}))


if __name__ == "__main__":
    main()
