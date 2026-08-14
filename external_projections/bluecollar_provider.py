"""Placeholder for a future BlueCollar DFS projection provider.

Milestone 17 status: the user has REQUESTED BlueCollar API access but
has NOT received credentials or API documentation yet. This class
exists purely so that once official information arrives, wiring it up
is a small, contained change -- see "TO ACTIVATE THIS PROVIDER" below.

IT DOES NOT AND MUST NOT:
  - make any network request,
  - guess an API base URL or endpoint path,
  - guess a request/response schema,
  - automate a BlueCollar login,
  - scrape BlueCollar's website.

`_DOCUMENTATION_AVAILABLE` is hardcoded False and is the real gate --
is_configured() returns False because of it regardless of whether
BLUECOLLAR_API_KEY / BLUECOLLAR_API_BASE_URL happen to be set in the
environment, since even a present API key is useless without knowing
what to call. The dashboard is expected to render this as
"WAITING FOR API ACCESS", never as an error state.

TO ACTIVATE THIS PROVIDER, once BlueCollar provides real documentation:

  1. Set `_DOCUMENTATION_AVAILABLE = True`.
  2. Implement `list_slates()` / `get_projections()` against BlueCollar's
     ACTUAL documented endpoints (never guessed ones) -- normalizing
     their response into ExternalSlateInfo / ExternalProjectionPlayer,
     exactly like external_projections/mock_provider.py demonstrates the
     normalization shape for.
  3. Set the environment variables (never committed):
       EXTERNAL_PROJECTION_PROVIDER=bluecollar
       BLUECOLLAR_API_KEY=<the real key>
       BLUECOLLAR_API_BASE_URL=<the real, documented base URL>
"""

from typing import List

from external_projections.base import (
    ProjectionProvider,
    ProjectionProviderNotConfiguredError,
)
from external_projections.models import ExternalProjectionPlayer, ExternalSlateInfo

# Deliberately hardcoded -- see module docstring. This is not read from
# an environment variable because no environment variable can supply
# what's actually missing: the documented API contract itself.
_DOCUMENTATION_AVAILABLE = False

_NOT_CONFIGURED_MESSAGE = (
    "BlueCollar DFS is not connected yet -- official API documentation and "
    "credentials have not been provided. Set BLUECOLLAR_API_KEY and "
    "BLUECOLLAR_API_BASE_URL once they exist, then implement "
    "BlueCollarProvider.list_slates()/get_projections() against BlueCollar's "
    "documented endpoints (see this module's docstring)."
)


class BlueCollarProvider(ProjectionProvider):
    """Reserved, disabled BlueCollar DFS projection provider. See module
    docstring -- this class intentionally does nothing network-related
    yet."""

    name = "bluecollar"
    is_mock = False

    def provider_name(self) -> str:
        return "BlueCollar DFS"

    def is_configured(self) -> bool:
        return _DOCUMENTATION_AVAILABLE

    def list_slates(self, date: str, sport: str = "MLB", site: str = "draftkings") -> List[ExternalSlateInfo]:
        raise ProjectionProviderNotConfiguredError(_NOT_CONFIGURED_MESSAGE)

    def get_projections(self, slate_id: str) -> List[ExternalProjectionPlayer]:
        raise ProjectionProviderNotConfiguredError(_NOT_CONFIGURED_MESSAGE)
