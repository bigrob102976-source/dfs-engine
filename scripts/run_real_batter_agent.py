"""CLI entry point: score REAL starting-lineup MLB hitters for a slate
date through the Batter Agent, enriched with real season/recent MLB
Stats, Statcast, platoon splits, and opposing-pitcher research context.

    Research Package -> Batter Input Adapter (posted lineups ONLY)
        -> MLB Stats enrichment (season/recent/platoon)
        -> Statcast enrichment (exit velo/hard-hit/barrel/xwOBA/trends)
        -> Opposing Pitcher Context (from the SAME pregame pitcher
           research the Pitcher Agent uses -- never its scores/ranks)
        -> BatterInput -> Batter Agent -> REAL ranked hitter board
        -> immutable prediction snapshot

Usage:
    python scripts/run_real_batter_agent.py --date YYYY-MM-DD
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.batter_agent import analyze_slate
from dfs.probable_starters import build_probable_hitters_map
from research import collector, enrichment as pitcher_enrichment, statcast_batter_collector, statcast_batter_enrichment
from research import statcast_collector as pitcher_statcast_collector
from research import statcast_enrichment as pitcher_statcast_enrichment
from research.adapters import batter_input as batter_adapter
from research.adapters import pitcher_input as pitcher_adapter
from research.adapters.pitcher_input import ResearchPackageNotFoundError
from research.batter_enrichment import apply_bios_to_batter_inputs, apply_stats_to_batter_inputs
from research.engine import build_research_package
from research.opposing_pitcher_context import attach_opposing_pitcher_context, build_opposing_pitcher_index
from research.prediction_snapshot import build_batter_snapshot, save_snapshot
from research.quality_report import build_batter_quality_report, render_batter_quality_report

TOP_N_DETAILED = 10
TOP_N_SUMMARY = 20
GROUP_SIZE = 10


def _ensure_research_package(date: str, output_root: str) -> dict:
    try:
        return batter_adapter.load_research_package(output_root, date)
    except ResearchPackageNotFoundError:
        print(f"No research package found for {date} under {output_root}/ -- building it now...\n")
        report = build_research_package(date, output_root=output_root)
        print(
            f"Built: {report.games_found} games, {report.pitchers_found} pitchers, "
            f"{report.batters_found} batters, {len(report.warnings)} warnings.\n"
        )
        return batter_adapter.load_research_package(output_root, date)


def _build_opposing_pitcher_index(date: str, output_root: str):
    """Runs the EXACT SAME pregame pitcher research pipeline
    scripts/run_real_pitcher_agent.py uses (identity adapter -> MLB
    Stats enrichment -> Statcast enrichment) so the Batter Agent can see
    real underlying pitcher metrics -- but never calls
    agents.pitcher_agent, so no pitcher score/tag/rank ever reaches a
    hitter's context."""
    package = pitcher_adapter.load_research_package(output_root, date)
    pitcher_inputs = pitcher_adapter.build_pitcher_inputs(package)
    if not pitcher_inputs:
        return {}

    pitcher_ids = [str(r["player_id"]) for r in package["pitchers"]]
    opponent_team_ids = sorted({str(r["opponent_team_id"]) for r in package["pitchers"]})
    player_to_opponent_team_id = {str(r["player_id"]): str(r["opponent_team_id"]) for r in package["pitchers"]}
    season = date.split("-")[0]

    raw_stats = collector.collect_pitcher_stats(pitcher_ids, opponent_team_ids, season, date)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    enriched_pitchers, provenance = pitcher_enrichment.apply_stats_to_pitcher_inputs(
        pitcher_inputs, raw_stats, player_to_opponent_team_id, retrieved_at
    )

    start_dates_by_player = {
        r["player_id"]: r["start_dates"] for r in provenance if r["type"] == "recent_pitching" and r.get("start_dates")
    }
    raw_statcast = pitcher_statcast_collector.collect_statcast_data(pitcher_ids, season, date, start_dates_by_player)
    enriched_pitchers, _ = pitcher_statcast_enrichment.apply_statcast_to_pitcher_inputs(enriched_pitchers, raw_statcast, retrieved_at)

    return build_opposing_pitcher_index(enriched_pitchers)


def _fmt(value, digits=1, none_text="--") -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else none_text


def _fmt3(value, none_text="--") -> str:
    return f"{value:.3f}"[1:] if isinstance(value, (int, float)) else none_text


