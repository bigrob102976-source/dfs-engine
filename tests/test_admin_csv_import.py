"""BREAK-GLASS ADMIN CSV UPLOAD -- canonical_ingestion/admin_csv_import.py.

Mirrors tests/test_canonical_ingestion_pipeline.py's own LocalArtifactStorage-
rooted-at-a-temp-dir convention (never touches the real repo's artifact
tree) and dfs/providers/models.py fixture-building style, but proves the
ONE genuine difference from the automatic-fetch path: slateDate is the
admin's own explicit input, never derived from (missing) game-start
instants -- and that this is never silently faked."""

import pytest

from canonical_ingestion import admin_csv_import as admin_csv_import_module
from canonical_ingestion.admin_csv_import import (
    ADMIN_CSV_FIRST_GAME_START_NOTE,
    AdminCsvNormalizationError,
    build_canonical_artifact_from_admin_csv,
    build_normalized_from_admin_csv,
)
from canonical.models import VALIDATION_STATE_REJECTED, VALIDATION_STATE_VALID
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo
from dfs.providers.source_provenance import OFFICIAL_USER_UPLOAD, SYNTHETIC_VALIDATION
from research.artifact_storage import LocalArtifactStorage


def _slate_info(provenance=OFFICIAL_USER_UPLOAD, realism_findings=None):
    return ProviderSlateInfo(
        slate_id="dkcsv-main-2026-09-04", slate_name="Main", site="draftkings", sport="MLB",
        start_time=None, game_count=1, game_ids=["g1"], player_count=1,
        source_provenance=provenance, realism_findings=realism_findings or [],
    )


def _player(external_player_id="1", name="Flex Player"):
    # CSV players never have a real start_time -- see
    # dfs/providers/draftkings_csv_provider.py, which always sets None.
    return ProviderPlayer(
        external_player_id=external_player_id, name=name, team="BOS", opponent="TOR", game="TOR@BOS",
        salary=4500, position_eligibility=["1B", "OF"], slate_id="dkcsv-main-2026-09-04", slate_name="Main",
        start_time=None, source="draftkings_csv", retrieved_at="2026-09-04T18:00:00Z",
    )


@pytest.fixture
def patched_storage(tmp_path, monkeypatch):
    storage = LocalArtifactStorage(tmp_path)
    monkeypatch.setattr(admin_csv_import_module, "resolve_artifact_storage", lambda root: storage)
    monkeypatch.setattr(admin_csv_import_module, "load_name_team_index", lambda: {})
    return storage


