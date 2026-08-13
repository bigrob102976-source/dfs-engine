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

This module deliberately never raises for the "nothing configured"
case -- that is the expected default state this milestone, and callers
(scripts/fetch_dfs_slate.py) are required to handle it as a normal,
reportable outcome ("DFS SALARIES: NOT CONNECTED"), not a crash.
"""

import os
from typing import Callable, Dict, Optional, Tuple

from dfs.providers.base import DFSSalaryProvider
from dfs.providers.mock_provider import MockProvider

PROVIDER_FACTORIES: Dict[str, Callable[[], DFSSalaryProvider]] = {
    "mock": MockProvider,
}


def get_configured_provider() -> Tuple[Optional[DFSSalaryProvider], Optional[str]]:
    """Returns (provider, None) if DFS_SALARY_PROVIDER names a
    registered, sufficiently-configured provider, else (None, reason)."""
    name = (os.environ.get("DFS_SALARY_PROVIDER") or "").strip().lower()
    if not name:
        return None, (
            "DFS_SALARY_PROVIDER is not set. Configure it to enable automatic salary ingestion "
            "(e.g. DFS_SALARY_PROVIDER=mock for local pipeline testing with mock/dev salary data)."
        )

    factory = PROVIDER_FACTORIES.get(name)
    if factory is None:
        return None, f"DFS_SALARY_PROVIDER={name!r} is not a recognized provider. Supported: {sorted(PROVIDER_FACTORIES)}."

    provider = factory()
    if provider.requires_api_key and not os.environ.get("DFS_PROVIDER_API_KEY"):
        return None, f"Provider {name!r} requires DFS_PROVIDER_API_KEY, which is not set."

    return provider, None
