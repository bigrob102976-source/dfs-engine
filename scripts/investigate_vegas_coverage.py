"""Milestone 27 -- Vegas coverage audit + LAD @ COL investigation.

For a slate date, reports every game's real Vegas coverage classification
across the configured provider(s) (SportsGameOdds primary, The Odds API
secondary/fallback if configured), and -- when LAD @ COL is present on
that date -- prints the full required investigation: each provider's raw
total/moneyline/validation status, the selected consensus, implied runs,
where the game ranks by total/team-implied-runs/Stack Environment Score
on the slate, and whether implied runs reconcile with the total.

Reuses the real, already-tested pipeline end to end (research package,
get_configured_vegas_provider(), scoring.score_environment()) -- never
recomputes/duplicates the scoring or consensus math.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from research.game_environment import ballpark, bullpen, collector, game_status as game_status_module, scoring, weather  # noqa: E402
from research.game_environment.providers import coverage as coverage_module  # noqa: E402
from research.game_environment.vegas import MultiProviderVegasProvider  # noqa: E402


def _load_games(date: str) -> list:
    path = Path("research_output") / date / "games.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dk_slate_games(date: str) -> "set | None":
    """Best-effort: if a real DK match report exists for this date,
    return the set of research game_ids on the LATEST built slate, so
    the audit can be scoped to the actual selected slate rather than the
    full day (same dk_game_matches this project's own dashboard --
    lib/dkVegasCoverage.ts -- already reads). Returns None (meaning "use
    every game") if no match report is found -- this script still works
    as a pure full-day Vegas-provider audit either way."""
    input_dir = Path("dfs_input") / date
    if not input_dir.exists():
        return None
    match_files = sorted(input_dir.glob("dk_match_report_*.json"))
    if not match_files:
        return None
    latest = json.loads(match_files[-1].read_text(encoding="utf-8"))
    matches = latest.get("dk_game_matches") or {}
    ids = {m.get("research_game_id") for m in matches.values() if m.get("status") == "matched" and m.get("research_game_id")}
    return ids or None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()

    games = _load_games(args.date)
    if not games:
        print(json.dumps({"status": "no_research_package", "date": args.date}))
        return

    slate_game_ids = _load_dk_slate_games(args.date)
    if slate_game_ids is not None:
        games = [g for g in games if g.get("game_id") in slate_game_ids]

    vegas_provider, provider_source = collector.get_configured_vegas_provider()
    print(f"Vegas provider source: {provider_source} ({vegas_provider.provider_name()})")
    print(f"Games audited: {len(games)}\n")

    rows = []
    for g in games:
        game_id = g["game_id"]
        home = g["home_team_abbr"]
        away = g["away_team_abbr"]
        mlb_status = g.get("status")

        snapshot = None
        try:
            snapshot = vegas_provider.get_vegas_line(game_id, home, away, slate_date=args.date, mlb_game_status=mlb_status)
        except Exception as exc:  # noqa: BLE001 -- diagnostic script, report anything that goes wrong
            print(f"{away}@{home}: ERROR building snapshot: {exc}")
            continue

        rows.append((g, snapshot))
        classification = snapshot.missing_reason or coverage_module.VALID
        total = snapshot.current_home.total
        print(
            f"{away}@{home}: status={snapshot.vegas_projection_status} "
            f"provider={snapshot.selected_provider} fallback={snapshot.fallback_used} "
            f"primary={snapshot.primary_provider_status} secondary={snapshot.secondary_provider_status} "
            f"missing_reason={classification} total={total} "
            f"home_implied={snapshot.home_implied_runs} away_implied={snapshot.away_implied_runs}"
        )

    # --- LAD @ COL mandatory investigation -----------------------------
    lad_col = next((pair for pair in rows if {pair[0]["home_team_abbr"], pair[0]["away_team_abbr"]} == {"LAD", "COL"}), None)
    if lad_col is None:
        print("\nLAD @ COL: not present on this slate/date.")
    else:
        g, snap = lad_col
        print("\n=== LAD @ COL investigation ===")
        print(f"Home: {g['home_team_abbr']}  Away: {g['away_team_abbr']}  MLB status: {g.get('status')}")
        print(f"Selected provider: {snap.selected_provider}  Fallback used: {snap.fallback_used}")
        print(f"Primary provider status: {snap.primary_provider_status}")
        print(f"Secondary provider status: {snap.secondary_provider_status}")
        print(f"Pregame status: {snap.vegas_projection_status} (game_status={snap.game_status})")
        print(f"Consensus total: {snap.current_home.total}")
        print(f"Home (COL) moneyline: {snap.current_home.moneyline}  Away (LAD) moneyline: {snap.current_away.moneyline}")
        print(f"Home (COL) implied runs: {snap.home_implied_runs}")
        print(f"Away (LAD) implied runs: {snap.away_implied_runs}")
        print(f"Books used: {snap.books_used}")
        if snap.home_implied_runs is not None and snap.away_implied_runs is not None and snap.current_home.total is not None:
            reconciled = round(snap.home_implied_runs + snap.away_implied_runs, 2) == round(snap.current_home.total, 2)
            print(f"LAD implied + COL implied == total? {reconciled} ({snap.away_implied_runs} + {snap.home_implied_runs} vs {snap.current_home.total})")

        # Ranking by total among audited games.
        by_total = sorted([r for r in rows if r[1].current_home.total is not None], key=lambda r: r[1].current_home.total, reverse=True)
        total_rank = next((i + 1 for i, r in enumerate(by_total) if r[0]["game_id"] == g["game_id"]), None)
        print(f"\nTotal ranking on this slate: #{total_rank} of {len(by_total)} games with a valid total.")

        # Ranking by team implied runs (LAD's own side).
        implied_candidates = []
        for gg, ss in rows:
            if gg["home_team_abbr"] == "LAD" and ss.home_implied_runs is not None:
                implied_candidates.append((gg["game_id"], "LAD", ss.home_implied_runs))
            elif gg["away_team_abbr"] == "LAD" and ss.away_implied_runs is not None:
                implied_candidates.append((gg["game_id"], "LAD", ss.away_implied_runs))
            if gg["home_team_abbr"] not in ("LAD",) and ss.home_implied_runs is not None:
                implied_candidates.append((gg["game_id"], gg["home_team_abbr"], ss.home_implied_runs))
            if gg["away_team_abbr"] not in ("LAD",) and ss.away_implied_runs is not None:
                implied_candidates.append((gg["game_id"], gg["away_team_abbr"], ss.away_implied_runs))
        implied_candidates.sort(key=lambda t: t[2], reverse=True)
        lad_implied_rank = next((i + 1 for i, t in enumerate(implied_candidates) if t[1] == "LAD"), None)
        print(f"LAD team-implied-runs ranking (all teams on slate): #{lad_implied_rank} of {len(implied_candidates)}.")

        # Stack Environment Score ranking (per-game, research/game_environment/scoring.py -- UNCHANGED weights).
        stack_scores = []
        for gg, ss in rows:
            park = ballpark.get_ballpark_profile(gg["home_team_abbr"])
            env_score = scoring.score_environment(park, None, ss, None, None)
            stack_scores.append((gg["game_id"], f"{gg['away_team_abbr']}@{gg['home_team_abbr']}", env_score.stack))
        stack_scores.sort(key=lambda t: t[2], reverse=True)
        lad_stack_rank = next((i + 1 for i, t in enumerate(stack_scores) if t[0] == g["game_id"]), None)
        print(f"LAD @ COL Stack Environment Score ranking: #{lad_stack_rank} of {len(stack_scores)}.")
        print("Full stack ranking:")
        for i, (gid, label, score) in enumerate(stack_scores, start=1):
            marker = "  <== LAD @ COL" if gid == g["game_id"] else ""
            print(f"  {i}. {label}: {score}{marker}")


if __name__ == "__main__":
    main()
