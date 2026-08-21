"""Milestone 32.0, Part 10 -- small proof-of-concept joined historical
dataset for ONE date. NOT the full warehouse (Part 9's directory layout
is proposed but deliberately not built out yet). Live network calls
only (MLB Stats API, Baseball Savant); nothing here is a unit test.

Usage:
    python scripts/run_historical_poc_join.py --date 2025-06-15
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from historical_mlb import audit, game_crosswalk, identity, rolling
from historical_mlb.leakage import filter_pregame_observations
from historical_mlb.scoring import score_boxscore
from historical_mlb.sources import mlb_stats, statcast, weather


def build_poc(date: str, max_pitchers: int = 15, max_hitters: int = 60) -> dict:
    t0 = time.time()
    schedule = mlb_stats.fetch_schedule(date)
    games = mlb_stats.games_from_schedule(schedule)
    final_games = [g for g in games if g["status"] == "Final"]

    game_rows = [game_crosswalk.crosswalk_row_from_schedule_game(g) for g in games]
    game_index = game_crosswalk.build_game_index(game_rows)

    from dfs.team_abbreviations import normalize_full_team_name

    all_pitcher_rows, all_hitter_rows = [], []
    unmatched_games = []
    for g in final_games:
        box = mlb_stats.fetch_boxscore(g["game_pk"])
        if not box:
            unmatched_games.append(g["game_pk"])
            continue
        # boxscore player entries carry the team as an ABBREVIATION (e.g.
        # "DET"); schedule's away_team/home_team are FULL names (e.g.
        # "Detroit Tigers") -- both normalized to abbreviations here so
        # the home/away and opponent comparisons below are apples-to-apples.
        away_abbr = normalize_full_team_name(g["away_team"])
        home_abbr = normalize_full_team_name(g["home_team"])
        pitchers, hitters = mlb_stats.extract_all_boxscore_players(box)
        pitcher_rows, hitter_rows = score_boxscore(pitchers, hitters, game_id=str(g["game_pk"]), game_date=date)
        for row in pitcher_rows + hitter_rows:
            row["home_away"] = "away" if row["team"] == away_abbr else "home" if row["team"] == home_abbr else None
            row["opponent"] = home_abbr if row["team"] == away_abbr else away_abbr if row["team"] == home_abbr else None
        all_pitcher_rows += pitcher_rows
        all_hitter_rows += hitter_rows

    # Statcast for this date -- one fetch, aggregated per player below.
    statcast_csv = statcast.fetch_statcast_csv_text(date)
    statcast_rows = statcast.parse_statcast_csv(statcast_csv)

    # Weather -- one fetch per unique home team playing this date, joined
    # at the GAME level (not per-player -- see this script's report note
    # on why a per-hour first-pitch join was scoped out of this POC).
    game_weather = {}
    for g in final_games:
        abbr = normalize_full_team_name(g["home_team"])
        if not abbr or abbr in game_weather:
            continue
        try:
            payload = weather.fetch_historical_weather_json(abbr, date)
        except Exception as exc:  # noqa: BLE001 -- a weather-fetch failure for one team must not abort the whole POC
            game_weather[abbr] = {"error": str(exc)}
            continue
        game_weather[abbr] = payload.get("hourly") if payload else None

    identity_rows = []
    seen_players = set()

    def crosswalk_for(player_id, name, team):
        if player_id in seen_players:
            return
        seen_players.add(player_id)
        identity_rows.append(identity.crosswalk_row_from_mlbam(player_id, name, team))

    # Rolling features + handedness for a bounded sample (network-call budget).
    enriched_pitchers = []
    for row in all_pitcher_rows[:max_pitchers]:
        crosswalk_for(row["player_id"], row["name"], row["team"])
        person = mlb_stats.fetch_person(row["player_id"])
        hand = mlb_stats.person_handedness(person)
        game_log = mlb_stats.fetch_pitcher_game_log(row["player_id"], season=date[:4])
        splits = (game_log or {}).get("stats", [{}])[0].get("splits", [])
        entries = [{"date": s.get("date"), "stat": s.get("stat", {})} for s in splits if s.get("date")]
        r7 = rolling.build_rolling_pitcher_stats(entries, date, 7, "last_7d")
        r30 = rolling.build_rolling_pitcher_stats(entries, date, 30, "last_30d")
        season = rolling.build_rolling_pitcher_stats(entries, date, None, "season_to_date")
        enriched_pitchers.append({
            **row, "throw_hand": hand["throw_hand"], "bat_hand": hand["bat_side"],
            "rolling_ip_30d": r30.innings_pitched, "rolling_k_rate_30d": r30.k_rate, "rolling_bb_rate_30d": r30.bb_rate,
            "rolling_era_30d": r30.era, "rolling_whip_30d": r30.whip,
            "rolling_ip_7d": r7.innings_pitched, "season_era": season.era, "season_games": season.games,
        })

    enriched_hitters = []
    for row in all_hitter_rows[:max_hitters]:
        crosswalk_for(row["player_id"], row["name"], row["team"])
        person = mlb_stats.fetch_person(row["player_id"])
        hand = mlb_stats.person_handedness(person)
        game_log = mlb_stats.fetch_batter_game_log(row["player_id"], season=date[:4])
        splits = (game_log or {}).get("stats", [{}])[0].get("splits", [])
        entries = [{"date": s.get("date"), "stat": s.get("stat", {})} for s in splits if s.get("date")]
        r7 = rolling.build_rolling_hitter_stats(entries, date, 7, "last_7d")
        r30 = rolling.build_rolling_hitter_stats(entries, date, 30, "last_30d")
        season = rolling.build_rolling_hitter_stats(entries, date, None, "season_to_date")
        statcast_agg = rolling.aggregate_statcast_rates(statcast_rows, "batter", row["player_id"])
        enriched_hitters.append({
            **row, "bat_hand": hand["bat_side"], "throw_hand": hand["throw_hand"],
            "rolling_avg_30d": r30.avg, "rolling_obp_30d": r30.obp, "rolling_slg_30d": r30.slg,
            "rolling_woba_30d": r30.woba_proxy, "rolling_iso_30d": r30.iso,
            "rolling_k_rate_30d": r30.k_rate, "rolling_bb_rate_30d": r30.bb_rate,
            "rolling_pa_7d": r7.pa, "season_avg": season.avg, "season_games": season.games,
            "hard_hit_rate": statcast_agg["hard_hit_rate"], "barrel_rate_proxy": statcast_agg["barrel_rate_proxy"],
            "xwoba_contribution": statcast_agg["avg_xwoba_contribution"],
        })

    quality_findings = audit.run_all_checks(enriched_hitters, enriched_pitchers, [vars(r) for r in game_rows])

    return {
        "date": date,
        "elapsed_sec": round(time.time() - t0, 1),
        "games_total": len(games),
        "games_final": len(final_games),
        "games_unmatched": unmatched_games,
        "pitcher_rows_total": len(all_pitcher_rows),
        "hitter_rows_total": len(all_hitter_rows),
        "pitchers_enriched": len(enriched_pitchers),
        "hitters_enriched": len(enriched_hitters),
        "identity_crosswalk_rows": len(identity_rows),
        "quality_findings": quality_findings,
        "weather_home_teams_covered": [k for k, v in game_weather.items() if v and "error" not in v],
        "weather_home_teams_failed": {k: v.get("error") for k, v in game_weather.items() if isinstance(v, dict) and "error" in v},
        "sample_pitchers": enriched_pitchers,
        "sample_hitters": enriched_hitters,
        "sample_games": [vars(r) for r in game_rows],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    result = build_poc(args.date)
    out_path = Path(args.out) if args.out else Path("data/historical/mlb/processed") / f"poc_{args.date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({
        "status": "ok", "date": args.date, "out_path": str(out_path),
        "pitchers_enriched": result["pitchers_enriched"], "hitters_enriched": result["hitters_enriched"],
        "quality_findings_count": len(result["quality_findings"]), "elapsed_sec": result["elapsed_sec"],
    }))


if __name__ == "__main__":
    main()
