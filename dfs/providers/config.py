"""Resolves which DFS salary provider to use for a given slate date.

Milestone M1: DraftKings Unofficial (draftkings_unofficial/,
dfs/providers/draftkings_unofficial_provider.py) is the PERMANENT
default DraftKings slate source for automatic production use -- no
manual CSV upload and no provider-selection override are required for
normal operation. Resolution is a short, date-aware cascade:

  1. DFS_SALARY_PROVIDER, if set -- an explicit power-user/CI override
     that always wins, e.g. forcing "mock", "draftkings_csv", or
     "csv_import_pool" for local development, historical CSV import, or
     testing. Not required for normal production use.
  2. Mock Mode, if explicitly enabled (config/runtime_settings.py; OFF
     by default, flipped only via the dashboard). This is checked BEFORE
     DraftKings Unofficial is even attempted, and its outcome never
     depends on whether DraftKings Unofficial would have succeeded --
     it is a standing, human-flipped dev/test override, structurally
     identical in spirit to DFS_SALARY_PROVIDER above, never an
     automatic fallback triggered by a live-provider failure.
  3. DraftKingsUnofficialProvider -- the real, live default. If this
     fails for any reason (its own DK_UNOFFICIAL_ENABLED kill switch,
     no active slate, endpoint failure, structural validation failure,
     etc.), that failure is surfaced directly as "unconfigured" with the
     real reason. There is NO automatic fallback to a DraftKings CSV or
     to Mock Mode -- CSV import remains available ONLY via the explicit
     DFS_SALARY_PROVIDER override above, for legitimate manual/
     historical/import/test use, never as a silent substitute for a
     live-provider failure.

If none of the above apply, returns
(None, "No live DraftKings salary provider configured.", "unconfigured")
-- callers show this message (or DraftKings Unofficial's own real
failure reason) verbatim, never a silent CSV or mock substitution.

    DFS_SALARY_PROVIDER=<provider name>     e.g. "mock", "draftkings_csv"
    DFS_PROVIDER_API_KEY=<key>              only required by providers that need one
"""

import os
from typing import Callable, Dict, Optional, Tuple

from config.runtime_settings import is_mock_mode_enabled
from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.csv_import_pool_provider import CsvImportPoolProvider
from dfs.providers.draftkings_csv_provider import DraftKingsCsvProvider
from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider
from dfs.providers.mock_provider import MockProvider

PROVIDER_FACTORIES: Dict[str, Callable[[], DFSSalaryProvider]] = {
    "mock": MockProvider,
    "draftkings_csv": DraftKingsCsvProvider,
    "csv_import_pool": CsvImportPoolProvider,
    # Milestone M1: this is the permanent DEFAULT provider (see the
    # automatic cascade below) -- also registered here so it remains
    # explicitly selectable via DFS_SALARY_PROVIDER, for parity with
    # every other provider and for CI/testing convenience.
    "draftkings_unofficial": DraftKingsUnofficialProvider,
}

NO_PROVIDER_CONFIGURED_MESSAGE = "No live DraftKings salary provider configured."


def get_configured_provider(date: str, capture: Optional[Callable[[str, str], None]] = None) -> Tuple[Optional[DFSSalaryProvider], Optional[str], str]:
    """Returns (provider, reason, source).

    `capture` is purely additive (default None -- zero behavior change
    for every existing caller). M3 finding: this function's own internal
    probe call below (`dk_unofficial.get_slate(date)`) is genuinely the
    FIRST real network fetch in a normal fetch_dfs_slate.py run --
    draftkings_unofficial/cache.py's shared, process-global TTL cache
    means a caller's own SUBSEQUENT get_slate() call for the same date/
    sport/site is a cache hit that never touches the network again (by
    design, to avoid doubling real DK traffic -- see the comment below).
    That also means a `capture` callback passed only to the caller's
    later get_slate() call would NEVER fire (confirmed live: a worker
    cycle logged EmptyRawCaptureError for every real slate because of
    exactly this). Passing `capture` HERE, to the actual first real
    fetch, is the fix -- scripts/fetch_dfs_slate.py now does this.

    `source` is one of:
      - "explicit": DFS_SALARY_PROVIDER named the result (successfully
        or not) -- always wins over the automatic cascade below.
      - "mock_explicit": no explicit override, but Mock Mode is
        explicitly enabled -- checked before DraftKings Unofficial is
        even attempted (see module docstring for why).
      - "draftkings_unofficial_live": the permanent default provider
        successfully resolved a real slate for `date`.
      - "unconfigured": DraftKings Unofficial failed, was disabled, or
        had nothing for `date`, and Mock Mode is off -- `provider` is
        None and `reason` carries the real failure detail.
    """
    name = (os.environ.get("DFS_SALARY_PROVIDER") or "").strip().lower()
    if name:
        factory = PROVIDER_FACTORIES.get(name)
        if factory is None:
            return None, f"DFS_SALARY_PROVIDER={name!r} is not a recognized provider. Supported: {sorted(PROVIDER_FACTORIES)}.", "explicit"
        provider = factory()
        if provider.requires_api_key and not os.environ.get("DFS_PROVIDER_API_KEY"):
            return None, f"Provider {name!r} requires DFS_PROVIDER_API_KEY, which is not set.", "explicit"
        return provider, None, "explicit"

    if is_mock_mode_enabled():
        return MockProvider(), None, "mock_explicit"

    dk_unofficial = DraftKingsUnofficialProvider()
    try:
        # Milestone M1: this is a real live-endpoint call, not a cheap
        # local file check like the CSV providers this replaced -- but
        # draftkings_unofficial/cache.py's in-process TTL cache (30-3600s
        # per category) makes it safe: this probe and the caller's own
        # subsequent get_slate() call for the same date/sport/site land
        # within the same process and well inside those TTLs, so this
        # never doubles real network traffic to DraftKings.
        # `capture` omitted entirely (not passed as capture=None) when
        # unset, so this call signature is byte-for-byte identical to
        # before this parameter existed for any test/caller whose fake
        # DraftKingsUnofficialProvider stand-in has a narrower get_slate()
        # signature -- mirrors draftkings_unofficial/collector.py's
        # identical _capture_kwargs() convention.
        probe_kwargs = {"capture": capture} if capture is not None else {}
        dk_unofficial.get_slate(date, **probe_kwargs)
        return dk_unofficial, None, "draftkings_unofficial_live"
    except (ProviderUnavailableError, ProviderNoSlateError) as exc:
        return None, f"{NO_PROVIDER_CONFIGURED_MESSAGE} DraftKings Unofficial: {exc}", "unconfigured"
