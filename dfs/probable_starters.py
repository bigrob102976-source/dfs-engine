"""Real, evidence-based probable-starter inference for hitters, used
ONLY before a team's official starting lineup has posted for today's
game (dfs/eligibility.py's own `posted_team_games` signal already tells
us exactly when that's true -- once it posts, the real BatterRecord data
always overrides whatever this module inferred; see PROBABLE FIX
milestone).

WHY THIS EXISTS: MLB Stats API has no concept of a "probable hitter" the
way it does a probable PITCHER (research/models.py::PitcherRecord).
Early in the day, before lineups post, dfs/eligibility.py has nothing to
say about hitters at all -- every one of them is honestly
LINEUP_UNCONFIRMED. Real DFS sites already show probable/projected
starters at this point, built from real historical evidence. This
module is that evidence layer, built ENTIRELY from data this project
already knows how to fetch (research/collector.py's existing MLB Stats
API wrappers) -- never a new, unvetted data source, never a fabricated
guess.

SIGNALS USED (real, MLB Stats API, all real, all cited in the resulting
`reason` string -- never fabricated):
  - recent starts: did this player appear in a recent game's actual
    starting batting order (boxscore), and how many of the last few games
  - recent batting-order slot: this player's most recent start's slot
  - recent bench pattern: whether the player sat out the most-recent of
    the considered games despite starting earlier ones
  - active roster status: is this player on the team's TODAY active
    roster at all (fetch_team_roster) -- absence is a real, strong signal
    (injured list, optioned, traded, DFA'd) -- see OUT below
  - platoon usage / handedness of the opposing starter: season vs-RHP/
    vs-LHP split (research/collector.py's existing
    fetch_batter_platoon_split), compared against today's real opposing
    probable pitcher's throwing hand

CONFIDENCE is a small, deterministic, transparent function of ONLY the
above real signals -- see `_classify_confidence`'s own docstring for the
exact rule. A player with ZERO real recent starts in the lookback window
is never included in the result at all (no confidence level low enough
to justify a pure guess) -- "do not create fantasy guesses with no
basis" is enforced by construction, not by a threshold that could be
tuned away.

Deliberately independent of dfs/eligibility.py itself (this module knows
nothing about DK rows, game_ids, or DFSPlayer) so it can be tested and
reasoned about in complete isolation -- dfs/eligibility.py is the one
place that combines this module's real output with the rest of the
eligibility picture.
"""

import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from research import cache
from research.batter_enrichment import parse_platoon_split
from research.collector import (
    fetch_batter_platoon_split,
    fetch_boxscore,
    fetch_team_recent_schedule,
    fetch_team_roster,
)

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

# How far back to look for a team's most recent played games, and how
# many of those (most recent first) actually get inspected. Deliberately
# small and recent -- "recent starts"/"recent bench pattern" per the
# milestone's own signal list, never a season-long lookback that would
# blur a genuine, current lineup change (a new call-up, a trade, a return
# from injury) with stale history.
RECENT_GAMES_LOOKBACK_DAYS = 12
RECENT_GAMES_MAX_CONSIDERED = 3

# A platoon split needs a real, meaningful sample before it's allowed to
# downgrade a confidence level -- an early-season 8-PA split is noise,
# not evidence. Mirrors the kind of sample-size discipline
# research/batter_enrichment.py already applies elsewhere in this
# codebase.
MIN_PLATOON_PLATE_APPEARANCES = 25
# A real, meaningful platoon-split gap (OPS points) below which we don't
# treat the matchup as a genuine disadvantage worth downgrading over.
PLATOON_OPS_DISADVANTAGE_THRESHOLD = 0.060


@dataclass
class ProbableHitterInfo:
    """One hitter's real, evidence-based probable-starter determination
    for a specific team+game. `on_active_roster=False` means this
    player has real recent-starts history but is NOT on today's active
    roster (research/collector.py::fetch_team_roster) -- dfs/eligibility.py
    maps that to OUT, never a guessed-eligible status."""

    mlb_player_id: str
    name: str
    on_active_roster: bool
    projected_batting_order: Optional[int]
    confidence: str  # HIGH | MEDIUM | LOW -- only meaningful when on_active_roster
    reason: str
    recent_starts_considered: int
    recent_starts_found: int
    # Filled in by build_probable_hitters_map (which has real per-game
    # team/opponent context that infer_probable_hitters_for_team, keyed
    # only by team_id, does not) -- None when this object was built
    # directly by infer_probable_hitters_for_team alone. Lets a
    # downstream consumer (e.g. research/adapters/batter_input.py::
    # build_batter_inputs_with_probables) build a complete real
    # BatterInput without needing to separately re-derive game context.
    team_abbr: Optional[str] = None
    opponent_abbr: Optional[str] = None
    game_id: Optional[str] = None


