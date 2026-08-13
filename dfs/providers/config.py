"""Resolves which DFS salary provider is configured, from environment
variables only -- never hardcoded credentials, never read from a file
checked into the repo.

    DFS_SALARY_PROVIDER=<provider name>     e.g. "mock"
    DFS_PROVIDER_API_KEY=<key>              only required by providers that need one

No live third-party DFS-salary API is configured or credentialed in
this environment. `mock` (dfs/providers/mock_provider.py) is the only
provider registered today -- it builds slate/player structure from the
REAL Research Package (real names, teams, positions, game times) but
assigns deterministic, clearly-labeled MOCK salaries, since no real DK
pricing source is available. Wiring up a genuine live provider (e.g. a
paid third-party odds/DFS-data API) would mean:

  1. Registering a new DFSSalaryProvider subclass in PROVIDER_FACTORIES
     below that calls that provider's documented, credentialed API.
  2. Setting DFS_SALARY_PROVIDER to its registered name.
  3. Setting DFS_PROVIDER_API_KEY (and any other required secret) as an
     environment variable -- never committed, never logged, never sent
     to the browser (see dashboard/lib/orchestrator/pythonRunner.ts,
     which passes environment variables to the Python subprocess but
     never returns them in any API response).

Milestone 15: the dashboard must work immediately on startup without
any manual terminal configuration. Resolution priority is:

  1. An explicitly configured, valid provider (DFS_SALARY_PROVIDER set
     to a registered name, with DFS_PROVIDER_API_KEY if that provider
     requires one) -- always wins.
  2. DFS_SALARY_PROVIDER explicitly set but invalid (unrecognized name,
     or a required API key missing) -- this is a real misconfiguration
     and is reported as such (None, reason, "explicit"), never silently
     replaced by the mock fallback -- masking a typo would be worse than
     surfacing it.
  3. DFS_SALARY_PROVIDER unset or empty -- automatically falls back to
     the mock provider (source="automatic_fallback") so the dashboard
     and optimizer work immediately without any PowerShell/terminal
     setup. This module still never raises for this case, exactly as
     before -- callers (scripts/fetch_dfs_slate.py,
     scripts/list_dfs_slates.py) branch on the returned status/source,
     never on an exception.
"""

import os
from typing import Callable, Dict, Optional, Tuple

from dfs.providers.base import DFSSalaryProvider
from dfs.providers.mock_provider import MockProvider

PROVIDER_FACTORIES: Dict[str, Callable[[], DFSSalaryProvider]] = {
    "mock": MockProvider,
}

DEFAULT_FALLBACK_PROVIDER_KEY = "mock"


def get_configured_provider() -> Tuple[Optional[DFSSalaryProvider], Optional[str], str]:
    """Returns (provider, reason, source).

    `source` is "explicit" when DFS_SALARY_PROVIDER named the result
    (successfully or not), or "automatic_fallback" when nothing was
    configured and the mock provider was used as the default. Explicit
    configuration always takes priority over the automatic fallback --
    see the module docstring for the full resolution order."""
    name = (os.environ.get("DFS_SALARY_PROVIDER") or "").strip().lower()

    if not name:
        provider = PROVIDER_FACTORIES[DEFAULT_FALLBACK_PROVIDER_KEY]()
        return provider, None, "automatic_fallback"

    factory = PROVIDER_FACTORIES.get(name)
    if factory is None:
        return None, f"DFS_SALARY_PROVIDER={name!r} is not a recognized provider. Supported: {sorted(PROVIDER_FACTORIES)}.", "explicit"

    provider = factory()
    if provider.requires_api_key and not os.environ.get("DFS_PROVIDER_API_KEY"):
        return None, f"Provider {name!r} requires DFS_PROVIDER_API_KEY, which is not set.", "explicit"

    return provider, None, "explicit"