class TestBuildCanonicalArtifactFromAdminCsv:
    def test_refuses_empty_slate_date(self):
        with pytest.raises(AdminCsvNormalizationError, match="slate_date"):
            build_canonical_artifact_from_admin_csv(
                sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
                provider_players=[_player()], internal_slate_id="s1", slate_date="", raw_hash=None, name_team_index={},
            )

    def test_refuses_empty_player_list(self):
        with pytest.raises(AdminCsvNormalizationError, match="No players"):
            build_canonical_artifact_from_admin_csv(
                sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
                provider_players=[], internal_slate_id="s1", slate_date="2026-09-04", raw_hash=None, name_team_index={},
            )

    def test_uses_the_admin_supplied_slate_date_verbatim_never_derived(self):
        artifact = build_canonical_artifact_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], internal_slate_id="s1", slate_date="2026-09-04", raw_hash="abc", name_team_index={},
        )
        assert artifact.slate.slate_date == "2026-09-04"

    def test_first_game_start_utc_is_never_fabricated_from_a_player(self):
        # Confirms firstGameStartUtc is the import's own processing
        # timestamp, not something invented to look like a real game
        # start pulled from a player/CSV row (which never has one).
        artifact = build_canonical_artifact_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], internal_slate_id="s1", slate_date="2026-09-04", raw_hash="abc",
            name_team_index={}, fetched_at="2026-09-04T18:30:00Z",
        )
        assert artifact.slate.first_game_start_utc == "2026-09-04T18:30:00Z"
        assert ADMIN_CSV_FIRST_GAME_START_NOTE in artifact.slate.validation_findings

    def test_trusted_provenance_yields_valid_state(self):
        artifact = build_canonical_artifact_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(provenance=OFFICIAL_USER_UPLOAD),
            provider_players=[_player()], internal_slate_id="s1", slate_date="2026-09-04", raw_hash="abc", name_team_index={},
        )
        assert artifact.slate.validation_state == VALIDATION_STATE_VALID

    def test_untrusted_provenance_yields_rejected_state_never_silently_valid(self):
        artifact = build_canonical_artifact_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv",
            slate_info=_slate_info(provenance=SYNTHETIC_VALIDATION, realism_findings=["looks fake"]),
            provider_players=[_player()], internal_slate_id="s1", slate_date="2026-09-04", raw_hash="abc", name_team_index={},
        )
        assert artifact.slate.validation_state == VALIDATION_STATE_REJECTED
        assert "looks fake" in artifact.slate.validation_findings

    def test_normalized_hash_is_computed_and_deterministic(self):
        a1 = build_canonical_artifact_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], internal_slate_id="s1", slate_date="2026-09-04", raw_hash="abc",
            name_team_index={}, fetched_at="2026-09-04T18:30:00Z",
        )
        a2 = build_canonical_artifact_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], internal_slate_id="s2", slate_date="2026-09-04", raw_hash="abc",
            name_team_index={}, fetched_at="2026-09-04T18:30:00Z",
        )
        assert a1.normalized_hash == a2.normalized_hash  # internal_slate_id is not part of the hash


class TestBuildNormalizedFromAdminCsv:
    def test_successful_import_writes_raw_and_normalized_and_reports_ok(self, patched_storage):
        result = build_normalized_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], slate_date="2026-09-04", original_filename="DKSalaries.csv",
            csv_text="Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\n",
        )
        assert result.ok is True
        assert result.player_count == 1
        assert result.unresolved_count == 1
        assert result.raw_manifest_key is not None
        assert "2026-09-04" in result.raw_manifest_key
        assert "draftkings_csv" in result.raw_manifest_key
        assert result.normalized_key is not None

    def test_raw_capture_is_the_real_uploaded_csv_bytes_not_a_reserialization(self, patched_storage):
        real_csv_text = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame\nOF,Flex Player (1),Flex Player,1,OF,4500,TOR@BOS,BOS,10.0\n"
        result = build_normalized_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], slate_date="2026-09-04", original_filename="DKSalaries.csv", csv_text=real_csv_text,
        )
        raw_files = [k for k in patched_storage.list_files(f"raw/MLB/2026-09-04/draftkings_csv/dkcsv-main-2026-09-04", prefix="", ext=".json") if "manifest" not in k]
        assert len(raw_files) == 1
        raw_bytes = patched_storage.read_bytes(raw_files[0])
        assert raw_bytes.decode("utf-8") == real_csv_text

    def test_never_raises_on_internal_failure_reports_instead(self, patched_storage, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("storage exploded")
        monkeypatch.setattr(admin_csv_import_module, "write_normalized_artifact", boom)

        result = build_normalized_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], slate_date="2026-09-04", original_filename="DKSalaries.csv", csv_text="x\n",
        )
        assert result.ok is False
        assert result.error_type == "RuntimeError"
        assert "storage exploded" in result.error

    def test_refuses_to_write_raw_capture_when_no_csv_text_given(self, patched_storage):
        # An empty csv_text still gets recorded as ONE entry (the upload
        # itself, even if it parses to zero rows) -- this proves the
        # RawCaptureRecorder path is genuinely exercised, not skipped.
        result = build_normalized_from_admin_csv(
            sport="MLB", site="draftkings", provider="draftkings_csv", slate_info=_slate_info(),
            provider_players=[_player()], slate_date="2026-09-04", original_filename="DKSalaries.csv", csv_text="",
        )
        assert result.ok is True
        assert result.raw_manifest_key is not None
