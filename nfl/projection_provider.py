"""NFL M4 -- the Big Money Native projection provider interface.

Mirrors external_projections/base.py's ABC pattern -- one standard
interface, so nothing downstream (the merge step, the optimizer) needs
to know which concrete implementation produced a projection. Unlike
external_projections/base.py, this interface's ONLY intended
implementation is Big Money's own first-party model (see this
milestone's product decision: FantasyPros/BlueCollar are external
benchmarks, never a production NFL projection source, and never
implement this interface).

NFL M10: BigMoneyNativeNflProvider is now a REAL provider, backed by
historical_models/nfl_v1's trained models (offline inference only --
no Railway/live-website wiring yet, per M10's explicit scope). It never
falls back to salary, FantasyPros, BlueCollar, or a synthetic value: a
position with no trained artifact, or a player unresolvable to a real
GSIS identity, is simply absent from get_projections()'s result, never
assigned a guessed number. Still raises NflProjectionProviderNotConfiguredError
if literally no model artifacts exist at all (e.g. a fresh checkout
before NFL M10's training has ever been run locally)."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from historical_models.nfl_v1.config import DEFAULT_ARTIFACT_ROOT, MODEL_VERSION
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
    """NFL M10: real provider backed by historical_models/nfl_v1's
    trained, persisted models. is_configured() checks that at least one
    position's model.joblib actually exists on disk (or in object
    storage) before ever claiming to be usable."""

    name = "big_money_native_nfl"

    def __init__(self, model_version: Optional[str] = None, artifact_root: Path = DEFAULT_ARTIFACT_ROOT):
        self._model_version = model_version or MODEL_VERSION
        self._artifact_root = Path(artifact_root)

    def provider_name(self) -> str:
        return "Big Money Native"

    def provider_version(self) -> Optional[str]:
        return self._model_version

    def is_configured(self) -> bool:
        return any((self._artifact_root / pos.lower() / "v1" / "model.joblib").exists() for pos in ("qb", "rb", "wr", "te", "dst"))

    def get_projections(self, draft_group_id: int, slate_date: str) -> List[NflProjectionRecord]:
        if not self.is_configured():
            raise NflProjectionProviderNotConfiguredError(
                f"No Big Money Native NFL model artifacts found under {self._artifact_root} (DraftGroup {draft_group_id}, {slate_date}). "
                f"Run historical_models.nfl_v1.train locally first -- never falls back to salary, FantasyPros, BlueCollar, or a synthetic value."
            )
        from nfl.big_money_native_inference import generate_projections
        return generate_projections(draft_group_id, slate_date)
