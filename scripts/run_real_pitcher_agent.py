"""CLI entry point: score REAL MLB probable starters for a slate date
through the (unchanged) existing Pitcher Agent, enriched with real
season/recent MLB Stats AND advanced Statcast metrics.

    Research Package -> Pitcher Input Adapter
        -> MLB Stats enrichment (season/recent/opponent K%)
        -> Statcast enrichment (velocity/CSW/SwStr%/hard-hit/barrel/GB/xERA/xwOBA/trends)
        -> PitcherInput -> existing Pitcher Agent -> REAL ranked board

Usage:
    python scripts/run_real_pitcher_agent.py --date YYYY-MM-DD
    python scripts/run_real_pitcher_agent.py --date YYYY-MM-DD --output research_output
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.pitcher_agent import analyze_slate
from research import collector, enrichment, innings, statcast_collector, statcast_enrichment
from research.adapters import pitcher_input as adapter
from research.adapters.pitcher_input import ResearchPackageNotFoundError
from research.engine import build_research_package
from research.prediction_snapshot import build_snapshot, save_snapshot
from research.quality_report import build_quality_report, render_quality_report
from research.storage import save_json

TOP_N_DETAILED = 10


def _ensure_research_package(date: str, output_root: str) -> dict:
    """Load the research package for `date`, building it first (one
    clean call into the existing engine) if it doesn't exist yet."""
    try:
        return adapter.load_research_package(output_root, date)
    except ResearchPackageNotFoundError:
        print(f"No research package found for {date} under {output_root}/ -- building it now...\n")
        report = build_research_package(date, output_root=output_root)
        print(
            f"Built: {report.games_found} games, {report.pitchers_found} pitchers, "
            f"{report.batters_found} batters, {len(report.warnings)} warnings.\n"
        )
        return adapter.load_research_package(output_root, date)


def _fmt(value, digits=1, none_text="--") -> str:
    return f"{value:.{digits}f}" if value is not None else none_text


def _fmt3(value, none_text="--") -> str:
    return f"{value:.3f}"[1:] if value is not None else none_text  # ".256" DFS-style, no leading 0


def _data_status(entry, p, has_season: bool, has_recent: bool) -> list:
    has_opponent_k = p.opponent_stats.strikeout_percent_vs_hand is not None or p.opponent_stats.strikeout_percent is not None
    has_statcast = any([
        p.season.swinging_strike_percent, p.recent.csw_percent, p.season.hard_hit_percent,
        p.season.barrel_percent, p.season.ground_ball_percent, p.season.xwoba_allowed, p.season.xera,
    ])
    lines = [
        ("Identity", True),
        ("Season Stats", has_season),
        ("Recent Stats", has_recent),
        ("Statcast", has_statcast),
        ("Opponent K Rate", has_opponent_k),
        ("Salary", entry.salary is not None),
        ("Weather", p.game.weather_pitching_factor is not None),
        ("Umpire", p.game.umpire_pitching_factor is not None),
        ("Vegas", p.opponent_stats.implied_runs is not None),
    ]
    return [f"{label}: {'loaded' if loaded else 'not loaded'}" for label, loaded in lines]


def _print_advanced_metrics(p) -> None:
    print("ADVANCED METRICS (Statcast)")
    print()
    print(f"Velocity -- season: {_fmt(p.recent.season_velocity)}  recent: {_fmt(p.recent.velocity)}  trend: {_fmt(p.trends.velocity_trend, none_text='n/a')}")
    print(f"CSW% -- recent: {_fmt(p.recent.csw_percent)}  (season CSW% unavailable from structured Statcast sources)")
    print(f"SwStr% -- season: {_fmt(p.season.swinging_strike_percent)}  recent: {_fmt(p.recent.swinging_strike_percent)}  trend: {_fmt(p.trends.swinging_strike_trend, none_text='n/a')}")
    print(f"Hard Hit% -- season: {_fmt(p.season.hard_hit_percent)}  recent: {_fmt(p.recent.hard_hit_percent)}  trend: {_fmt(p.trends.hard_hit_trend, none_text='n/a')}")
    print(f"Barrel% -- season: {_fmt(p.season.barrel_percent)}  recent: {_fmt(p.recent.barrel_percent)}  trend: {_fmt(p.trends.barrel_trend, none_text='n/a')}")
    print(f"Ground Ball% -- season: {_fmt(p.season.ground_ball_percent)}  recent: {_fmt(p.recent.ground_ball_percent)}  trend: {_fmt(p.trends.ground_ball_trend, none_text='n/a')}")
    print(f"Exit Velo Allowed -- season: {_fmt(p.season.avg_exit_velocity_allowed)}  recent: {_fmt(p.recent.avg_exit_velocity_allowed)}")
    print(f"xERA: {_fmt(p.season.xera, 2)}  xwOBA: {_fmt3(p.season.xwoba_allowed)}  xBA: {_fmt3(p.season.xba)}")
    if p.season.pitch_mix:
        mix = ", ".join(f"{pt} {pct:.0f}%" for pt, pct in sorted(p.season.pitch_mix.items(), key=lambda kv: -kv[1]))
        print(f"Pitch mix (season): {mix}")
    if p.trends.pitch_mix_change is not None:
        print(f"Pitch mix change (recent vs. season): {p.trends.pitch_mix_change:.1f} points")
    print()


