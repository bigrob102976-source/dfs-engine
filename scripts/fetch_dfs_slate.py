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
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.providers.base import ProviderAuthenticationError, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.config import get_configured_provider
from research.adapters.pitcher_input import ResearchPackageNotFoundError, load_research_package
from research.artifact_storage import raise_if_exists
from research.prediction_snapshot import timestamp_tag
from research.storage import save_json

DEFAULT_OUTPUT_ROOT = "dfs_input"
# M3: promotion is a single Postgres round-trip plus real `railway ssh`
# connection setup overhead (confirmed live: ~14.5s typical) -- generous
# but bounded so one stuck promotion can't stall the worker. Kept
# comfortably below scripts/fetch_all_dfs_slates.py's own outer per-slate
# FETCH_TIMEOUT_SECONDS (90s), which must always exceed real-fetch-time +
# this budget with margin -- see that script's own comment on
# FETCH_TIMEOUT_SECONDS for why.
CANONICAL_PROMOTION_TIMEOUT_SECONDS = 60
# MLB WORKER ORPHAN PROCESS HARDENING: `railway ssh --service X -- <cmd>`
# has no built-in mechanism tying the REMOTE command's lifetime to this
# LOCAL client connection -- confirmed live: killing (or, as here, Python's
# own subprocess.run(timeout=...) auto-killing) the LOCAL `railway.exe`
# process on timeout does NOT stop the remote `npx tsx
# scripts/promote-canonical-slate.ts` process or its own DB connections,
# which keep running (or hanging) on the container indefinitely. Wrapping
# the REMOTE command itself in GNU coreutils `timeout` (confirmed present
# on the deployed Debian 12 image, and confirmed live to correctly signal
# the ENTIRE remote descendant process tree, not just its direct child --
# GNU timeout puts the monitored command in its own process group and
# signals the whole group on expiry) makes the remote side self-terminate
# BEFORE this local timeout would otherwise fire, so no orphan is ever
# created by a promotion that genuinely hangs. TERM first (graceful --
# lets the promotion script's own DB transaction roll back cleanly),
# KILL after a short grace period if TERM didn't work. Sized well under
# CANONICAL_PROMOTION_TIMEOUT_SECONDS (worst case 40+10=50s vs local 60s)
# so this remote self-stop is what normally resolves a hang; the local
# timeout above remains a pure backup for the pathological case where the
# remote `timeout` binary itself is somehow unavailable.
CANONICAL_PROMOTION_REMOTE_TIMEOUT_SECONDS = 40
CANONICAL_PROMOTION_REMOTE_KILL_AFTER_SECONDS = 10
REPO_ROOT = Path(__file__).resolve().parent.parent
# M3 architecture finding: this Windows worker machine has real DK
# network access but NOT network access to Railway's private network
# (postgres.railway.internal only resolves from inside a container
# actually running on Railway -- confirmed live: a local `railway run`
# subprocess promotion attempt failed with
# "getaddrinfo ENOTFOUND postgres.railway.internal"). `railway ssh`
# executes the command INSIDE the real deployed container instead of
# locally, which DOES have that access (same real command verified live:
# a Postgres promotion via railway ssh succeeded, ~14.5s). This is the
# same --service/--environment pair every other railway invocation for
# this project already uses (see worker/run_dk_fetch_worker.ps1).
CANONICAL_PROMOTION_RAILWAY_SERVICE = "dfs-engine"
CANONICAL_PROMOTION_RAILWAY_ENVIRONMENT = "production"


def _load_research_games(date: str) -> list:
    """See scripts/list_dfs_slates.py's identical helper -- best-effort,
    never fails this script."""
    try:
        package = load_research_package("research_output", date)
    except ResearchPackageNotFoundError:
        return []
    return package.get("games", [])


