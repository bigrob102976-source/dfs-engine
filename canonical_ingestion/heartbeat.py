"""M3K -- optional, provider-neutral success heartbeat hook.

AUDIT (M3K): no external heartbeat/dead-man's-switch system exists
anywhere in this codebase today -- confirmed via repo-wide search. The
only existing "heartbeat" concept is the internal `worker_heartbeats`
Postgres table (lib/jobs/heartbeat.ts), which tracks JOB WORKER
liveness, not an external monitoring service. This module fills that
gap, optionally.

Configuration: a single, optional environment variable,
CANONICAL_SHADOW_HEARTBEAT_URL. If unset (the default), send_success_
heartbeat() does nothing at all -- NO external HTTP request is ever
made, no service is contacted, no credential is required. This
deliberately does NOT purchase, activate, or hardcode any specific
provider (healthchecks.io, Cronitor, BetterStack, ...) -- an operator
who wants one plugs in whatever "ping this URL on success" endpoint
their chosen service issues them, as a plain env var.

SUCCESS DEFINITION (per M3K's explicit requirement -- narrower than
"the worker merely started"): call send_success_heartbeat() ONLY after
ALL of the following are independently true for a real slate:
  1. a real DK slate was found (provider.get_slate() returned it)
  2. real draftables were actually fetched (players_by_slate non-empty
     is the caller's own signal, not checked here)
  3. validation passed (slate.validationState == VALID, reflected by
     the canonical shadow result being ok=True)
  4. canonical NORMALIZED R2 write succeeded (ShadowIngestionResult.ok)
  5. shadow Postgres promotion succeeded (the promotion subprocess
     returned ok=True)
See scripts/fetch_dfs_slate.py::_run_canonical_shadow_and_promotion for
the exact call site -- this module itself has no opinion on when to
call it; it only decides WHETHER a call reaches the network.
"""

import os
import urllib.parse
import urllib.request
from typing import Optional

HEARTBEAT_URL_ENV_VAR = "CANONICAL_SHADOW_HEARTBEAT_URL"
HEARTBEAT_TIMEOUT_SECONDS = 10


def send_success_heartbeat(detail: Optional[str] = None) -> bool:
    """Sends a best-effort GET ping to CANONICAL_SHADOW_HEARTBEAT_URL if
    (and only if) it's configured. `detail` (e.g. "146757: 840 players")
    is appended as a `?detail=` query parameter for whatever monitoring
    dashboard the operator's chosen service shows it in -- purely
    cosmetic, never required. Returns True if a ping was actually
    attempted (regardless of whether it succeeded), False if no URL was
    configured (the common, default case -- no external request occurs
    at all). NEVER raises -- a monitoring integration must never be able
    to break the pipeline it's monitoring."""
    url = os.environ.get(HEARTBEAT_URL_ENV_VAR, "").strip()
    if not url:
        return False

    if detail:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}detail={urllib.parse.quote(detail)}"

    try:
        request = urllib.request.Request(url, method="GET", headers={"User-Agent": "BigMoneyDFS-canonical-shadow-heartbeat/1.0"})
        with urllib.request.urlopen(request, timeout=HEARTBEAT_TIMEOUT_SECONDS):
            pass
    except Exception:  # noqa: BLE001 -- a heartbeat failure must never break the real pipeline
        pass
    return True
