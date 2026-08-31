"""NFL M4 -- the Big Money Native projection provider interface.

Mirrors external_projections/base.py's ABC pattern -- one standard
interface, so nothing downstream (the merge step, the optimizer) needs
to know which concrete implementation produced a projection. Unlike
external_projections/base.py, this interface's ONLY intended
implementation is Big Money's own first-party model (see this
milestone's product decision: FantasyPros/BlueCollar are external
benchmarks, never a production NFL projection source, and never
implement this interface).

BigMoneyNativeNflProvider is a deliberately honest stub for M4: no real
NFL projection model exists yet (that's NFL M5+ research work), so
get_projections() always raises NflProjectionProviderNotConfiguredError
rather than fabricating a number, guessing from salary, or returning an
empty-but-successful list that a caller might mistake for "zero
players project positively." A future real model implementation slots
into this exact same interface with no changes needed elsewhere.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from nfl.projection_models import NflProjectionRecord


class NflProjectionProviderNotConfiguredError(RuntimeError):
    """No real model/projections exist yet for this provider -- a
    normal, expected state (true for BigMoneyNativeNflProvider until a
    real model is trained), not a failure. Distinct from
    NflProjectionProviderUnavailableError: this means "there is
    deliberately nothing to fetch yet", not "we tried and it failed"."""


class NflProjectionProviderUnavailableError(RuntimeError):
    """The provider is configured but unreachable/erroring."""


class NflProjectionProvider(ABC):
    name: str = "unnamed_nfl_projection_provider"

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name for display (e.g. 'Big Money Native')."""
        raise NotImplementedError

    def provider_version(self) -> Optional[str]:
        """Optional model/provider version. None if not yet meaningful."""
        return None

    @abstractmethod
    def is_configured(self) -> bool:
        """False whenever this provider has nothing real to offer yet.
        Never raises; callers check this BEFORE calling get_projections()."""
        raise NotImplementedError

    @abstractmethod
    def get_projections(self, draft_group_id: int, slate_date: str) -> List[NflProjectionRecord]:
        """Every real projection this provider has for this DraftGroup.
        Raises NflProjectionProviderNotConfiguredError /
        NflProjectionProviderUnavailableError on failure -- never
        returns fabricated data, and never returns records with a
        guessed/derived projection value."""
        raise NotImplementedError


class BigMoneyNativeNflProvider(NflProjectionProvider):
    """M4's honest placeholder: the interface Big Money's real NFL model
    will eventually implement, wired all the way through to the
    optimizer, but with no real model behind it yet. Always reports
    is_configured() == False and get_projections() always raises --
    this is the correct, truthful state until NFL M5+ produces a real
    model, not a bug to work around."""

    name = "big_money_native_nfl"

    def __init__(self, model_version: Optional[str] = None):
        self._model_version = model_version

    def provider_name(self) -> str:
        return "Big Money Native"

    def provider_version(self) -> Optional[str]:
        return self._model_version

    def is_configured(self) -> bool:
        return False

    def get_projections(self, draft_group_id: int, slate_date: str) -> List[NflProjectionRecord]:
        raise NflProjectionProviderNotConfiguredError(
            f"No Big Money Native NFL projection model exists yet (DraftGroup {draft_group_id}, {slate_date}). "
            f"This is expected until NFL M5+ ships a real trained model -- never falls back to salary, "
            f"FantasyPros, BlueCollar, or a synthetic value."
        )
