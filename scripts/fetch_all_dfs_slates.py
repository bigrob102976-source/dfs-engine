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
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from canonical_ingestion.pipeline import build_normalized_from_fetch
from canonical_ingestion.raw_capture import RawCaptureRecorder
from dfs.providers.base import ProviderAuthenticationError, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.config import get_configured_provider
from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider
from draftkings_unofficial.cache import DkUnofficialCache

# M3D: each per-slate fetch_dfs_slate.py invocation now also performs
# an in-process canonical RAW/NORMALIZED write plus a Postgres shadow
# promotion subprocess (see fetch_dfs_slate.py::CANONICAL_PROMOTION_
# TIMEOUT_SECONDS) -- this outer timeout must stay comfortably larger
# than that inner budget, or this script could kill a per-slate child
# process while its OWN nested promotion subprocess is still validly
# running within its own budget.
FETCH_TIMEOUT_SECONDS = 90

EASTERN = ZoneInfo("America/New_York")


def _eastern_date_offset(days: int) -> str:
    """Returns the America/New_York calendar date `days` days from right
    now, as YYYY-MM-DD -- the canonical slateDate contract's own
    timezone (canonical/slate_date.py), used here ONLY for PROVIDER
    ACQUISITION/DISCOVERY filtering (collector.slate_local_date() is
    already Eastern-based -- see that module's own docstring, and
    dfs/providers/draftkings_unofficial_provider.py's day_slates filter
    compares against exactly this kind of date string). This is
    deliberately NOT dashboard/lib/currentDate.ts's Chicago-anchored
    customer-facing "today", which this module never touches."""
    return (datetime.now(EASTERN) + timedelta(days=days)).strftime("%Y-%m-%d")


def prefetch_future_slates(sport: str = "MLB", site: str = "draftkings", days_ahead: int = 1) -> dict:
    """M4B/M4C/M4D -- shadow-only prefetch of the real DK Classic
    slate(s) already published for the America/New_York calendar date
    `days_ahead` days from right now (default 1, i.e. "tomorrow").

    SHADOW ONLY: writes canonical RAW R2 -> canonical NORMALIZED R2 ->
    canonical Postgres shadow CURRENT via the exact same shared
    functions the TODAY path uses (build_normalized_from_fetch,
    scripts.fetch_dfs_slate._run_canonical_promotion_batch) -- never a
    second, divergent implementation of either. All of this date's
    accepted slates are promoted in ONE `railway ssh` round trip (M4M:
    a live natural worker cycle showed promoting each slate with its
    own separate SSH round trip pushed total worker runtime past the
    internal timeout once several real Classic slates existed for the
    same date). NEVER calls
    scripts/fetch_dfs_slate.py's legacy _save_document/customer-facing
    write path -- a future date's data can therefore never land in
    today's legacy dfs_input/{date}/ namespace poolCache.ts reads from.

    Deliberately calls DraftKingsUnofficialProvider() directly (never
    get_configured_provider()) so a DFS_SALARY_PROVIDER override or Mock
    Mode active for TODAY's own fetch can never cause non-real data to
    be promoted into canonical Postgres for a future date -- M4's "real
    DraftKings data only" rule applies unconditionally here. The
    DK_UNOFFICIAL_ENABLED operational kill switch still applies (it's
    checked inside get_slate() itself). Uses a FRESH, unshared
    DkUnofficialCache() (mirrors canonical_ingestion.pipeline.
    ingest_slate_shadow's own established pattern) so `capture` fires
    against a genuine network round trip even though today's own
    collection already ran earlier in this SAME process.

    DK not having published this future date yet is NOT a failure --
    ProviderNoSlateError (zero DraftGroups found) is reported as
    status="NOT_YET_PUBLISHED", never a fabricated/placeholder slate.
    Never raises -- every real failure is caught and reported in the
    returned dict so a problem here can NEVER affect this process's own
    exit code or today's already-decided result (see main(), which
    calls this AFTER today's own outcome is already final)."""
    from scripts.fetch_dfs_slate import _run_canonical_promotion_batch

    future_date = _eastern_date_offset(days_ahead)
    started = time.monotonic()
    status: dict = {"date": future_date, "status": None, "slates": []}

    recorder = RawCaptureRecorder()
    provider = DraftKingsUnofficialProvider()
    try:
        result = provider.get_slate(
            future_date, sport=sport, site=site, research_games=[],
            capture=recorder.record, cache=DkUnofficialCache(),
        )
    except ProviderNoSlateError:
        status["status"] = "NOT_YET_PUBLISHED"
        status["duration_seconds"] = round(time.monotonic() - started, 3)
        return status
    except Exception as exc:  # noqa: BLE001 -- a future-date problem must never propagate
        status["status"] = "ERROR"
        status["error"] = f"{type(exc).__name__}: {exc}"
        status["duration_seconds"] = round(time.monotonic() - started, 3)
        return status

    status["status"] = "DISCOVERED"
    # M4M: build EVERY slate's shadow (RAW+NORMALIZED) result first,
    # deferring the network-bound promotion step until every key is
    # known -- so all of them can be promoted in ONE railway ssh round
    # trip below, rather than one round trip per slate.
    promotable: List[tuple] = []
    for slate_info in result.slates:
        provider_players = result.players_by_slate.get(slate_info.slate_id, [])
        slate_status: dict = {"slate_id": slate_info.slate_id, "slate_name": slate_info.slate_name}
        try:
            shadow_result = build_normalized_from_fetch(
                sport=sport, site=site, provider_name=provider.name, slate_info=slate_info,
                provider_players=provider_players, recorder=recorder,
            )
        except Exception as exc:  # noqa: BLE001
            slate_status["ok"] = False
            slate_status["error"] = f"{type(exc).__name__}: {exc}"
            status["slates"].append(slate_status)
            continue

        slate_status["ok"] = shadow_result.ok
        slate_status["player_count"] = shadow_result.player_count
        slate_status["normalized_hash"] = shadow_result.normalized_hash
        slate_status["is_semantic_duplicate"] = shadow_result.is_semantic_duplicate
        if not shadow_result.ok:
            slate_status["error"] = f"{shadow_result.error_type}: {shadow_result.error}"
            status["slates"].append(slate_status)
            continue

        status["slates"].append(slate_status)
        promotable.append((slate_status, shadow_result.normalized_key))

    if promotable:
        try:
            promotions = _run_canonical_promotion_batch([key for _, key in promotable])
        except Exception as exc:  # noqa: BLE001
            promotions = [{"ok": False, "error_type": type(exc).__name__, "error": str(exc)} for _ in promotable]
        for (slate_status, _key), promotion in zip(promotable, promotions):
            slate_status["promotion"] = promotion

    status["duration_seconds"] = round(time.monotonic() - started, 3)
    return status


