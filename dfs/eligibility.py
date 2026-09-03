"""Milestone 30.1 (extended by the PROBABLE FIX milestone): optimizer-
eligible player pool filtering.

Adds `eligibility_status`/`optimizer_eligible` to every already-built
DFSPlayer, in place, WITHOUT deleting or reordering any row -- every DK
salary row is preserved regardless of status (see dfs/player_pool.py's
own module docstring for this same "never silently drop" discipline,
which this module extends rather than replaces).

Computed from the RAW research package (research_output/<date>/pitchers.json
and batters.json -- research/models.py's PitcherRecord/BatterRecord),
never from the AI/agent-scored board snapshots
(predictions/*_board_*.json). This is deliberate: "is this player a
confirmed starter" is an MLB-data fact, independent of whether our own
projection model happens to have produced a projection for them yet --
computing eligibility from board-snapshot presence would make a data-
quality/model gap (a real starter our model couldn't project) look
identical to "this is a genuine bench player." Native/AI projection
*coverage* is measured separately, against this eligibility layer -- see
dfs/eligibility.py callers in the dashboard, not this module.

STATUS VALUES (eligibility_status):
    STARTING_PITCHER    -- matched today's probable/confirmed MLB starter for this exact game_id
    STARTING_HITTER      -- in the OFFICIALLY POSTED starting lineup for this game_id, with a batting order
    PROBABLE_HITTER       -- real-evidence-based probable starter (dfs/probable_starters.py), before the
                             official lineup posts -- see `lineup_confirmation`/`probable_*` fields below
    LINEUP_UNCONFIRMED   -- hitter whose team's lineup has not posted AND no real probable-starter evidence exists
    BENCH                 -- hitter on a team whose lineup HAS posted, but not among the starting nine
    RELIEF_PITCHER        -- matched MLB pitcher who is not today's confirmed/probable starter for this game
    OUT                    -- real recent-starts evidence exists, but the player is NOT on today's active
                              roster (injured list / optioned / traded / DFA'd) -- never optimizer_eligible
    SCRATCHED              -- was STARTING_PITCHER/STARTING_HITTER/PROBABLE_HITTER as of the immediately
                              prior pool build for this slate, no longer confirmed/probable now
    UNMATCHED              -- DK row never resolved to a real MLB player_id/game_id
    AMBIGUOUS              -- DK row resolved to more than one plausible MLB identity

optimizer_eligible is True for STARTING_PITCHER, STARTING_HITTER, and
PROBABLE_HITTER only -- PROBABLE_HITTER is deliberately eligible (real
DFS sites already let you roster probable starters), but the DISTINCTION
from a confirmed starter is always preserved via DFSPlayer.lineup_confirmation
("CONFIRMED" | "PROBABLE" | None), never collapsed into eligibility_status
alone. STARTING_PITCHER also carries lineup_confirmation -- "CONFIRMED"
once this team's own lineup has officially posted (the same
posted_team_games signal already used for hitters), "PROBABLE" before
that -- MLB's probable-pitcher designation is usually reliable but is
not itself an official lineup card.

Every join is keyed by (game_id, mlb_player_id) -- never by name alone --
so a same-named player on a different team/game can never bleed into the
wrong game's eligibility (a doubleheader's Game 1 starter must not read
as eligible for Game 2 just because the name matches; each game has its
own game_id, so this falls out naturally from the key shape).
"""

from typing import Dict, List, Optional, Set, Tuple

from dfs.models import DFSPlayer
from dfs.probable_starters import ProbableHitterInfo

STARTING_PITCHER = "STARTING_PITCHER"
STARTING_HITTER = "STARTING_HITTER"
PROBABLE_HITTER = "PROBABLE_HITTER"
LINEUP_UNCONFIRMED = "LINEUP_UNCONFIRMED"
BENCH = "BENCH"
RELIEF_PITCHER = "RELIEF_PITCHER"
OUT = "OUT"
SCRATCHED = "SCRATCHED"
UNMATCHED = "UNMATCHED"
AMBIGUOUS = "AMBIGUOUS"

CONFIRMED = "CONFIRMED"
PROBABLE = "PROBABLE"

OPTIMIZER_ELIGIBLE_STATUSES = frozenset({STARTING_PITCHER, STARTING_HITTER, PROBABLE_HITTER})

