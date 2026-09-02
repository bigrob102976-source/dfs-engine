"""M6L -- the HONEST, non-projection structural proof that a canonical-
Postgres-sourced pool can produce real, legal DraftKings Classic MLB
lineups (roster rules + $50,000 salary cap + locks + excludes +
multiple-lineup uniqueness), WITHOUT running the real CP-SAT optimizer
(scripts/optimize_dk_lineups.py) -- that script requires a real
per-player projection/ceiling for every candidate (see
_build_optimizer_players()), which canonical Postgres does not have in
this milestone (M6M: never fabricate one merely to force a build
through).

Reuses dfs/lineup_smoke_test.py::find_lineups() UNCHANGED -- the exact
same deterministic backtracking roster/salary-cap search
dfs/pool_builder.py's own pre-flight check already runs for the legacy
pipeline, now extended (additively, M6L) with locks/excludes. Never a
second, divergent lineup-construction algorithm, and never the real
optimizer's own objective/exposure logic (this produces A legal roster,
not the BEST one).

Usage:
    python scripts/canonical_lineup_legality_check.py --input players.json
    (or --input - to read the same JSON from stdin)

Input JSON shape (only OPTIMIZER-ELIGIBLE players should be included --
the caller is expected to have already applied the real, persisted
eligibility state from M6A-M6D):
    {"count": 3, "salaryCap": 50000, "locks": ["123"], "excludes": ["456"],
     "players": [
        {"providerPlayerId": "123", "name": "...", "team": "BOS",
         "positions": ["OF"], "salary": 4500},
        ...
    ]}

Output (stdout, last line):
    {"status": "OK", "lineupsRequested": 3, "lineupsProduced": 2,
     "lineups": [[{"providerPlayerId": "123", "name": "...", "salary": 4500, "positions": ["OF"]}, ...], ...]}
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.lineup_smoke_test import find_lineups
from dfs.models import DFSPlayer
from dfs.player_resolver import _infer_player_type_from_dk_positions


def _build_dfs_player(p: dict) -> DFSPlayer:
    positions = p.get("positions") or []
    return DFSPlayer(
        dk_player_id=p["providerPlayerId"], name=p.get("name") or "", team=p.get("team") or "",
        player_type=_infer_player_type_from_dk_positions(positions) or "hitter",
        dk_positions=positions, salary=int(p.get("salary") or 0),
    )


def check_for_payload(payload: dict) -> dict:
    players = [_build_dfs_player(p) for p in payload.get("players") or []]
    count = int(payload.get("count") or 1)
    salary_cap = int(payload.get("salaryCap") or 50000)
    locks = set(payload.get("locks") or [])
    excludes = set(payload.get("excludes") or [])

    lineups = find_lineups(players, count=count, salary_cap=salary_cap, locked_player_ids=locks, excluded_player_ids=excludes)

    return {
        "status": "OK",
        "lineupsRequested": count,
        "lineupsProduced": len(lineups),
        "lineups": [
            [{"providerPlayerId": p.dk_player_id, "name": p.name, "salary": p.salary, "positions": p.dk_positions} for p in lineup]
            for lineup in lineups
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Structural (non-projection) DK Classic MLB lineup legality check for a canonical player pool.")
    parser.add_argument("--input", required=True, help="Path to input JSON, or '-' to read from stdin.")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    payload = json.loads(raw)

    result = check_for_payload(payload)
    print(f"RESULT_JSON:{json.dumps(result)}")


if __name__ == "__main__":
    main()
