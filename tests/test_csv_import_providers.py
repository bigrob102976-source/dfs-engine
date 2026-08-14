from external_projections.csv_import.providers import IMPORT_PROVIDERS, is_known_provider, provider_label


def test_all_required_providers_present():
    keys = {p.key for p in IMPORT_PROVIDERS}
    assert keys == {"bluecollar", "fantasycruncher", "sabersim", "thebat", "stokastic", "rotogrinders", "custom_csv"}


def test_provider_label_known():
    assert provider_label("bluecollar") == "BlueCollar DFS"
    assert provider_label("custom_csv") == "Custom CSV"


def test_provider_label_unknown_is_none():
    assert provider_label("not_a_provider") is None


def test_is_known_provider():
    assert is_known_provider("sabersim") is True
    assert is_known_provider("nonsense") is False