# The statuses that are "scratchable" -- only a player who WAS confirmed
# or probable can be SCRATCHED. A player who was already
# RELIEF_PITCHER/BENCH/OUT/etc. simply keeps being whatever they are
# now; there is no "un-scratch."
_SCRATCHABLE_PRIOR_STATUSES = frozenset({STARTING_PITCHER, STARTING_HITTER, PROBABLE_HITTER})

# Keyed the same way as lineup_index below: (game_id, mlb_player_id).
ProbableHitterMap = Dict[Tuple[str, str], ProbableHitterInfo]


def _key(game_id: object, player_id: object) -> Tuple[str, str]:
    return (str(game_id), str(player_id))


def compute_eligibility(
    players: List[DFSPlayer],
    research_pitchers: List[dict],
    research_batters: List[dict],
    previous_eligibility_by_dk_id: Optional[Dict[str, str]] = None,
    probable_hitters: Optional[ProbableHitterMap] = None,
) -> None:
    """Mutates every player in `players` in place, setting
    `eligibility_status`, `optimizer_eligible`, `lineup_confirmation`,
    and (for PROBABLE_HITTER only) `probable_confidence`/`probable_reason`/
    `projected_batting_order`.

    `research_pitchers`/`research_batters` are the raw
    research_output/<date>/pitchers.json and batters.json lists (plain
    dicts, as loaded by research/adapters/*_input.py::load_research_package
    -- PitcherRecord/BatterRecord shaped) for this slate date.

    `previous_eligibility_by_dk_id` (optional): dk_player_id ->
    eligibility_status from the immediately prior pool build for this
    same (date, slate_id), enabling SCRATCHED detection. Omit (or pass
    None/{}) for a first build -- every player is then evaluated fresh
    with no scratch detection, which is correct: there is nothing to
    scratch FROM yet.

    `probable_hitters` (optional, additive -- PROBABLE FIX milestone):
    {(game_id, mlb_player_id): ProbableHitterInfo}, real evidence-based
    probable-starter data from dfs/probable_starters.py, for hitters
    whose team's official lineup has NOT posted yet. Omitted entirely
    (None, the default) means every pre-existing caller gets byte-for-
    byte the same behavior as before this milestone -- a hitter with no
    posted lineup simply stays LINEUP_UNCONFIRMED, exactly as always.
    Only consulted for a (game_id, team) NOT already in posted_team_games
    -- an OFFICIALLY POSTED lineup always wins outright, a probable
    guess is never allowed to override or coexist with real confirmed
    data for the same team+game.
    """
    starter_keys: Set[Tuple[str, str]] = {_key(r["game_id"], r["player_id"]) for r in research_pitchers}
    lineup_index: Dict[Tuple[str, str], dict] = {_key(r["game_id"], r["player_id"]): r for r in research_batters}
    # "Has this team's lineup posted for this game" is derived from
    # batter research-record PRESENCE for that (game_id, team) -- MLB
    # only publishes lineups.homePlayers/awayPlayers once the lineup card
    # is official (research/normalizer.py), so ANY row at all for a
    # team+game means that team's lineup has posted. The SAME signal now
    # also decides pitcher lineup_confirmation (CONFIRMED vs PROBABLE) --
    # see _compute_one.
    posted_team_games: Set[Tuple[str, str]] = {(str(r["game_id"]), str(r["team_abbr"])) for r in research_batters}

    previous = previous_eligibility_by_dk_id or {}
    probable = probable_hitters or {}

    for player in players:
        status, confirmation, probable_info = _compute_one(player, starter_keys, lineup_index, posted_team_games, probable)

        previous_status = previous.get(player.dk_player_id)
        # PROBABLE FIX: SCRATCHED means "lost their expected-to-play
        # status," never "moved between two still-eligible statuses."
        # PROBABLE_HITTER -> STARTING_HITTER (the real, desired
        # probable-to-confirmed promotion) must never look like a
        # scratch just because the literal status string changed.
        if previous_status in _SCRATCHABLE_PRIOR_STATUSES and status not in OPTIMIZER_ELIGIBLE_STATUSES:
            status = SCRATCHED
            confirmation = None
            probable_info = None

        player.eligibility_status = status
        player.optimizer_eligible = status in OPTIMIZER_ELIGIBLE_STATUSES
        player.lineup_confirmation = confirmation

        if status == STARTING_HITTER:
            record = lineup_index.get(_key(player.game_id, player.mlb_player_id))
            if record is not None and record.get("batting_order") is not None:
                player.batting_order = record["batting_order"]
        elif status == PROBABLE_HITTER and probable_info is not None:
            player.probable_confidence = probable_info.confidence
            player.probable_reason = probable_info.reason
            player.projected_batting_order = probable_info.projected_batting_order


