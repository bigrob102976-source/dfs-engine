"""Resolves which EXTERNAL PROJECTION provider is configured, from an
environment variable only -- never hardcoded credentials, never read
from a file checked into the repo.

    EXTERNAL_PROJECTION_PROVIDER=<provider name>   e.g. "mock" or "bluecollar"

Unlike dfs/providers/config.py's DFS salary provider resolution, there
is deliberately NO automatic fallback here: external projections are a
purely additive comparison/adjustment layer, not something the
optimizer needs to function (Big Money Independent always works with
zero external configuration). If EXTERNAL_PROJECTION_PROVIDER is unset,
the resolved state is simply "no external provider configured" --
never an error, never a silent mock substitution.

Setting EXTERNAL_PROJECTION_PROVIDER=bluecollar resolves the
BlueCollarProvider class, but its own is_configured() still returns
False until real credentials AND documentation exist (see
external_projections/bluecollar_provider.py) -- this registry does not
and cannot make it usable early.
"""

import os
from typing import Callable, Dict, Optional, Tuple

from external_projections.base import ProjectionProvider
from external_projections.bluecollar_provider import BlueCollarProvider
from external_projections.mock_provider import MockExternalProvider

PROVIDER_FACTORIES: Dict[str, Callable[[], ProjectionProvider]] = {
    "mock": MockExternalProvider,
    "bluecollar": BlueCollarProvider,
}


def get_configured_provider() -> Tuple[Optional[ProjectionProvider], Optional[str], str]:
    """Returns (provider, reason, source).

    `source` is:
      - "unconfigured" when EXTERNAL_PROJECTION_PROVIDER is unset/blank
        (provider is always None in this case -- this is the default,
        expected state today).
      - "explicit" when EXTERNAL_PROJECTION_PROVIDER named a provider,
        whether or not that provider is actually usable yet (`provider`
        is non-None but `provider.is_configured()` may still be False,
        e.g. bluecollar today -- callers must check both).
      - "unknown" when EXTERNAL_PROJECTION_PROVIDER named something not
        in PROVIDER_FACTORIES (provider is None, reason explains why).
    """
    name = (os.environ.get("EXTERNAL_PROJECTION_PROVIDER") or "").strip().lower()

    if not name:
        return None, None, "unconfigured"

    factory = PROVIDER_FACTORIES.get(name)
    if factory is None:
        return None, f"EXTERNAL_PROJECTION_PROVIDER={name!r} is not a recognized provider. Supported: {sorted(PROVIDER_FACTORIES)}.", "unknown"

    return factory(), None, "explicit"