def _fetch_recent_completed_game_ids(team_id: str, slate_date: str) -> List[str]:
    """Real, chronological (most-recent-first) list of this team's own
    completed ("Final") game IDs (plus their officialDate) in the
    lookback window strictly BEFORE `slate_date` -- never today's own
    games (this is pregame inference for TODAY, using only genuinely
    historical, already-played games; see
    research/collector.py::fetch_boxscore's own docstring on why this is
    not a lookahead-bias concern). Returns a list of (game_id, date)
    tuples, most-recent-first, capped at RECENT_GAMES_MAX_CONSIDERED."""
    end = (datetime.strptime(slate_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.strptime(slate_date, "%Y-%m-%d") - timedelta(days=RECENT_GAMES_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    schedule = fetch_team_recent_schedule(team_id, start, end)
    if not schedule:
        return []

    finals: List[tuple] = []
    for date_block in schedule.get("dates", []):
        for game in date_block.get("games", []):
            status = (game.get("status") or {}).get("detailedState")
            game_pk = game.get("gamePk")
            official_date = game.get("officialDate")
            if status == "Final" and game_pk is not None and official_date:
                finals.append((official_date, str(game_pk)))

    finals.sort(key=lambda t: t[0], reverse=True)
    return finals[:RECENT_GAMES_MAX_CONSIDERED]


def _which_side(boxscore: dict, team_id: str) -> Optional[str]:
    for side in ("home", "away"):
        team_block = ((boxscore.get("teams") or {}).get(side) or {}).get("team") or {}
        if str(team_block.get("id")) == str(team_id):
            return side
    return None


def _extract_team_starting_order(boxscore: dict, side: str) -> Dict[str, int]:
    """{mlb_player_id: batting_order_slot (1-9)} for the real starting 9
    of `side` ('home'/'away') in this historical boxscore. The team-level
    `battingOrder` list IS the real starting lineup order -- position in
    that list (not the player's own string `battingOrder` field, which
    can be absent/malformed for a mid-game substitute) is authoritative."""
    team_block = (boxscore.get("teams") or {}).get(side) or {}
    batting_order_ids = team_block.get("battingOrder") or []
    return {str(player_id): slot for slot, player_id in enumerate(batting_order_ids, start=1)}


def _extract_team_player_names(boxscore: dict, side: str) -> Dict[str, str]:
    """{mlb_player_id: real full name}, straight from the SAME boxscore's
    own `players` map (`ID<id>.person.fullName`) -- never a placeholder.
    Covers every player who appeared in this game, not just the starting
    9, so a probable candidate's real name is available even if this
    specific game wasn't the one where they started."""
    team_block = (boxscore.get("teams") or {}).get(side) or {}
    players = team_block.get("players") or {}
    names: Dict[str, str] = {}
    for key, entry in players.items():
        person = (entry or {}).get("person") or {}
        player_id = person.get("id")
        full_name = person.get("fullName")
        if player_id is not None and full_name:
            names[str(player_id)] = full_name
    return names


def _classify_confidence(started_flags: List[bool]) -> str:
    """`started_flags` is most-recent-first, one bool per considered game
    (True = started, False = did not start) -- always has at least one
    True (a player with zero starts is never passed in at all).

    HIGH   -- started the MOST RECENT considered game, AND started at
              least 2 of the games considered overall (a consistent,
              current starter, not a one-off).
    MEDIUM -- started the most recent considered game, but with only 1
              data point (fewer games were available/considered), OR
              started 2+ games considered but NOT the most recent one (a
              possible, not-yet-confirmed recent bench pattern).
    LOW    -- has at least one real start somewhere in the considered
              window, but was NOT in the most recent 1-2 games (a real,
              if weaker, signal -- e.g. a part-time role or a real recent
              bench pattern).
    """
    total_starts = sum(1 for flag in started_flags if flag)
    started_most_recent = bool(started_flags) and started_flags[0]

    if started_most_recent and total_starts >= 2:
        return HIGH
    if started_most_recent:
        return MEDIUM
    return LOW


def infer_probable_hitters_for_team(
    team_id: str,
    slate_date: str,
    opposing_pitcher_throws: Optional[str] = None,
    cache_root=cache.DEFAULT_RESULTS_CACHE_ROOT,
) -> Dict[str, ProbableHitterInfo]:
    """Real, evidence-based probable-hitter inference for one team, for
    a slate on `slate_date`. Returns {mlb_player_id: ProbableHitterInfo}
    -- ONLY for players with at least one real recent start in the
    lookback window (see module docstring: never a guess with no basis).

    `opposing_pitcher_throws` ("R"/"L"/None): today's real opposing
    probable pitcher's throwing hand, if known (research/models.py::
    PitcherRecord.throws) -- used only as an optional confidence
    DOWNGRADE when a real, adequately-sampled season platoon split shows
    a genuine disadvantage against that hand (see module docstring's
    sample-size/threshold constants). Never upgrades confidence, and
    never excludes a player outright -- a real platoon concern is
    disclosed in `reason`, not silently hidden by omission.

    Never raises: every network call already returns None on failure
    (research/collector.py's own convention) and is treated as "no
    evidence available" rather than a crash.
    """
    recent_games = _fetch_recent_completed_game_ids(team_id, slate_date)
    if not recent_games:
        return {}

    roster = fetch_team_roster(team_id, "active")
    active_ids = {
        str(entry["person"]["id"])
        for entry in (roster or {}).get("roster", [])
        if entry.get("person", {}).get("id") is not None
    }

    # One starting_order dict per game in recent_games, same
    # most-recent-first order -- {} for a game whose boxscore couldn't be
    # fetched at all (treated as "no evidence from that game", never a
    # guessed absence vs. presence). names_by_player accumulates each
    # player's real, boxscore-sourced full name -- never a placeholder.
    starting_orders: List[Dict[str, int]] = []
    names_by_player: Dict[str, str] = {}
    for _game_date, game_id in recent_games:
        boxscore = cache.get_or_fetch(
            cache_root, slate_date, f"probable_boxscore_{game_id}",
            lambda gid=game_id: fetch_boxscore(gid),
        )
        side = _which_side(boxscore, team_id) if boxscore else None
        starting_orders.append(_extract_team_starting_order(boxscore, side) if side else {})
        if side:
            names_by_player.update(_extract_team_player_names(boxscore, side))

    # Every player who started ANY of the considered games, so each gets
    # a flags list properly aligned across ALL considered games (not just
    # the games after their first appearance).
    all_starters = {pid for order in starting_orders for pid in order}

    results: Dict[str, ProbableHitterInfo] = {}
    for player_id in all_starters:
        flags = [player_id in order for order in starting_orders]
        starts = [
            (recent_games[i][0], starting_orders[i][player_id])
            for i in range(len(recent_games))
            if flags[i]
        ]
        if not starts:
            continue
        on_roster = player_id in active_ids
        most_recent_date, most_recent_slot = starts[0]

        if not on_roster:
            results[player_id] = ProbableHitterInfo(
                mlb_player_id=player_id,
                name=names_by_player.get(player_id, ""),
                on_active_roster=False,
                projected_batting_order=None,
                confidence=LOW,
                reason=(
                    f"Started {len(starts)} of the last {len(recent_games)} completed games "
                    f"considered (most recently {most_recent_date}, batting {most_recent_slot}), "
                    "but is NOT on today's active roster."
                ),
                recent_starts_considered=len(recent_games),
                recent_starts_found=len(starts),
            )
            continue

        confidence = _classify_confidence(flags)
        reason_parts = [
            f"Started {len(starts)} of the last {len(recent_games)} completed games considered",
            f"most recently {most_recent_date} batting {most_recent_slot}",
            "on today's active roster",
        ]
        if not flags[0]:
            reason_parts.append("did not start the most recent of those games")

        platoon_note = _platoon_disadvantage_note(player_id, slate_date, opposing_pitcher_throws)
        if platoon_note:
            reason_parts.append(platoon_note)
            if confidence == HIGH:
                confidence = MEDIUM
            elif confidence == MEDIUM:
                confidence = LOW

        results[player_id] = ProbableHitterInfo(
            mlb_player_id=player_id,
            name=names_by_player.get(player_id, ""),
            on_active_roster=True,
            projected_batting_order=most_recent_slot,
            confidence=confidence,
            reason="; ".join(reason_parts) + ".",
            recent_starts_considered=len(recent_games),
            recent_starts_found=len(starts),
        )

    return results


def build_probable_hitters_map(date: str, package: dict) -> Dict[Tuple[str, str], ProbableHitterInfo]:
    """The one shared entry point both dfs/pool_builder.py (legacy) and
    scripts/compute_canonical_eligibility.py (canonical Postgres) call --
    never a second, divergent implementation of "which teams need
    probable-hitter inference, and with what opposing-pitcher context."

    `package` is the same research-package dict shape both callers
    already have (`games`/`pitchers`/`batters` -- research/models.py's
    Game/PitcherRecord/BatterRecord, as plain dicts). Real, evidence-based
    inference (infer_probable_hitters_for_team) is computed ONLY for a
    (game, team) whose official lineup has NOT posted yet -- confirmed
    real data always wins outright, a probable guess is never computed
    (let alone used) once it's moot. Never raises: one team's inference
    failing must never block the rest of the slate."""
    games = package.get("games") or []
    batters = package.get("batters") or []
    pitchers = package.get("pitchers") or []

    posted_team_games = {(str(b["game_id"]), str(b["team_abbr"])) for b in batters}
    throws_by_game_team = {(str(p["game_id"]), str(p["team_abbr"])): p.get("throws") for p in pitchers}

    # MLB AUTOMATIC PIPELINE RELIABILITY Phase 1 diagnostic timing:
    # per-team elapsed time for the REAL MLB Stats API work this function
    # does (fetch_team_recent_schedule/fetch_team_roster/fetch_boxscore,
    # each cached in research/cache.py but only after the first real
    # fetch) -- printed to stderr (captured in the worker log, never
    # stdout, so it can never be mistaken for this script's own
    # RESULT_JSON contract) so a genuine slow/uncached team is visible
    # per-invocation, not just as one opaque total. Kept permanently
    # (cheap -- one print per team needing inference, never per player)
    # rather than removed after diagnosis, matching this milestone's own
    # "explicit per-slate progress" bounded-execution requirement.
    result: Dict[Tuple[str, str], ProbableHitterInfo] = {}
    teams_needing_inference = 0
    inference_seconds_total = 0.0
    for game in games:
        game_id = str(game.get("game_id"))
        for side_team_key, side_team_id_key, opponent_team_key in (
            ("home_team_abbr", "home_team_id", "away_team_abbr"),
            ("away_team_abbr", "away_team_id", "home_team_abbr"),
        ):
            team_abbr = game.get(side_team_key)
            team_id = game.get(side_team_id_key)
            opponent_abbr = game.get(opponent_team_key)
            if not team_abbr or not team_id:
                continue
            if (game_id, str(team_abbr)) in posted_team_games:
                continue  # official lineup already posted -- never compute or use a probable guess here

            opposing_throws = throws_by_game_team.get((game_id, str(opponent_abbr)))
            team_started = time.monotonic()
            try:
                team_probables = infer_probable_hitters_for_team(str(team_id), date, opposing_pitcher_throws=opposing_throws)
            except Exception:  # noqa: BLE001 -- one team's real-evidence lookup failing must never block the slate
                team_probables = {}
            team_elapsed = time.monotonic() - team_started
            teams_needing_inference += 1
            inference_seconds_total += team_elapsed
            print(f"[probable_hitters] team={team_abbr} game={game_id} elapsed={team_elapsed:.2f}s", file=sys.stderr, flush=True)
            for mlb_player_id, info in team_probables.items():
                result[(game_id, mlb_player_id)] = replace(
                    info, team_abbr=str(team_abbr), opponent_abbr=str(opponent_abbr) if opponent_abbr else None, game_id=game_id,
                )

    print(
        f"[probable_hitters] date={date} teams_needing_inference={teams_needing_inference} "
        f"total_inference_seconds={inference_seconds_total:.2f}",
        file=sys.stderr, flush=True,
    )
    return result


def _platoon_disadvantage_note(player_id: str, slate_date: str, opposing_pitcher_throws: Optional[str]) -> Optional[str]:
    """Real, sample-size-gated platoon check -- returns a human-readable
    disadvantage note, or None when there's no real evidence of one (no
    opposing throwing hand known, no adequately-sampled split, or no
    meaningful gap). Never raises."""
    if opposing_pitcher_throws not in ("R", "L"):
        return None

    season = slate_date[:4]
    sit_code = "vr" if opposing_pitcher_throws == "R" else "vl"
    other_sit_code = "vl" if opposing_pitcher_throws == "R" else "vr"

    raw_same = fetch_batter_platoon_split(player_id, season, sit_code)
    raw_other = fetch_batter_platoon_split(player_id, season, other_sit_code)
    retrieved_at = datetime.now(timezone.utc).isoformat()
    same_line = parse_platoon_split(raw_same, player_id, season, sit_code, retrieved_at)
    other_line = parse_platoon_split(raw_other, player_id, season, other_sit_code, retrieved_at)

    if not same_line or not other_line:
        return None
    if (same_line.plate_appearances or 0) < MIN_PLATOON_PLATE_APPEARANCES:
        return None
    if same_line.ops is None or other_line.ops is None:
        return None

    gap = other_line.ops - same_line.ops
    if gap < PLATOON_OPS_DISADVANTAGE_THRESHOLD:
        return None

    hand_label = "RHP" if opposing_pitcher_throws == "R" else "LHP"
    return (
        f"real season platoon split shows a weaker line vs {hand_label} "
        f"({same_line.ops:.3f} OPS in {same_line.plate_appearances} PA vs {other_line.ops:.3f} OPS otherwise), "
        f"and today's opposing probable starter throws {opposing_pitcher_throws}"
    )