def _compute_one(
    player: DFSPlayer,
    starter_keys: Set[Tuple[str, str]],
    lineup_index: Dict[Tuple[str, str], dict],
    posted_team_games: Set[Tuple[str, str]],
    probable_hitters: ProbableHitterMap,
) -> Tuple[str, Optional[str], Optional[ProbableHitterInfo]]:
    """Returns (eligibility_status, lineup_confirmation, probable_info)."""
    if player.match_status == "ambiguous":
        return AMBIGUOUS, None, None

    if player.match_status != "matched" or not player.mlb_player_id:
        # dfs/player_resolver.py's own docstring is explicit: the
        # identity canonical index is built ONLY from today's probable
        # pitchers + POSTED-lineup hitters -- a hitter whose team's
        # lineup hasn't posted yet has no identity record to match
        # against at all, and is EXPECTED to come back unmatched here,
        # not because their identity is genuinely unknown. `game_id`/
        # `team`, unlike `mlb_player_id`, are resolved at the GAME level
        # (dfs/player_pool.py's dk_game_match) independent of whether
        # this specific player's identity matched -- so they're still
        # usable here to tell "lineup not posted yet" apart from
        # "identity genuinely unresolvable," mirroring the equivalent
        # distinction dfs/player_pool.py::_determine_lineup_status
        # already makes for the legacy lineup_status field. A DK row
        # with no mlb_player_id at all can never be matched against
        # probable_hitters either (that map is keyed by mlb_player_id) --
        # honestly stays LINEUP_UNCONFIRMED, never a guess.
        if player.player_type == "hitter" and player.game_id and (str(player.game_id), player.team) not in posted_team_games:
            return LINEUP_UNCONFIRMED, None, None
        return UNMATCHED, None, None

    if not player.game_id:
        return UNMATCHED, None, None

    key = _key(player.game_id, player.mlb_player_id)
    lineup_posted = (str(player.game_id), player.team) in posted_team_games

    if player.player_type == "pitcher":
        if key in starter_keys:
            return STARTING_PITCHER, (CONFIRMED if lineup_posted else PROBABLE), None
        return RELIEF_PITCHER, None, None

    # hitter
    if key in lineup_index:
        return STARTING_HITTER, CONFIRMED, None
    if lineup_posted:
        # The official lineup HAS posted for this team+game, and this
        # player isn't in it -- real, authoritative BENCH information
        # that always overrides any probable guess (probable inference
        # only ever applies before the real lineup exists at all).
        return BENCH, None, None

    probable_info = probable_hitters.get(key)
    if probable_info is None:
        return LINEUP_UNCONFIRMED, None, None
    if not probable_info.on_active_roster:
        return OUT, None, None
    return PROBABLE_HITTER, PROBABLE, probable_info


def eligibility_counts(players: List[DFSPlayer]) -> Dict[str, int]:
    """A count per eligibility_status, plus the optimizer_eligible total
    -- the exact breakdown the admin Slate Operations board and the
    match report surface (dfs/player_pool.py::build_match_report)."""
    counts: Dict[str, int] = {
        "starting_pitchers": 0, "relief_pitchers": 0,
        "confirmed_hitters": 0, "probable_hitters": 0, "bench_hitters": 0, "waiting_for_lineups": 0,
        "out": 0, "scratched": 0, "unmatched": 0, "ambiguous": 0,
    }
    status_to_key = {
        STARTING_PITCHER: "starting_pitchers", RELIEF_PITCHER: "relief_pitchers",
        STARTING_HITTER: "confirmed_hitters", PROBABLE_HITTER: "probable_hitters",
        BENCH: "bench_hitters", LINEUP_UNCONFIRMED: "waiting_for_lineups", OUT: "out",
        SCRATCHED: "scratched", UNMATCHED: "unmatched", AMBIGUOUS: "ambiguous",
    }
    for player in players:
        key = status_to_key.get(player.eligibility_status)
        if key:
            counts[key] += 1
    counts["optimizer_eligible"] = sum(1 for p in players if p.optimizer_eligible)
    counts["raw_dk_players"] = len(players)
    return counts
