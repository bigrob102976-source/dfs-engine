"""M6A/M6B/M6C -- computes REAL MLB lineup-eligibility for canonical
Postgres slate players, reusing dfs/eligibility.py's own
compute_eligibility() and dfs/slate_validation.py's own
match_game_infos() UNCHANGED -- never a second, divergent eligibility or
game-matching algorithm (M6 rules #11/#12).

WHY THIS IS A SEPARATE SCRIPT, NOT A NEW ALGORITHM: canonical Postgres
lives on the Node/TS side of this codebase (player_identity/persistence.py's
own documented reason for never adding a Python-to-Postgres dependency --
see canonical_ingestion/__init__.py). Eligibility computation needs the
MLB research package (Python-only: research_output/<date>/{games,
pitchers,batters}.json). This script is the bridge: it accepts a
canonical player list as JSON (built by the TS caller from Postgres),
runs the REAL eligibility computation, and returns REAL results as JSON
for the TS caller to persist back into slate_players -- it never reads
or writes Postgres itself.

Usage:
    python scripts/compute_canonical_eligibility.py --date 2026-09-02 --input players.json
    (or --input - to read the same JSON from stdin)

Input JSON shape:
    {"date": "2026-09-02", "players": [
        {"providerPlayerId": "123", "name": "...", "team": "BOS", "opponent": "TOR",
         "positions": ["OF"], "salary": 4500, "identityStatus": "RESOLVED"|"UNRESOLVED"|"REVIEW_REQUIRED",
         "mlbPlayerId": "660271"|null},
        ...
    ]}

Output (stdout, one JSON object, always the last line so a caller can
safely take the last line even if research-package auto-build printed
progress lines above it):
    {"status": "OK", "date": "...", "results": [
        {"providerPlayerId": "123", "gameId": "..."|null, "eligibilityStatus": "STARTING_HITTER", "optimizerEligible": true, "battingOrder": 3|null},
        ...
    ]}
    or, honestly, when no research package exists yet for this date and
    could not be built (M6F: this is NORMAL for a freshly tomorrow-
    prefetched slate, never a worker failure):
    {"status": "NO_RESEARCH_PACKAGE", "date": "...", "reason": "...", "results": []}

Never fabricates a game_id, an eligibility status, or a projection.
Every player not resolvable stays honestly UNMATCHED/AMBIGUOUS/
LINEUP_UNCONFIRMED -- see dfs/eligibility.py's own docstring for exactly
what each status means. This script never touches DraftKings (no
network call at all -- research_output/ and its object-storage backing
are the only inputs read).
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.eligibility import compute_eligibility
from dfs.models import DFSPlayer
from dfs.player_resolver import _infer_player_type_from_dk_positions
from dfs.pool_builder import ensure_research_package
from dfs.probable_starters import build_probable_hitters_map
from dfs.slate_validation import match_game_infos
from research.adapters.pitcher_input import ResearchPackageNotFoundError

_IDENTITY_TO_MATCH_STATUS = {"RESOLVED": "matched", "REVIEW_REQUIRED": "ambiguous", "UNRESOLVED": "unmatched"}


def _resolve_game_ids(players_in: List[dict], games: List[dict]) -> dict:
    """Batch game-id resolution for a whole slate in one call to the
    REAL, existing dfs.slate_validation.match_game_infos() -- the same
    function both the legacy CSV pool builder and the M26 provider-layer
    slate-listing game_ids resolution already use. Builds a time-less
    "AWAY@HOME" string per player from `team`/`opponent` (frozenset-keyed
    team-pair matching means which side is "away" vs "home" in the
    string never matters -- see slate_validation.py's own docstring).
    A player with no `opponent` at all gets no game_info string and
    therefore no game_id -- honestly unresolved, never guessed."""
    game_infos_by_provider_id = {}
    for p in players_in:
        if p.get("team") and p.get("opponent"):
            game_infos_by_provider_id[p["providerPlayerId"]] = f"{p['team']}@{p['opponent']}"

    matches = match_game_infos(list(set(game_infos_by_provider_id.values())), games)
    resolved: dict = {}
    for provider_player_id, game_info in game_infos_by_provider_id.items():
        match = matches.get(game_info)
        if match and match.status == "matched":
            resolved[provider_player_id] = match.research_game_id
    return resolved


def _build_dfs_player(p: dict, game_id: Optional[str]) -> DFSPlayer:
    positions = p.get("positions") or []
    return DFSPlayer(
        dk_player_id=p["providerPlayerId"],
        name=p.get("name") or "",
        team=p.get("team") or "",
        player_type=_infer_player_type_from_dk_positions(positions) or "hitter",
        dk_positions=positions,
        salary=int(p.get("salary") or 0),
        mlb_player_id=p.get("mlbPlayerId"),
        opponent=p.get("opponent"),
        game_id=game_id,
        match_status=_IDENTITY_TO_MATCH_STATUS.get(p.get("identityStatus"), "unmatched"),
    )


def compute_for_payload(payload: dict) -> dict:
    # MLB AUTOMATIC PIPELINE RELIABILITY Phase 1: explicit per-stage
    # timing to stderr (never stdout -- this script's RESULT_JSON
    # contract on stdout must stay exactly one line) so a slow/hanging
    # invocation is diagnosable from the worker log alone, not just an
    # opaque "it took a while." Kept permanently (cheap -- a handful of
    # prints per invocation) per this milestone's own bounded-execution
    # observability requirement.
    stage_started = time.monotonic()
    date = payload["date"]
    players_in = payload.get("players") or []
    print(f"[eligibility] date={date} players_in={len(players_in)}", file=sys.stderr, flush=True)

    t0 = time.monotonic()
    try:
        package = ensure_research_package(date, "research_output")
    except ResearchPackageNotFoundError as exc:
        return {"status": "NO_RESEARCH_PACKAGE", "date": date, "reason": str(exc), "results": []}
    except Exception as exc:  # noqa: BLE001 -- a real research-build failure is honestly reported, never crashes the caller
        return {"status": "NO_RESEARCH_PACKAGE", "date": date, "reason": f"{type(exc).__name__}: {exc}", "results": []}
    print(f"[eligibility] research_package_load elapsed={time.monotonic() - t0:.2f}s games={len(package.get('games', []))}", file=sys.stderr, flush=True)

    t0 = time.monotonic()
    games = package.get("games", [])
    game_id_by_provider_id = _resolve_game_ids(players_in, games)
    dfs_players = [_build_dfs_player(p, game_id_by_provider_id.get(p["providerPlayerId"])) for p in players_in]
    print(f"[eligibility] game_id_resolution elapsed={time.monotonic() - t0:.2f}s", file=sys.stderr, flush=True)

    t0 = time.monotonic()
    probable_hitters = build_probable_hitters_map(date, package)
    print(f"[eligibility] probable_hitters_map elapsed={time.monotonic() - t0:.2f}s entries={len(probable_hitters)}", file=sys.stderr, flush=True)

    t0 = time.monotonic()
    compute_eligibility(dfs_players, package.get("pitchers", []), package.get("batters", []), probable_hitters=probable_hitters)
    print(f"[eligibility] compute_eligibility elapsed={time.monotonic() - t0:.2f}s", file=sys.stderr, flush=True)

    results = [
        {
            "providerPlayerId": player.dk_player_id,
            "gameId": player.game_id,
            "eligibilityStatus": player.eligibility_status,
            "optimizerEligible": player.optimizer_eligible,
            "battingOrder": player.batting_order,
            "lineupConfirmation": player.lineup_confirmation,
            "probableConfidence": player.probable_confidence,
            "probableReason": player.probable_reason,
            "projectedBattingOrder": player.projected_batting_order,
        }
        for player in dfs_players
    ]
    print(f"[eligibility] total elapsed={time.monotonic() - stage_started:.2f}s players_out={len(results)}", file=sys.stderr, flush=True)
    return {"status": "OK", "date": date, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute real MLB lineup eligibility for a canonical Postgres player list.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--input", required=True, help="Path to input JSON, or '-' to read from stdin.")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    payload = json.loads(raw)
    payload.setdefault("date", args.date)

    result = compute_for_payload(payload)
    print(f"RESULT_JSON:{json.dumps(result)}")


if __name__ == "__main__":
    main()