def _print_board(date: str, board, pitchers_by_id, season_by_player, recent_by_player) -> None:
    print("=" * 70)
    print("REAL MLB DFS PITCHER BOARD")
    print(f"Slate: {date}")
    print("=" * 70)
    print()
    print(f"Showing full detail for the top {min(TOP_N_DETAILED, len(board))} of {len(board)} pitchers "
          f"(full ranking is in the summary table below).")
    print()

    for rank, entry in enumerate(board[:TOP_N_DETAILED], start=1):
        p = pitchers_by_id[entry.player_id]
        season_line = season_by_player.get(entry.player_id)
        recent_line = recent_by_player.get(entry.player_id)

        print(f"{rank}. {entry.name}")
        print(f"   Team: {entry.team}")
        print(f"   Opponent: {entry.opponent}")
        print()
        print(f"Projection: {_fmt(entry.projection)}")
        print(f"Ceiling: {_fmt(entry.ceiling)}")
        print(f"Overall: {_fmt(entry.overall_score)}")
        print(f"K Upside: {_fmt(entry.strikeout_score)}")
        print(f"Run Prevention: {_fmt(entry.run_prevention_score)}")
        print(f"Matchup: {_fmt(entry.matchup_score)}")
        print(f"Risk: {_fmt(entry.risk_score)}")
        print(f"Confidence: {_fmt(entry.confidence)}")
        print()

        print("SEASON")
        print()
        if season_line:
            print(f"IP: {innings.decimal_innings_to_notation(season_line['innings_pitched'])}")
            print(f"BF: {season_line['batters_faced']}")
            print(f"K: {season_line['strikeouts']}")
            print(f"BB: {season_line['walks']}")
            print(f"ERA: {_fmt(season_line['era'], 2)}")
            print(f"K%: {_fmt(season_line['k_percent'])}")
            print(f"BB%: {_fmt(season_line['bb_percent'])}")
            print(f"K-BB%: {_fmt(season_line['k_minus_bb_percent'])}")
        else:
            print("(no season stats available yet)")
        print()

        print("RECENT -- LAST 3 STARTS")
        print()
        if recent_line:
            print(f"IP: {innings.decimal_innings_to_notation(recent_line['innings_pitched'])}")
            print(f"K%: {_fmt(recent_line['k_percent'])}")
            print(f"BB%: {_fmt(recent_line['bb_percent'])}")
            print(f"Avg Pitch Count: {_fmt(recent_line['pitch_count_average'])}")
        else:
            print("(no recent game log available yet)")
        print()

        _print_advanced_metrics(p)

        print("DATA STATUS")
        print()
        for line in _data_status(entry, p, season_line is not None, recent_line is not None):
            print(line)
        print()

        if entry.tags:
            print(f"Tags: {', '.join(entry.tags)}")
            print()
        print("Why:")
        for reason in entry.reasons:
            print(f"  - {reason}")
        print()
        print("-" * 70)

    print()
    print("SUMMARY TABLE (full slate)")
    header = f"{'Rk':<3} {'Pitcher':<26} {'Team':<5} {'Opp':<5} {'Proj':>6} {'Ceil':>6} {'Ovr':>5} {'K%':>6} {'K-BB%':>6} {'Risk':>5} {'Conf':>5}"
    print(header)
    print("-" * len(header))
    for rank, entry in enumerate(board, start=1):
        p = pitchers_by_id[entry.player_id]
        print(
            f"{rank:<3} {entry.name:<26} {entry.team:<5} {entry.opponent:<5} "
            f"{entry.projection:>6} {entry.ceiling:>6} {entry.overall_score:>5} "
            f"{_fmt(p.season.k_percent):>6} {_fmt(p.season.k_minus_bb_percent):>6} "
            f"{entry.risk_score:>5} {entry.confidence:>5}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Score real MLB probable starters through the existing Pitcher Agent.")
    parser.add_argument("--date", required=True, help="Slate date in YYYY-MM-DD format")
    parser.add_argument("--output", default="research_output", help="Research package root directory (default: research_output)")
    args = parser.parse_args()

    package = _ensure_research_package(args.date, args.output)
    pitcher_inputs = adapter.build_pitcher_inputs(package)

    if not pitcher_inputs:
        print(f"No probable pitchers found in the research package for {args.date}.")
        return

    pitcher_ids = [str(r["player_id"]) for r in package["pitchers"]]
    opponent_team_ids = sorted({str(r["opponent_team_id"]) for r in package["pitchers"]})
    player_to_opponent_team_id = {str(r["player_id"]): str(r["opponent_team_id"]) for r in package["pitchers"]}
    season = args.date.split("-")[0]

    print(f"Fetching real season/recent/opponent statistics for {len(pitcher_ids)} probable pitchers "
          f"({len(opponent_team_ids)} opponent teams)...\n")
    raw_stats = collector.collect_pitcher_stats(pitcher_ids, opponent_team_ids, season, args.date)

    retrieved_at = datetime.now(timezone.utc).isoformat()
    enriched_pitchers, provenance = enrichment.apply_stats_to_pitcher_inputs(
        pitcher_inputs, raw_stats, player_to_opponent_team_id, retrieved_at
    )

    if raw_stats.warnings:
        print(f"MLB Stats data collection notes ({len(raw_stats.warnings)}):")
        for w in raw_stats.warnings:
            print(f"  - {w}")
        print()

    # Recent Statcast pulls are scoped to each pitcher's exact last-3-start
    # dates, which only the MLB Stats recent-form parse (just above) knows.
    start_dates_by_player = {}
    for record in provenance:
        if record["type"] == "recent_pitching" and record.get("start_dates"):
            start_dates_by_player[record["player_id"]] = record["start_dates"]

    print(f"Fetching advanced Statcast metrics from Baseball Savant "
          f"({len(pitcher_ids)} pitchers, 4 season leaderboards)...\n")
    raw_statcast = statcast_collector.collect_statcast_data(pitcher_ids, season, args.date, start_dates_by_player)

    enriched_pitchers, statcast_provenance = statcast_enrichment.apply_statcast_to_pitcher_inputs(
        enriched_pitchers, raw_statcast, retrieved_at
    )
    provenance = provenance + statcast_provenance

    if raw_statcast.warnings:
        print(f"Statcast data collection notes ({len(raw_statcast.warnings)}):")
        for w in raw_statcast.warnings:
            print(f"  - {w}")
        print()
    if raw_statcast.errors:
        print(f"Statcast errors ({len(raw_statcast.errors)}):")
        for e in raw_statcast.errors:
            print(f"  - {e}")
        print()

    stats_path = Path(args.output) / args.date / "pitcher_stats.json"
    save_json(stats_path, provenance)

    board = analyze_slate(enriched_pitchers)

    pitchers_by_id = {p.player_id: p for p in enriched_pitchers}
    season_by_player = {r["player_id"]: r for r in provenance if r["type"] == "season_pitching"}
    recent_by_player = {r["player_id"]: r for r in provenance if r["type"] == "recent_pitching"}

    _print_board(args.date, board, pitchers_by_id, season_by_player, recent_by_player)

    print()
    quality_report = build_quality_report(enriched_pitchers)
    print(render_quality_report(quality_report))

    print()
    print(f"Stat provenance written to: {stats_path}")

    source_metadata = {
        "mlb_stats_sources": raw_stats.sources_used,
        "statcast_sources": raw_statcast.sources_used,
    }
    snapshot = build_snapshot(args.date, board, pitchers_by_id, quality_report, source_metadata, generated_at=retrieved_at)
    snapshot_path = save_snapshot(snapshot)
    print(f"Pregame prediction snapshot saved (immutable): {snapshot_path}")


if __name__ == "__main__":
    main()