def _run_today(args) -> int:
    print("=" * 70)
    print(f"FETCH ALL DFS SLATES -- {args.date}")
    print("=" * 70)

    provider, reason, _source = get_configured_provider(args.date)
    if provider is None:
        print(f"ERROR: no DFS provider configured: {reason}", file=sys.stderr)
        return 1

    try:
        result = provider.get_slate(args.date, sport=args.sport, site=args.site, research_games=[])
    except (ProviderAuthenticationError, ProviderUnavailableError, ProviderNoSlateError) as e:
        print(f"ERROR: DraftKings Unofficial discovery failed: {e}", file=sys.stderr)
        return 1

    if not result.slates:
        print("No real Classic slates discovered for this date -- nothing to fetch.")
        return 0

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
        return 1

    print(f"\nAll {len(result.slates)} slate(s) fetched successfully.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch every real DK Classic slate for a date, keeping all of them fresh in object storage.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--sport", default="MLB")
    parser.add_argument("--site", default="draftkings")
    args = parser.parse_args()

    today_started = time.monotonic()
    today_exit_code = _run_today(args)
    today_duration = round(time.monotonic() - today_started, 3)

    # M4: tomorrow-prefetch runs AFTER today's own outcome is already
    # decided, and is wrapped so it can NEVER affect today_exit_code or
    # today's own already-completed collection -- see
    # prefetch_future_slates's own docstring for why a future-date
    # problem must never look like a today failure to the Task
    # Scheduler wrapper (run_dk_fetch_worker.ps1) driving this script.
    print("\n" + "=" * 70)
    print("TOMORROW PREFETCH (shadow-only -- canonical Postgres CURRENT, never customer-visible)")
    print("=" * 70)
    tomorrow_duration = None
    try:
        tomorrow_status = prefetch_future_slates(sport=args.sport, site=args.site)
        tomorrow_duration = tomorrow_status.get("duration_seconds")
        print(json.dumps(tomorrow_status, indent=2, default=str))
    except Exception as exc:  # noqa: BLE001 -- belt-and-suspenders on top of prefetch_future_slates's own internal handling
        print(f"TOMORROW PREFETCH: unexpected top-level failure -- {type(exc).__name__}: {exc}", file=sys.stderr)

    # M4M: printed every cycle so a natural Task Scheduler run's own log
    # carries a real, timestamped record of how close total runtime gets
    # to the ~5-minute recurrence -- never inferred after the fact.
    total_duration = round(time.monotonic() - today_started, 3)
    print(
        f"\nWORKER TIMING -- today={today_duration}s tomorrow={tomorrow_duration if tomorrow_duration is not None else 'n/a'}s "
        f"total={total_duration}s"
    )

    if today_exit_code != 0:
        sys.exit(today_exit_code)


if __name__ == "__main__":
    main()
