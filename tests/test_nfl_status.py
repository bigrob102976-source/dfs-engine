"""NFL M14 -- targeted tests for nfl/status.py: real DK status
normalization and the default exclusion/warning policy."""

from nfl.status import (
    ACTIVE,
    DOUBTFUL,
    INACTIVE,
    IR,
    OUT,
    QUESTIONABLE,
    UNKNOWN,
    build_status_info,
    normalize_status,
)


def test_confirmed_real_dk_values_normalize_correctly():
    """These four exact strings were observed live in captured
    DraftGroup 151307 payloads (NFL M14 Phase 2 audit)."""
    assert normalize_status("None") == ACTIVE
    assert normalize_status("Q") == QUESTIONABLE
    assert normalize_status("OUT") == OUT
    assert normalize_status("IR") == IR


def test_none_python_value_means_active_never_unknown():
    assert normalize_status(None) == ACTIVE


def test_unrecognized_value_is_unknown_never_guessed():
    assert normalize_status("SOME_NEW_DK_CODE") == UNKNOWN


def test_doubtful_and_inactive_mapped_even_though_not_yet_observed_live():
    assert normalize_status("D") == DOUBTFUL
    assert normalize_status("INACTIVE") == INACTIVE


def test_out_excluded_by_default():
    info = build_status_info("OUT")
    assert info.excluded_by_default is True
    assert info.normalized_status == OUT


def test_inactive_and_ir_excluded_by_default():
    assert build_status_info("INACTIVE").excluded_by_default is True
    assert build_status_info("IR").excluded_by_default is True


def test_questionable_never_silently_excluded():
    info = build_status_info("Q")
    assert info.excluded_by_default is False
    assert info.warn is True


def test_active_never_flagged():
    info = build_status_info("None")
    assert info.excluded_by_default is False
    assert info.warn is False


def test_unknown_eligible_but_flagged():
    info = build_status_info("SOME_NEW_DK_CODE")
    assert info.excluded_by_default is False
    assert info.warn is True


def test_doubtful_visibly_warned_regardless_of_exclusion_policy():
    info = build_status_info("D")
    assert info.warn is True


def test_exclusion_policy_is_overridable():
    """NFL M14 Phase 10 -- product policy configurability."""
    info = build_status_info("D", exclude_overrides={DOUBTFUL: True})
    assert info.excluded_by_default is True


def test_raw_status_preserved_verbatim():
    info = build_status_info("Q")
    assert info.raw_status == "Q"
