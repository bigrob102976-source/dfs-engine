"""Resolves which DFS salary provider to use for a given slate date.

Milestone 19: normal operation must use REAL DraftKings data whenever
it's available, and must never silently substitute mock data. Since
dfs/providers/base.py forbids a live/scraped DraftKings connection
(see that module's docstring), resolution is an automatic, date-aware
priority cascade rather than a single environment-variable selection:

  1. DraftKingsCsvProvider -- at least one real DraftKings salary CSV
     has been uploaded for `date` (dfs/providers/draftkings_csv_storage.py,
     via the dashboard's "Upload DraftKings CSV" flow).
  2. CsvImportPoolProvider -- a CSV-imported projection snapshot
     (Milestone 18, external_projections/csv_import/) with real salaries
     exists for `date`, even though it isn't DraftKings' own file.
  3. MockProvider -- ONLY if Mock Mode has been explicitly enabled
     (config/runtime_settings.py; OFF by default). Never used silently.

If none of the three apply, returns
(None, "No live DraftKings salary provider configured.", "unconfigured")
-- callers show this message verbatim and offer "Import CSV" /
"Enable Mock Mode", never a silent mock substitution.

DFS_SALARY_PROVIDER remains available as an explicit power-user/CI
override (e.g. forcing "mock" without touching the dashboard's Mock
Mode toggle, or forcing one specific provider by name) -- when set, it
skips the cascade entirely:

    DFS_SALARY_PROVIDER=<provider name>     e.g. "mock", "draftkings_csv"
    DFS_PROVIDER_API_KEY=<key>              only required by providers that need one
"""

import os
from typing import Callable, Dict, Optional, Tuple

from config.runtime_settings import is_mock_mode_enabled
from dfs.providers.base import DFSSalaryProvider, ProviderUnavailableError
from dfs.providers.csv_import_pool_provider import CsvImportPoolProvider
from dfs.providers.draftkings_csv_provider import DraftKingsCsvProvider
from dfs.providers.draftkings_unofficial_provider import DraftKingsUnofficialProvider
from dfs.providers.mock_provider import MockProvider

PROVIDER_FACTORIES: Dict[str, Callable[[], DFSSalaryProvider]] = {
    "mock": MockProvider,
    "draftkings_csv": DraftKingsCsvProvider,
    "csv_import_pool": CsvImportPoolProvider,
    # Milestone 31.2: registered ONLY for the explicit
    # DFS_SALARY_PROVIDER=draftkings_unofficial override below --
    # deliberately NEVER added to the automatic cascade in
    # get_configured_provider() beneath. It also refuses to run at all
    # unless DK_UNOFFICIAL_ENABLED=true (see that provider's own
    # is_enabled() check) -- two independent, explicit opt-ins.
    "draftkings_unofficial": DraftKingsUnofficialProvider,
}

NO_PROVIDER_CONFIGURED_MESSAGE = "No live DraftKings salary provider configured."


def get_configured_provider(date: str) -> Tuple[Optional[DFSSalaryProvider], Optional[str], str]:
    """Returns (provider, reason, source).

    `source` is one of:
      - "explicit": DFS_SALARY_PROVIDER named the result (successfully
        or not) -- always wins over the automatic cascade below.
      - "real_dk_csv": a real, user-uploaded DraftKings CSV was found
        for `date`.
      - "csv_import_pool": no real DK CSV, but a usable CSV-imported
        projection snapshot was found for `date`.
      - "mock_explicit": neither real source was available AND Mock
        Mode is explicitly enabled.
      - "unconfigured": nothing is available -- `provider` is None.
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

    dk_csv = DraftKingsCsvProvider()
    try:
        dk_csv.get_slate(date)
        return dk_csv, None, "real_dk_csv"
    except ProviderUnavailableError:
        pass

    csv_pool = CsvImportPoolProvider()
    try:
        csv_pool.get_slate(date)
        return csv_pool, None, "csv_import_pool"
    except ProviderUnavailableError:
        pass

    if is_mock_mode_enabled():
        return MockProvider(), None, "mock_explicit"

    return None, NO_PROVIDER_CONFIGURED_MESSAGE, "unconfigured"
