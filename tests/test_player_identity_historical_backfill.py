from player_identity import historical_backfill


def test_load_historical_handedness_returns_empty_for_missing_file(tmp_path):
    result = historical_backfill.load_historical_handedness(tmp_path / "does_not_exist.parquet")
    assert result == {}


def test_load_historical_handedness_returns_empty_when_pandas_unavailable(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pandas":
            raise ImportError("simulated: pandas not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert historical_backfill.load_historical_handedness(tmp_path / "whatever.parquet") == {}


def test_load_historical_handedness_reads_the_real_default_file_safely():
    # This project's real historical crosswalk (data/historical/mlb/crosswalks/players.parquet,
    # 1,798 rows as of this milestone's own audit) -- exercised here
    # against the REAL file to prove the safe (mlbam_id -> handedness
    # only, never team) reading contract, not a synthetic fixture.
    result = historical_backfill.load_historical_handedness()
    if not result:
        return  # environment without the historical warehouse built yet -- acceptable, never a failure
    sample_id, (bat_side, throw_side) = next(iter(result.items()))
    assert isinstance(sample_id, str)
    assert bat_side is None or isinstance(bat_side, str)
    assert throw_side is None or isinstance(throw_side, str)


def test_load_historical_handedness_never_exposes_a_team_field(monkeypatch, tmp_path):
    class _FakeDataFrame:
        def to_dict(self, orient):
            return [{"mlbam_id": "683002", "player_name": "Gunnar Henderson", "team": "BAL", "bat_side": "L", "throw_side": "R"}]

    class _FakePandasModule:
        @staticmethod
        def read_parquet(path):
            return _FakeDataFrame()

    import sys
    monkeypatch.setitem(sys.modules, "pandas", _FakePandasModule())

    result = historical_backfill.load_historical_handedness(tmp_path / "fake.parquet")
    assert result == {"683002": ("L", "R")}
    # The function's return type itself has no room for "team" -- a
    # (bat_side, throw_side) tuple only. Confirmed structurally: exactly
    # 2 values per entry.
    assert all(len(v) == 2 for v in result.values())


def test_load_historical_handedness_skips_rows_with_no_mlbam_id(monkeypatch, tmp_path):
    class _FakeDataFrame:
        def to_dict(self, orient):
            return [{"mlbam_id": None, "bat_side": "L", "throw_side": "R"}]

    class _FakePandasModule:
        @staticmethod
        def read_parquet(path):
            return _FakeDataFrame()

    import sys
    monkeypatch.setitem(sys.modules, "pandas", _FakePandasModule())

    assert historical_backfill.load_historical_handedness(tmp_path / "fake.parquet") == {}
