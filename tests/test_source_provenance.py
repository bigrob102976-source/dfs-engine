from dfs.providers.source_provenance import (
    AUTHORIZED_PROVIDER,
    DEVELOPMENT_MOCK,
    DRAFTKINGS_UNOFFICIAL_LIVE,
    OFFICIAL_USER_UPLOAD,
    SYNTHETIC_VALIDATION,
    TRUSTED_FOR_PRODUCTION,
    UNKNOWN,
    UNOFFICIAL_DEVELOPMENT_SOURCE,
    classify_source_provenance,
)
from dfs.providers.source_realism import RealismFinding, RealismReport, BLOCK, WARN


def _clean_report():
    return RealismReport(findings=[])


def _warned_report():
    return RealismReport(findings=[RealismFinding(WARN, "just a warning")])


def _blocked_report():
    return RealismReport(findings=[RealismFinding(BLOCK, "impossible pitcher count")])


def test_official_upload_provenance_is_trusted_when_realism_clean():
    assert classify_source_provenance(OFFICIAL_USER_UPLOAD, _clean_report()) == OFFICIAL_USER_UPLOAD
    assert OFFICIAL_USER_UPLOAD in TRUSTED_FOR_PRODUCTION


def test_official_upload_provenance_survives_warnings():
    # A WARN (e.g. a legitimate rare same-name collision) does not by
    # itself disqualify an otherwise-real upload.
    assert classify_source_provenance(OFFICIAL_USER_UPLOAD, _warned_report()) == OFFICIAL_USER_UPLOAD


def test_synthetic_cannot_masquerade_as_official_upload():
    # This IS the core guarantee: no matter what the ingestion mechanism
    # claims, a BLOCK-level realism finding always wins.
    assert classify_source_provenance(OFFICIAL_USER_UPLOAD, _blocked_report()) == SYNTHETIC_VALIDATION


def test_mock_cannot_masquerade_as_official_upload_either():
    # A mock provider claim also gets reclassified if its content somehow
    # fails realism checks -- the downgrade is content-driven, not
    # mechanism-driven.
    assert classify_source_provenance(DEVELOPMENT_MOCK, _blocked_report()) == SYNTHETIC_VALIDATION
    assert DEVELOPMENT_MOCK not in TRUSTED_FOR_PRODUCTION


def test_authorized_provider_is_trusted_for_production():
    assert classify_source_provenance(AUTHORIZED_PROVIDER, _clean_report()) == AUTHORIZED_PROVIDER
    assert AUTHORIZED_PROVIDER in TRUSTED_FOR_PRODUCTION


def test_unknown_provenance_is_never_trusted_for_production():
    assert classify_source_provenance(UNKNOWN, _clean_report()) == UNKNOWN
    assert UNKNOWN not in TRUSTED_FOR_PRODUCTION


def test_draftkings_unofficial_live_is_trusted_for_production_when_realism_clean():
    """Milestone 32.2B: once draftkings_unofficial's own structural
    validation has passed (see draftkings_unofficial_provider.py) and
    content realism is clean, DRAFTKINGS_UNOFFICIAL_LIVE is trusted for
    production -- the sole DK slate source per the explicit M32.2B
    architecture decision, no manual CSV step."""
    assert classify_source_provenance(DRAFTKINGS_UNOFFICIAL_LIVE, _clean_report()) == DRAFTKINGS_UNOFFICIAL_LIVE
    assert DRAFTKINGS_UNOFFICIAL_LIVE in TRUSTED_FOR_PRODUCTION


def test_draftkings_unofficial_live_still_downgrades_on_a_real_block():
    """Trust is earned per-slate, not by provider name alone -- a
    genuine BLOCK-level content finding (e.g. identity conflation) still
    downgrades this claim to SYNTHETIC_VALIDATION exactly like any other
    provenance claim."""
    assert classify_source_provenance(DRAFTKINGS_UNOFFICIAL_LIVE, _blocked_report()) == SYNTHETIC_VALIDATION


def test_bare_unofficial_development_source_is_not_trusted_for_production():
    # The un-upgraded claim (structural validation not run/not passed)
    # stays untrusted, distinct from the validated DRAFTKINGS_UNOFFICIAL_LIVE.
    assert UNOFFICIAL_DEVELOPMENT_SOURCE not in TRUSTED_FOR_PRODUCTION
