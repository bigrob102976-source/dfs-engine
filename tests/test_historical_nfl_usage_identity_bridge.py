"""NFL M6C -- targeted tests for historical_nfl/usage_identity_bridge.py."""

import polars as pl

from historical_nfl.usage_identity_bridge import build_pfr_to_gsis_bridge, resolve_gsis_for_snap_row, summarize_bridge_coverage


def test_build_bridge_from_real_shaped_playerids():
    df = pl.DataFrame({"gsis_id": ["00-0001", "00-0002", None], "pfr_id": ["SmitJo00", None, "DoeJa00"]})
    bridge = build_pfr_to_gsis_bridge(df)
    assert bridge == {"SmitJo00": "00-0001"}  # only rows with BOTH ids present


def test_resolve_gsis_for_snap_row():
    bridge = {"SmitJo00": "00-0001"}
    assert resolve_gsis_for_snap_row("SmitJo00", bridge) == "00-0001"
    assert resolve_gsis_for_snap_row("Unknown00", bridge) is None
    assert resolve_gsis_for_snap_row(None, bridge) is None


def test_summarize_bridge_coverage():
    bridge = {"a": "00-0001", "b": "00-0002"}
    summary = summarize_bridge_coverage(["a", "b", "c"], bridge)
    assert summary == {"total": 3, "resolved": 2, "unresolved": 1, "resolution_rate_percent": 66.7}


def test_summarize_bridge_coverage_empty_input():
    assert summarize_bridge_coverage([], {}) == {"total": 0, "resolved": 0, "unresolved": 0, "resolution_rate_percent": 0.0}


def test_duplicate_pfr_id_keeps_first_seen_not_last():
    df = pl.DataFrame({"gsis_id": ["00-0001", "00-0002"], "pfr_id": ["SmitJo00", "SmitJo00"]})
    bridge = build_pfr_to_gsis_bridge(df)
    assert bridge["SmitJo00"] == "00-0001"
