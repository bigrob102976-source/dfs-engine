"""CLI entry point: keeps EVERY real MLB Classic DK slate for a date
fresh in object storage, not just one -- the automatic external-worker
counterpart to fetch_dfs_slate.py's single-slate fetch.

WHY THIS EXISTS: the dashboard's optimizer auto-selects whichever real
slate has the most games (components/optimizer/OptimizerWorkspace.tsx),
but a previously-persisted user selection can point at a DIFFERENT
slate. Railway's own direct DraftKings access is blocked by an egress
IP restriction, so the dashboard depends entirely on a recent artifact
already sitting in object storage
(dashboard/lib/optimizerWorkspace/poolCache.ts's freshness-reuse
check). Fetching every discovered slate here, not just the biggest
one, means that reuse succeeds no matter which slate the frontend ends
up selecting.

Intended to run on a schedule from a machine with real DraftKings
network access (e.g. a Windows Task Scheduler entry invoking this via
`railway run` so real R2 credentials are injected without ever
touching local disk) -- NOT from inside the Railway container itself,
since that network path is the one that's blocked.

Never falls back to CSV/mock/synthetic data: this script's only job is
calling the existing scripts/fetch_dfs_slate.py once per real,
currently-discovered slate -- all persistence/validation logic is
exactly what that script already does. A DraftKings access failure
fails this script loudly (non-zero exit, message on stderr) rather
than writing anything.

Usage:
    python scripts/fetch_all_dfs_slates.py --date YYYY-MM-DD
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.providers.base import ProviderAuthenticationError, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.config import get_configured_provider

# M3D: each per-slate fetch_dfs_slate.py invocation now also performs
# an in-process canonical RAW/NORMALIZED write plus a Postgres shadow
# promotion subprocess (see fetch_dfs_slate.py::CANONICAL_PROMOTION_
# TIMEOUT_SECONDS) -- this outer timeout must stay comfortably larger
# than that inner budget, or this script could kill a per-slate child
# process while its OWN nested promotion subprocess is still validly
# running within its own budget.
FETCH_TIMEOUT_SECONDS = 90


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch every real DK Classic slate for a date, keeping all of them fresh in object storage.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--sport", default="MLB")
    parser.add_argument("--site", default="draftkings")
    args = parser.parse_args()

    print("=" * 70)
    print(f"FETCH ALL DFS SLATES -- {args.date}")
    print("=" * 70)

    provider, reason, _source = get_configured_provider(args.date)
    if provider is None:
        print(f"ERROR: no DFS provider configured: {reason}", file=sys.stderr)
        sys.exit(1)

    try:
        result = provider.get_slate(args.date, sport=args.sport, site=args.site, research_games=[])
    except (ProviderAuthenticationError, ProviderUnavailableError, ProviderNoSlateError) as e:
        print(f"ERROR: DraftKings Unofficial discovery failed: {e}", file=sys.stderr)
        sys.exit(1)

    if not result.slates:
        print("No real Classic slates discovered for this date -- nothing to fetch.")
        return

    print(f"Discovered {len(result.slates)} real slate(s): {[s.slate_id for s in result.slates]}")

    repo_root = Path(__file__).resolve().parent.parent
    failures = []
    for slate in result.slates:
        print(f"\n--- fetching {slate.slate_id} ({slate.slate_name}) ---")
        # M3D: a slow/hung slate (network or shadow-promotion side) must
        # never stop the OTHER valid slates in this cycle from being
        # attempted -- catch both a real timeout and any other
        # unexpected subprocess-launch failure per slate, record it, and
        # continue the loop.
        try:
            proc = subprocess.run(
                [
                    sys.executable, "scripts/fetch_dfs_slate.py",
                    "--date", args.date, "--slate-id", slate.slate_id,
                    "--sport", args.sport, "--site", args.site,
                ],
                capture_output=True, text=True, timeout=FETCH_TIMEOUT_SECONDS, cwd=repo_root,
            )
        except subprocess.TimeoutExpired as exc:
            print(f"TIMEOUT after {FETCH_TIMEOUT_SECONDS}s fetching {slate.slate_id} -- skipping, continuing with remaining slates.", file=sys.stderr)
            if exc.stdout:
                print(exc.stdout[-500:] if isinstance(exc.stdout, str) else exc.stdout.decode(errors="replace")[-500:])
            failures.append(slate.slate_id)
            continue
        except Exception as exc:  # noqa: BLE001 -- one slate's launch failure must not stop the batch
            print(f"ERROR launching fetch for {slate.slate_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures.append(slate.slate_id)
            continue

        print(proc.stdout[-500:])
        if proc.returncode != 0:
            print(proc.stderr[-500:], file=sys.stderr)
            failures.append(slate.slate_id)

    if failures:
        print(f"\nERROR: failed to fetch {len(failures)}/{len(result.slates)} slate(s): {failures}", file=sys.stderr)
        sys.exit(1)

    print(f"\nAll {len(result.slates)} slate(s) fetched successfully.")


if __name__ == "__main__":
    main()