def _no_overwrite(path: Path) -> None:
    # Milestone 33.2: storage-aware (see bluecollar/persistence.py's
    # identical comment for why this replaced a local path.exists() check).
    raise_if_exists(path)


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

    # M3 bugfix (found via a real natural worker cycle logging
    # EmptyRawCaptureError for every slate): draftkings_unofficial/cache.py's
    # shared, process-global TTL cache means get_configured_provider()'s
    # OWN internal probe call below is the genuine FIRST real network
    # fetch in this process -- passing `capture` only to THIS script's
    # later provider.get_slate() call (further down) never fires it,
    # since that call is a same-process cache HIT by the time it runs.
    # `capture` must be wired into the probe call itself; see
    # dfs/providers/config.py::get_configured_provider's own updated
    # docstring. Created unconditionally (before we even know which
    # provider will be selected) and simply unused if the outcome isn't
    # draftkings_unofficial -- passing it into get_configured_provider is
    # harmless either way (mock/explicit-override branches never touch it).
    from canonical_ingestion.raw_capture import RawCaptureRecorder

    recorder = RawCaptureRecorder()
    provider, reason, source = get_configured_provider(args.date, capture=recorder.record)
    if provider is None:
        print("\nDFS SALARIES: NOT CONNECTED")
        print(reason)
        path = _save_document(args, status="not_connected", reason=reason, source=source)
        print(f"\nFile written:\n  - {path}")
        return

    print(f"\nProvider: {provider.name} (source: {source})")
    research_games = _load_research_games(args.date)

    # Only the real DK provider accepts `capture`/`cache` kwargs at all
    # (mock/CSV providers do not) -- passed here too for robustness
    # (e.g. if the shared cache's TTL ever changes), but the real fix is
    # the probe call above; this call is expected to be a cache hit.
    get_slate_kwargs = {"capture": recorder.record} if provider.name == "draftkings_unofficial" else {}
    if provider.name != "draftkings_unofficial":
        recorder = None

    try:
        result = provider.get_slate(args.date, sport=args.sport, site=args.site, research_games=research_games, **get_slate_kwargs)
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

    # M2/M3: parallel/shadow canonical ingestion -- attached HERE,
    # deliberately AFTER the legacy artifact write above has already
    # succeeded, and ONLY for the real DraftKings Unofficial provider
    # (never mock/CSV -- those never populate `recorder`). Runs IN-PROCESS
    # (M3: no subprocess, no second fetch -- reuses `result`/`recorder`
    # from the ONE real fetch above) through RAW+NORMALIZED R2, then
    # automatically triggers Postgres shadow promotion as a single
    # subprocess call to the Node/TS promotion script (Postgres access
    # has always lived exclusively on the Node side of this codebase --
    # see canonical_ingestion/__init__.py). Every step is wrapped so a
    # shadow-path failure can NEVER affect this script's own exit code
    # or the legacy artifact just written -- see canonical_ingestion/
    # pipeline.py's M2I/M3C docstring. The customer-facing path
    # (poolCache.ts, reading the file written above) is unaffected
    # either way.
    if provider.name == "draftkings_unofficial" and recorder is not None:
        try:
            _run_canonical_shadow_and_promotion(args.date, args.sport, args.site, chosen, result, recorder)
        except Exception as exc:  # noqa: BLE001 -- M3C: belt-and-suspenders; the legacy artifact above is already written and must not be affected
            print(f"\nCANONICAL SHADOW/PROMOTION: unexpected top-level failure -- {type(exc).__name__}: {exc}", file=sys.stderr)


def _run_canonical_shadow_and_promotion(date: str, sport: str, site: str, chosen_slate_info, fetch_result, recorder) -> dict:
    """Returns a structured shadow-status dict (never raises) -- the
    caller is expected to print it; a future M3E status-recording step
    can also persist it. Fields mirror
    canonical_ingestion.pipeline.ShadowIngestionResult plus a nested
    `promotion` result."""
    from canonical_ingestion.pipeline import build_normalized_from_fetch

    provider_players = fetch_result.players_by_slate.get(chosen_slate_info.slate_id, [])
    shadow_result = build_normalized_from_fetch(
        sport=sport, site=site, provider_name="draftkings_unofficial", slate_info=chosen_slate_info,
        provider_players=provider_players, recorder=recorder,
    )
    print("\n--- canonical shadow ingestion ---")
    print(json.dumps(shadow_result.to_dict(), indent=2, default=str))

    status = shadow_result.to_dict()
    status["collection_date"] = date  # M4: the caller's own fetch-trigger date/window (e.g. "today" vs "tomorrow"), for observability only -- never used for RAW/NORMALIZED partitioning
    status["promotion"] = None

    if not shadow_result.ok:
        print(f"CANONICAL SHADOW INGESTION: FAILED -- {shadow_result.error_type}: {shadow_result.error}", file=sys.stderr)
        return status

    print(
        f"CANONICAL SHADOW INGESTION: OK -- {shadow_result.player_count} players "
        f"({shadow_result.resolved_count} resolved, {shadow_result.unresolved_count} unresolved, "
        f"{shadow_result.review_required_count} review-required)"
    )
    promotion = _run_canonical_promotion(shadow_result.normalized_key)
    status["promotion"] = promotion

    # M3K: fire the optional success heartbeat ONLY when every real stage
    # succeeded -- a real slate was found (we're in this function at
    # all), real players were fetched (checked below), NORMALIZED write
    # succeeded (shadow_result.ok, already true to reach here), AND
    # Postgres promotion actually PROMOTED (not merely "the script exited
    # 0" -- a legitimate no-op/rejection also exits 0). See
    # canonical_ingestion/heartbeat.py's own docstring for the full
    # definition and why "the worker merely started" is never sufficient.
    if provider_players and promotion.get("promoted") is True:
        from canonical_ingestion.heartbeat import send_success_heartbeat

        send_success_heartbeat(detail=f"{chosen_slate_info.slate_id}: {shadow_result.player_count} players")

    return status


