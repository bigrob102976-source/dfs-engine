from pathlib import Path

from bluecollar.persistence import save_bluecollar_snapshot
from evaluation.projection_source_comparison import compare_projection_sources
from evaluation.projection_source_loader import (
    build_hitter_projection_sources,
    build_pitcher_projection_sources,
    load_bluecollar_hitter_projections,
    load_bluecollar_pitcher_projections,
)

DATE = "2026-08-13"
DK_SLATE_ID = "dk-2026-08-13-0-main"


def _bc_player(mlb_player_id, position, usable_projection, match_status="matched", raw_projection=None):
    return {
        "bluecollar_local_id": f"local|{mlb_player_id}",
        "name": f"Player {mlb_player_id}",
        "team": "AAA",
        "position": position,
        "opponent": "BBB",
        "salary": 5000,
        "raw_projection": raw_projection if raw_projection is not None else usable_projection,
        "usable_projection": usable_projection,
        "match_status": match_status,
        "match_confidence": "name_team_exact",
        "mlb_player_id": mlb_player_id,
        "candidate_mlb_ids": [],
        "candidate_names": [],
    }


def _snapshot_doc(players):
    return {
        "slate_date": DATE,
        "dk_slate_id": DK_SLATE_ID,
        "bluecollar_slate_id": "bc-1",
        "bluecollar_slate_name": "1:05PM ET Main 8 Games",
        "bluecollar_updated": "08_13_26 12:00 PM",
        "retrieved_at": f"{DATE}T18:00:00+00:00",
        "slate_match_status": "matched",
        "slate_match_reason": None,
        "player_count": len(players),
        "matched_count": sum(1 for p in players if p["match_status"] == "matched"),
        "usable_projection_count": sum(1 for p in players if p["usable_projection"] is not None),
        "players": players,
    }


def _save(tmp_path, players):
    save_bluecollar_snapshot(_snapshot_doc(players), DATE, DK_SLATE_ID, "20260813T180000", output_root=tmp_path)


def test_bluecollar_pitcher_projections_empty_when_no_slate_id(tmp_path):
    _save(tmp_path, [_bc_player("608331", "P", 18.5)])
    points, path = load_bluecollar_pitcher_projections(DATE, None, bluecollar_root=tmp_path)
    assert points == {}
    assert path is None


def test_bluecollar_pitcher_projections_empty_when_no_snapshot(tmp_path):
    points, _ = load_bluecollar_pitcher_projections(DATE, DK_SLATE_ID, bluecollar_root=tmp_path)
    assert points == {}


def test_bluecollar_projections_split_by_position(tmp_path):
    _save(tmp_path, [
        _bc_player("608331", "P", 18.5),
        _bc_player("592450", "OF", 9.2),
    ])
    pitcher_points, _ = load_bluecollar_pitcher_projections(DATE, DK_SLATE_ID, bluecollar_root=tmp_path)
    hitter_points, _ = load_bluecollar_hitter_projections(DATE, DK_SLATE_ID, bluecollar_root=tmp_path)
    assert pitcher_points == {"608331": 18.5}
    assert hitter_points == {"592450": 9.2}


def test_bluecollar_projections_recognize_sp_rp_as_pitcher_positions(tmp_path):
    _save(tmp_path, [_bc_player("1", "SP", 20.0), _bc_player("2", "RP", 4.0)])
    pitcher_points, _ = load_bluecollar_pitcher_projections(DATE, DK_SLATE_ID, bluecollar_root=tmp_path)
    assert pitcher_points == {"1": 20.0, "2": 4.0}


def test_bluecollar_zero_value_rule_never_surfaces_a_null_usable_projection(tmp_path):
    # A BlueCollar-reported <=0/missing value is already None in
    # usable_projection by the time it's persisted (bluecollar/build.py's
    # own zero-value rule) -- the loader must never substitute
    # raw_projection back in.
    _save(tmp_path, [_bc_player("608331", "P", None, raw_projection=0.0)])
    points, _ = load_bluecollar_pitcher_projections(DATE, DK_SLATE_ID, bluecollar_root=tmp_path)
    assert points == {}


def test_bluecollar_excludes_unmatched_and_ambiguous_players(tmp_path):
    _save(tmp_path, [
        _bc_player("608331", "P", 18.5, match_status="matched"),
        _bc_player(None, "P", 12.0, match_status="unmatched"),
        _bc_player(None, "P", 9.0, match_status="ambiguous"),
    ])
    points, _ = load_bluecollar_pitcher_projections(DATE, DK_SLATE_ID, bluecollar_root=tmp_path)
    assert points == {"608331": 18.5}


def test_build_pitcher_sources_includes_bluecollar_when_slate_id_given(tmp_path):
    bluecollar_root = tmp_path / "bluecollar"
    _save(bluecollar_root, [_bc_player("608331", "P", 21.0)])

    sources = build_pitcher_projection_sources(
        DATE, predictions_root=tmp_path / "predictions", adjusted_root=tmp_path / "adjusted",
        ai_root=tmp_path / "ai", native_root=tmp_path / "native",
        dk_slate_id=DK_SLATE_ID, bluecollar_root=bluecollar_root,
    )
    assert sources == {"bluecollar": {"608331": 21.0}}


def test_build_hitter_sources_omits_bluecollar_when_no_slate_id_given(tmp_path):
    bluecollar_root = tmp_path / "bluecollar"
    _save(bluecollar_root, [_bc_player("592450", "OF", 9.2)])

    sources = build_hitter_projection_sources(
        DATE, predictions_root=tmp_path / "predictions", adjusted_root=tmp_path / "adjusted",
        ai_root=tmp_path / "ai", native_root=tmp_path / "native",
        bluecollar_root=bluecollar_root,
    )
    assert sources == {}


def test_bluecollar_flows_through_the_generic_comparison_with_bias(tmp_path):
    bluecollar_root = tmp_path / "bluecollar"
    _save(bluecollar_root, [_bc_player("608331", "P", 18.0), _bc_player("592450", "OF", 8.0)])

    pitcher_sources = build_pitcher_projection_sources(
        DATE, predictions_root=tmp_path / "predictions", adjusted_root=tmp_path / "adjusted",
        ai_root=tmp_path / "ai", native_root=tmp_path / "native",
        dk_slate_id=DK_SLATE_ID, bluecollar_root=bluecollar_root,
    )
    metrics = compare_projection_sources(pitcher_sources, {"608331": 22.0})
    bluecollar_metrics = next(m for m in metrics if m.source == "bluecollar")
    assert bluecollar_metrics.n == 1
    assert bluecollar_metrics.mae == 4.0
    assert bluecollar_metrics.bias == 4.0  # actual(22) - predicted(18)
