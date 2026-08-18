"""CLI entry point: fetch today's DFS salary/slate data from the
configured provider (dfs/providers/config.py) and save an immutable
"provider slate" artifact -- the automatic replacement for a manually
uploaded DraftKings CSV (Milestone 13's one-click pipeline, step 4).

If the provider exposes more than one slate for the date and none is
specified via --slate-id, this saves an artifact recording every
discovered slate option WITHOUT picking one (status="needs_selection")
rather than guessing -- the dashboard then shows a selector and re-runs
this script with --slate-id once the user picks.

If no provider is configured (the default state -- see
dfs/providers/config.py), this completes cleanly with
status="not_connected" rather than crashing; see the milestone's
IMPORTANT FALLBACK requirement.

Usage:
    python scripts/fetch_dfs_slate.py --date YYYY-MM-DD
    python scripts/fetch_dfs_slate.py --date YYYY-MM-DD --slate-id mock-main-2026-08-11
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.providers.base import ProviderAuthenticationError, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.config import get_configured_provider
from research.adapters.pitcher_input import ResearchPackageNotFoundError, load_research_package
from research.prediction_snapshot import timestamp_tag
from research.storage import save_json

DEFAULT_OUTPUT_ROOT = "dfs_input"


def _load_research_games(date: str) -> list:
    """See scripts/list_dfs_slates.py's identical helper -- best-effort,
    never fails this script."""
    try:
        package = load_research_package("research_output", date)
    except ResearchPackageNotFoundError:
        return []
    return package.get("games", [])


def _no_overwrite(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing provider slate artifact: {path}")


def _save_document(args, status: str, reason, provider_name=None, source=None, raw_result=None, chosen_slate_id=None) -> Path:
    generated_at = datetime.now(timezone.utc).isoformat()
    ts = timestamp_tag(generated_at)
    players = []
    if raw_result is not None and chosen_slate_id:
        players = [p.to_dict() for p in raw_result.players_by_slate.get(chosen_slate_id, [])]

    is_mock = provider_name == "mock_dev_provider"
    document = {
        "slate_date": args.date,
        "generated_at_utc": generated_at,
        "sport": args.sport,
        "site": args.site,
        # "ready" | "not_connected" | "unavailable" | "auth_failed" | "no_slate" | "needs_selection" | "invalid_slate_id"
        "status": status,
        "reason": reason,
        "provider_name": provider_name,
        "provider_type": "mock" if is_mock else ("real" if provider_name else None),
        "is_mock": is_mock,
        # "explicit" (DFS_SALARY_PROVIDER was set) | "automatic_fallback" (unset -- defaulted to mock)
        "source": source,
        "slates": [s.to_dict() for s in raw_result.slates] if raw_result is not None else [],
        "warnings": raw_result.warnings if raw_result is not None else [],
        "selected_slate_id": chosen_slate_id,
        "players": players,
    }
    path = Path(args.output_root) / args.date / f"provider_slate_{ts}.json"
    _no_overwrite(path)
    save_json(path, document)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch today's DFS salary/slate data from the configured provider.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slate-id", default=None, help="Explicit slate to select when the provider exposes more than one")
    parser.add_argument("--sport", default="MLB")
    parser.add_argument("--site", default="draftkings")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()

    print("=" * 70)
    print("DFS SALARY PROVIDER FETCH")
    print("=" * 70)

    provider, reason, source = get_configured_provider(args.date)
    if provider is None:
        print("\nDFS SALARIES: NOT CONNECTED")
        print(reason)
        path = _save_document(args, status="not_connected", reason=reason, source=source)
        print(f"\nFile written:\n  - {path}")
        return

    print(f"\nProvider: {provider.name} (source: {source})")
    research_games = _load_research_games(args.date)
    try:
        result = provider.get_slate(args.date, sport=args.sport, site=args.site, research_games=research_games)
    except ProviderAuthenticationError as e:
        print(f"\nDFS SALARIES: AUTHENTICATION FAILED\n{e}")
        path = _save_document(args, status="auth_failed", reason=str(e), provider_name=provider.name, source=source)
        print(f"\nFile written:\n  - {path}")
        return
    except ProviderUnavailableError as e:
        print(f"\nDFS SALARIES: PROVIDER UNAVAILABLE\n{e}")
        path = _save_document(args, status="unavailable", reason=str(e), provider_name=provider.name, source=source)
        print(f"\nFile written:\n  - {path}")
        return
    except ProviderNoSlateError as e:
        print(f"\nDFS SALARIES: NO SLATE AVAILABLE\n{e}")
        path = _save_document(args, status="no_slate", reason=str(e), provider_name=provider.name, source=source)
        print(f"\nFile written:\n  - {path}")
        return

    if not result.slates:
        print("\nDFS SALARIES: NO SLATE AVAILABLE")
        for w in result.warnings:
            print(f"  - {w}")
        path = _save_document(
            args, status="no_slate", reason="Provider returned zero slates for this date.",
            provider_name=provider.name, source=source, raw_result=result,
        )
        print(f"\nFile written:\n  - {path}")
        return

    chosen = None
    if args.slate_id:
        chosen = next((s for s in result.slates if s.slate_id == args.slate_id), None)
        if chosen is None:
            print(f"\nERROR: --slate-id {args.slate_id!r} is not one of the discovered slates:")
            for s in result.slates:
                print(f"  - {s.slate_id}")
            path = _save_document(
                args, status="invalid_slate_id", reason=f"{args.slate_id!r} not found among discovered slates",
                provider_name=provider.name, source=source, raw_result=result,
            )
            print(f"\nFile written:\n  - {path}")
            return
    elif len(result.slates) == 1:
        chosen = result.slates[0]
        print(f"\nAuto-selected the only available slate: {chosen.slate_name or chosen.slate_id}")
    else:
        print(f"\n{len(result.slates)} slates available -- selection required:")
        for s in result.slates:
            print(f"  - {s.slate_id}: {s.slate_name} ({s.game_count} games)")
        path = _save_document(args, status="needs_selection", reason=None, provider_name=provider.name, source=source, raw_result=result)
        print(f"\nFile written:\n  - {path}")
        return

    players = result.players_by_slate.get(chosen.slate_id, [])
    print(f"\nSlate: {chosen.slate_name or chosen.slate_id}")
    print(f"Players: {len(players)}")
    if result.warnings:
        print("Warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    path = _save_document(
        args, status="ready", reason=None, provider_name=provider.name, source=source,
        raw_result=result, chosen_slate_id=chosen.slate_id,
    )
    print(f"\nFile written:\n  - {path}")


if __name__ == "__main__":
    main()
