"""Milestone 27.3 -- player identity/type integrity audit.

For the selected real DraftKings slate, prints a per-team breakdown of:

    DK rows -> pitcher/hitter classification -> MLB match ->
    Native Big Money DFS coverage -> AI Big Money DFS coverage ->
    identity-integrity VALID/WARNING/INVALID counts (dfs/player_integrity.py)

and, for one team (default LAD, the team M27.3's live regression was
found on), a full per-player identity table -- exactly the format
required to prove a player like Tarik Skubal is under the team the raw
DK CSV actually says, with the game_id that actually matches that team's
matchup, and the player_type DraftKings' own position eligibility says.
"""

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _latest(pattern: str) -> "Path | None":
    matches = sorted(Path(".").glob(pattern))
    return matches[-1] if matches else None


def _latest_ids(pattern: str) -> set:
    files = sorted(glob.glob(pattern))
    if not files:
        return set()
    doc = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    return {str(p["player_id"]) for p in doc.get("players", [])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True)
    parser.add_argument("--team", default="LAD", help="Team to print a full per-player identity table for")
    args = parser.parse_args()

    pool_path = _latest(f"dfs_input/{args.date}/dk_player_pool_*.json")
    report_path = _latest(f"dfs_input/{args.date}/dk_match_report_*.json")
    if pool_path is None or report_path is None:
        print(json.dumps({"status": "no_pool_or_report", "date": args.date}))
        return

    pool = json.loads(pool_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    integrity = report.get("identity_integrity", {})
    status_by_dkid = {}
    for r in integrity.get("invalid_rows", []):
        status_by_dkid[r["dk_player_id"]] = "INVALID"
    for r in integrity.get("warning_rows", []):
        status_by_dkid.setdefault(r["dk_player_id"], "WARNING")

    native_ids = _latest_ids(f"native_projection_snapshots/{args.date}/native_projection_*.json")
    ai_ids = _latest_ids(f"ai_projection_snapshots/{args.date}/*.json")

    players = pool["players"]
    by_team: dict = {}
    for p in players:
        by_team.setdefault(p["team"], []).append(p)

    print(f"Pool: {pool_path.name}")
    print(f"Identity integrity: {integrity.get('valid')} VALID / {integrity.get('warning')} WARNING / "
          f"{integrity.get('invalid')} INVALID (of {integrity.get('total')})\n")

    header = f"{'TEAM':<6}{'DK ROWS':>9}{'PITCHERS':>10}{'HITTERS':>9}{'MLB MATCHED':>13}{'NATIVE':>8}{'AI':>5}{'INVALID':>9}"
    print(header)
    totals = dict(dk=0, pit=0, hit=0, mlb=0, native=0, ai=0, invalid=0)
    for team in sorted(by_team):
        rows = by_team[team]
        dk = len(rows)
        pit = sum(1 for p in rows if p["player_type"] == "pitcher")
        hit = sum(1 for p in rows if p["player_type"] == "hitter")
        mlb = sum(1 for p in rows if p["match_status"] == "matched")
        native = sum(1 for p in rows if p.get("mlb_player_id") in native_ids)
        ai = sum(1 for p in rows if p.get("mlb_player_id") in ai_ids)
        invalid = sum(1 for p in rows if status_by_dkid.get(p["dk_player_id"]) == "INVALID")
        for k, v in zip(totals, (dk, pit, hit, mlb, native, ai, invalid)):
            totals[k] += v
        print(f"{team:<6}{dk:>9}{pit:>10}{hit:>9}{mlb:>13}{native:>8}{ai:>5}{invalid:>9}")
    print(f"{'TOTAL':<6}{totals['dk']:>9}{totals['pit']:>10}{totals['hit']:>9}{totals['mlb']:>13}"
          f"{totals['native']:>8}{totals['ai']:>5}{totals['invalid']:>9}")

    team_rows = sorted(by_team.get(args.team, []), key=lambda p: -p["salary"])
    if team_rows:
        print(f"\n{args.team} full identity table ({len(team_rows)} players):\n")
        print(f"{'Name':<24}{'DK ID':>10} {'Team':<5}{'Opp':<5}{'GameID':>8} {'DK Pos':<8}{'Type':<9}"
              f"{'MLB ID':<8}{'Native':<7}{'AI':<4}{'Status'}")
        for p in team_rows:
            status = status_by_dkid.get(p["dk_player_id"], "VALID")
            native = "Y" if p.get("mlb_player_id") in native_ids else "N"
            ai = "Y" if p.get("mlb_player_id") in ai_ids else "N"
            print(f"{p['name']:<24}{p['dk_player_id']:>10} {p['team']:<5}{p['opponent'] or '-':<5}"
                  f"{p['game_id'] or '-':>8} {'/'.join(p['dk_positions']):<8}{p['player_type']:<9}"
                  f"{p['mlb_player_id'] or '-':<8}{native:<7}{ai:<4}{status}")


if __name__ == "__main__":
    main()
