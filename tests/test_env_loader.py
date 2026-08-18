import os

import pytest

from config.env_loader import load_dashboard_env


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SGO_TEST_KEY", raising=False)
    monkeypatch.delenv("SGO_TEST_ALREADY_SET", raising=False)
    yield


def test_loads_key_value_pairs_from_file(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("SGO_TEST_KEY=abc123\n", encoding="utf-8")

    load_dashboard_env(path=env_file)

    assert os.environ["SGO_TEST_KEY"] == "abc123"


def test_does_not_override_an_already_set_real_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("SGO_TEST_ALREADY_SET", "real-shell-value")
    env_file = tmp_path / ".env.local"
    env_file.write_text("SGO_TEST_ALREADY_SET=from-file\n", encoding="utf-8")

    load_dashboard_env(path=env_file)

    assert os.environ["SGO_TEST_ALREADY_SET"] == "real-shell-value"


def test_skips_blank_lines_and_comments(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("\n# a comment\nSGO_TEST_KEY=xyz\n\n# trailing comment\n", encoding="utf-8")

    load_dashboard_env(path=env_file)

    assert os.environ["SGO_TEST_KEY"] == "xyz"


def test_strips_surrounding_quotes(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text('SGO_TEST_KEY="quoted-value"\n', encoding="utf-8")

    load_dashboard_env(path=env_file)

    assert os.environ["SGO_TEST_KEY"] == "quoted-value"


def test_missing_file_is_a_safe_no_op(tmp_path):
    missing = tmp_path / "does-not-exist" / ".env.local"

    load_dashboard_env(path=missing)  # must not raise

    assert "SGO_TEST_KEY" not in os.environ


def test_ignores_malformed_lines_without_an_equals_sign(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("not-a-valid-line\nSGO_TEST_KEY=ok\n", encoding="utf-8")

    load_dashboard_env(path=env_file)

    assert os.environ["SGO_TEST_KEY"] == "ok"