def _run_canonical_promotion_batch(normalized_keys: List[str]) -> List[dict]:
    """M4M: promotes MULTIPLE NORMALIZED artifacts in ONE `railway ssh`
    round trip -- a live natural worker cycle showed several real
    Classic slates published for the same date (tomorrow's Main/Turbo/
    Night all needing promotion in the same ~5-minute cycle) paying
    repeated SSH connection-setup latency, once per slate via
    _run_canonical_promotion, was enough to push total worker runtime
    past run_dk_fetch_worker.ps1's own internal timeout (observed:
    process killed after 150s despite every individual promotion having
    already succeeded). This amortizes the SSH round trip only -- each
    key is still promoted independently server-side (its own
    transaction, its own result; see promote-canonical-slate.ts's own
    --key-repeated loop), never a second, divergent promotion
    implementation of dashboard/lib/db/canonicalPromotion.ts.

    Never raises; returns exactly one result dict per input key, in the
    SAME order as `normalized_keys` -- a whole-subprocess failure (CLI
    missing, launch exception, non-zero exit) is reported as that same
    failure for every key, since none of them could have been attempted."""
    if not normalized_keys:
        return []

    railway_path = shutil.which("railway")
    if railway_path is None:
        print("CANONICAL PROMOTION: skipped -- railway CLI not found on PATH.", file=sys.stderr)
        failure = {"ok": False, "promoted": False, "error": "railway CLI not found on PATH", "error_type": "railway_cli_not_found"}
        return [dict(failure) for _ in normalized_keys]

    print(f"\n--- canonical shadow promotion (via railway ssh, {len(normalized_keys)} slate(s) in one round trip) ---")
    argv = [
        railway_path, "ssh", "--service", CANONICAL_PROMOTION_RAILWAY_SERVICE, "--environment", CANONICAL_PROMOTION_RAILWAY_ENVIRONMENT,
        "--", "timeout", "--signal=TERM", f"--kill-after={CANONICAL_PROMOTION_REMOTE_KILL_AFTER_SECONDS}",
        str(CANONICAL_PROMOTION_REMOTE_TIMEOUT_SECONDS), "npx", "tsx", "scripts/promote-canonical-slate.ts",
    ]
    for key in normalized_keys:
        argv.extend(["--key", key])

    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=CANONICAL_PROMOTION_TIMEOUT_SECONDS, cwd=REPO_ROOT, check=False,
        )
    except Exception as exc:  # noqa: BLE001 -- M2I/M3C: report, never let this break the legacy fetch
        print(f"CANONICAL PROMOTION: could not be launched -- {type(exc).__name__}: {exc}", file=sys.stderr)
        failure = {"ok": False, "promoted": False, "error": str(exc), "error_type": type(exc).__name__}
        return [dict(failure) for _ in normalized_keys]

    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    if proc.returncode != 0:
        print(f"CANONICAL PROMOTION: FAILED -- exit code {proc.returncode}", file=sys.stderr)
        failure = {"ok": False, "promoted": False, "error": f"exit code {proc.returncode}", "error_type": "promotion_script_nonzero_exit", "stderr_tail": proc.stderr[-1000:]}
        return [dict(failure) for _ in normalized_keys]

    # M3K/M4M: parse each RESULT_JSON: line (one per --key, in order --
    # see promote-canonical-slate.ts's own comment) to know whether that
    # SPECIFIC key actually PROMOTED -- distinct from "the script exited
    # 0", which is also true for a legitimate no-op/rejection.
    results: List[dict] = []
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT_JSON:"):
            try:
                parsed = json.loads(line[len("RESULT_JSON:"):])
                results.append({"ok": True, "promoted": parsed.get("promoted"), "reason": parsed.get("reason")})
            except (ValueError, TypeError):
                results.append({"ok": True, "promoted": None, "reason": None})

    # Defensive only -- should never trigger in practice (the script
    # emits exactly one RESULT_JSON: line per --key it was given).
    while len(results) < len(normalized_keys):
        results.append({"ok": True, "promoted": None, "reason": "no RESULT_JSON line found for this key"})
    results = results[: len(normalized_keys)]

    promoted_count = sum(1 for r in results if r.get("promoted"))
    print(f"CANONICAL PROMOTION: OK (script succeeded; {promoted_count}/{len(results)} promoted)")
    return results


def _run_canonical_promotion(normalized_key: str) -> dict:
    """Automatic M3B promotion trigger for a SINGLE artifact -- the
    TODAY per-slate path's own entry point, unchanged in behavior since
    before M4M. Delegates to _run_canonical_promotion_batch (never a
    second, divergent promotion implementation) with a one-element list,
    which produces the exact same `railway ssh ... --key <key>` argv
    this function always used."""
    return _run_canonical_promotion_batch([normalized_key])[0]


if __name__ == "__main__":
    main()
