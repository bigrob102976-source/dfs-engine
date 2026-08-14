from config.runtime_settings import is_mock_mode_enabled, set_mock_mode_enabled


def test_mock_mode_defaults_to_disabled_when_no_settings_file(tmp_path):
    path = tmp_path / "mock_mode.json"
    assert is_mock_mode_enabled(settings_path=path) is False


def test_mock_mode_defaults_to_disabled_for_a_corrupt_settings_file(tmp_path):
    path = tmp_path / "mock_mode.json"
    path.write_text("not valid json", encoding="utf-8")
    assert is_mock_mode_enabled(settings_path=path) is False


def test_set_mock_mode_enabled_persists(tmp_path):
    path = tmp_path / "nested" / "mock_mode.json"
    set_mock_mode_enabled(True, settings_path=path)
    assert is_mock_mode_enabled(settings_path=path) is True

    set_mock_mode_enabled(False, settings_path=path)
    assert is_mock_mode_enabled(settings_path=path) is False


def test_set_mock_mode_enabled_creates_parent_directory(tmp_path):
    path = tmp_path / "does" / "not" / "exist" / "mock_mode.json"
    set_mock_mode_enabled(True, settings_path=path)
    assert path.exists()