def _print_summary_row(rank: int, entry) -> None:
    print(
        f"{rank:<3} {entry.name:<24} {entry.team:<5} {entry.opponent:<5} "
        f"{entry.batting_order!s:<3} {_fmt(entry.projection):>6} {_fmt(entry.ceiling):>6} {_fmt(entry.overall_score):>5} "
        f"{_fmt(entry.power_score):>6} {_fmt(entry.matchup_score):>6} {_fmt(entry.recent_trend_score):>6} "
        f"{_fmt(entry.risk_score):>5} {_fmt(entry.confidence):>5}"
    )


def _print_detail(rank: int, entry, b) -> None:
    print(f"{rank}. {entry.name}")
    print(f"   Team: {entry.team}   Opponent: {entry.opponent}   Order: {entry.batting_order}   Pos: {b.position}")
    print()
    print(f"Projection: {_fmt(entry.projection)}   Ceiling: {_fmt(entry.ceiling)}   Floor: {_fmt(entry.floor)}")
    print(f"Overall: {_fmt(entry.overall_score)}   Power: {_fmt(entry.power_score)}   Hitting Skill: {_fmt(entry.hitting_skill_score)}")
    print(f"Contact: {_fmt(entry.contact_score)}   Matchup: {_fmt(entry.matchup_score)}   Recent Trend: {_fmt(entry.recent_trend_score)}")
    print(f"Lineup Position: {_fmt(entry.lineup_position_score)}   Risk: {_fmt(entry.risk_score)}   Confidence: {_fmt(entry.confidence)}")
    print()
    print(
        f"Season: AVG {_fmt3(b.season.avg)}  OBP {_fmt3(b.season.obp)}  SLG {_fmt3(b.season.slg)}  "
        f"K% {_fmt(b.season.k_percent)}  BB% {_fmt(b.season.bb_percent)}  ISO {_fmt3(b.season.iso)}"
    )
    print(
        f"Statcast: xwOBA {_fmt3(b.season.xwoba)}  xBA {_fmt3(b.season.xba)}  Hard Hit% {_fmt(b.season.hard_hit_percent)}  "
        f"Barrel% {_fmt(b.season.barrel_percent)}  EV {_fmt(b.season.exit_velocity)}"
    )
    print(
        f"Recent (14d, {b.recent.plate_appearances or 0} PA): K% {_fmt(b.recent.k_percent)}  BB% {_fmt(b.recent.bb_percent)}  "
        f"xwOBA {_fmt3(b.recent.xwoba)}  Hard Hit% {_fmt(b.recent.hard_hit_percent)}"
    )
    if b.opposing_pitcher.player_id:
        print(
            f"Opposing SP: {b.opposing_pitcher.name} ({b.opposing_pitcher.throwing_hand})  K% {_fmt(b.opposing_pitcher.k_percent)}  "
            f"xERA {_fmt(b.opposing_pitcher.xera, 2)}  xwOBA allowed {_fmt3(b.opposing_pitcher.xwoba_allowed)}"
        )
    if entry.tags:
        print(f"Tags: {', '.join(entry.tags)}")
    print("Why:")
    for reason in entry.reasons:
        print(f"  - {reason}")
    print("-" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score real starting-lineup MLB hitters through the Batter Agent.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--output", default="research_output", help="Research package root directory")
    args = parser.parse_args()

    package = _ensure_research_package(args.date, args.output)
    confirmed_count = len(batter_adapter.build_batter_inputs(package))
    # PROBABLE FIX milestone: real, evidence-based probable starters
    # (dfs/probable_starters.py) for any team whose official lineup
    # hasn't posted yet, merged in alongside confirmed starters -- so
    # Native projections/ownership never have to wait for official
    # lineups. Never a second, divergent probable-inference algorithm --
    # the SAME build_probable_hitters_map dfs/eligibility.py itself uses.
    probable_hitters = build_probable_hitters_map(args.date, package)
    batter_inputs = batter_adapter.build_batter_inputs_with_probables(package, probable_hitters)
    missing_games = batter_adapter.missing_lineup_games(package)

    print("=" * 70)
    print("REAL MLB DFS BATTER BOARD")
    print(f"Slate: {args.date}")
    print(f"Confirmed Starting Hitters: {confirmed_count}")
    print(f"Probable Starting Hitters (real evidence, lineup not yet posted): {len(batter_inputs) - confirmed_count}")
    print(f"Total Hitters Analyzed: {len(batter_inputs)}")
    print(f"Games without a posted lineup yet: {len(missing_games)}")
    for g in missing_games:
        print(f"  - game {g['game_id']}: {g['away_team_abbr']} @ {g['home_team_abbr']}")
    print("=" * 70)
    print()

    if not batter_inputs:
        print("No posted lineups AND no real probable-starter evidence yet -- nothing to analyze. Lineups are typically posted a few hours before first pitch.")
        return

    batter_ids = [b.player_id for b in batter_inputs]
    season = args.date.split("-")[0]

    print(f"Fetching real season/recent/platoon hitting statistics for {len(batter_ids)} starting hitters...\n")
    raw_stats = collector.collect_batter_stats(batter_ids, season, args.date)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    enriched, mlb_provenance = apply_stats_to_batter_inputs(batter_inputs, raw_stats, args.date, retrieved_at)

    people = collector.collect_batter_bios(batter_ids, args.date)
    enriched = apply_bios_to_batter_inputs(enriched, people)

    print(f"Fetching advanced Statcast metrics for {len(batter_ids)} hitters...\n")
    raw_statcast = statcast_batter_collector.collect_batter_statcast_data(batter_ids, season, args.date, args.date)
    enriched, sc_provenance = statcast_batter_enrichment.apply_statcast_to_batter_inputs(enriched, raw_statcast, retrieved_at)

    print("Building opposing-pitcher research context (reusing pregame pitcher research, not the Pitcher Agent)...\n")
    pitcher_index = _build_opposing_pitcher_index(args.date, args.output)
    enriched = attach_opposing_pitcher_context(enriched, pitcher_index)

    for warnings, label in ((raw_stats.warnings, "MLB Stats"), (raw_statcast.warnings, "Statcast")):
        if warnings:
            print(f"{label} data collection notes ({len(warnings)}):")
            for w in warnings[:10]:
                print(f"  - {w}")
            if len(warnings) > 10:
                print(f"  ... and {len(warnings) - 10} more")
            print()

    board = analyze_slate(enriched)
    batters_by_id = {b.player_id: b for b in enriched}

    print(f"TOP {min(TOP_N_SUMMARY, len(board))}")
    header = f"{'Rk':<3} {'Player':<24} {'Team':<5} {'Opp':<5} {'Ord':<3} {'Proj':>6} {'Ceil':>6} {'Ovr':>5} {'Power':>6} {'Match':>6} {'Recent':>6} {'Risk':>5} {'Conf':>5}"
    print(header)
    print("-" * len(header))
    for rank, entry in enumerate(board[:TOP_N_SUMMARY], start=1):
        _print_summary_row(rank, entry)
    print()

    print(f"DETAILED TOP {min(TOP_N_DETAILED, len(board))}")
    print()
    for rank, entry in enumerate(board[:TOP_N_DETAILED], start=1):
        _print_detail(rank, entry, batters_by_id[entry.player_id])
    print()

    def _top(key, n=GROUP_SIZE):
        return sorted(board, key=lambda e: -getattr(e, key))[:n]

    print("TOP POWER")
    for e in _top("power_score"):
        print(f"  {e.name:<24} {e.team:<5} power={e.power_score:>5} proj={e.projection:>5}")
    print()

    print("TOP CONTACT")
    for e in _top("contact_score"):
        print(f"  {e.name:<24} {e.team:<5} contact={e.contact_score:>5}")
    print()

    print("TOP MATCHUPS")
    for e in _top("matchup_score"):
        print(f"  {e.name:<24} {e.team:<5} vs {e.opponent:<5} matchup={e.matchup_score:>5}")
    print()

    print("TOP RECENT STATCAST RISERS")
    for e in _top("recent_trend_score"):
        print(f"  {e.name:<24} {e.team:<5} recent_trend={e.recent_trend_score:>5}")
    print()

    print("HIGH-RISK POWER (power_score >= 60 and risk_score >= 45)")
    high_risk_power = sorted(
        [e for e in board if e.power_score >= 60.0 and e.risk_score >= 45.0],
        key=lambda e: -e.power_score,
    )[:GROUP_SIZE]
    for e in high_risk_power:
        print(f"  {e.name:<24} {e.team:<5} power={e.power_score:>5} risk={e.risk_score:>5}")
    if not high_risk_power:
        print("  (none this slate)")
    print()

    quality_report = build_batter_quality_report(enriched)
    print(render_batter_quality_report(quality_report))
    print()

    source_metadata = {
        "mlb_stats_sources": raw_stats.sources_used,
        "statcast_sources": raw_statcast.sources_used,
    }
    missing_lineup_game_ids = [g["game_id"] for g in missing_games]
    snapshot = build_batter_snapshot(
        args.date, board, batters_by_id, quality_report, source_metadata,
        missing_lineup_game_ids=missing_lineup_game_ids, generated_at=retrieved_at,
    )
    snapshot_path = save_snapshot(snapshot, filename_prefix="batter_board")
    print(f"Pregame prediction snapshot saved (immutable): {snapshot_path}")


if __name__ == "__main__":
    main()
