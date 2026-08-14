"""The provider list the CSV Import wizard's Step 1 dropdown offers
(Milestone 18). This is purely a labeling/namespacing table for
CSV-sourced imports -- it does NOT create or alter any live-API
provider. "bluecollar" intentionally reuses the same provider key
external_projections/registry.py uses for the (still unconfigured)
BlueCollarProvider placeholder: a CSV-imported BlueCollar export and a
future live BlueCollar API fetch are the same provider from the
snapshot-storage point of view, and naturally coexist/supersede by
timestamp -- see external_projections/persistence.py. No BlueCollar API
code is touched by this module.
"""

from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass
class ImportProviderOption:
    key: str
    label: str

    def to_dict(self) -> dict:
        return asdict(self)


IMPORT_PROVIDERS: List[ImportProviderOption] = [
    ImportProviderOption("bluecollar", "BlueCollar DFS"),
    ImportProviderOption("fantasycruncher", "FantasyCruncher"),
    ImportProviderOption("sabersim", "SaberSim"),
    ImportProviderOption("thebat", "THE BAT"),
    ImportProviderOption("stokastic", "Stokastic"),
    ImportProviderOption("rotogrinders", "RotoGrinders"),
    ImportProviderOption("custom_csv", "Custom CSV"),
]

_BY_KEY = {p.key: p for p in IMPORT_PROVIDERS}


def provider_label(key: str) -> Optional[str]:
    provider = _BY_KEY.get(key)
    return provider.label if provider else None


def is_known_provider(key: str) -> bool:
    return key in _BY_KEY
