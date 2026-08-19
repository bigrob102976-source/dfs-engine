"""Milestone 30.1: tests for dfs/eligibility.py -- the optimizer-eligible
player pool filtering layer (STARTING_PITCHER/STARTING_HITTER/
LINEUP_UNCONFIRMED/BENCH/RELIEF_PITCHER/SCRATCHED/UNMATCHED/AMBIGUOUS)."""

from dfs.eligibility import (
    AMBIGUOUS,
    BENCH,
    LINEUP_UNCONFIRMED,
    RELIEF_PITCHER,
    SCRATCHED,
    STARTING_HITTER,
    STARTING_PITCHER,
    UNMATCHED,
    compute_eligibility,
    eligibility_counts,
)
from dfs.models import DFSPlayer


def _pitcher(dk_id, mlb_id, game_id, team="BOS", opponent="TOR", match_status="matched"):
    return DFSPlayer(
        dk_player_id=dk_id, name=f"Pitcher {dk_id}", team=team, player_type="pitcher",
        dk_positions=["P"], salary=8000, mlb_player_id=mlb_id, opponent=opponent, game_id=game_id,
        match_status=match_status,
    )


def _hitter(dk_id, mlb_id, game_id, team="BOS", opponent="TOR", match_status="matched"):
    return DFSPlayer(
        dk_player_id=dk_id, name=f"Hitter {dk_id}", team=team, player_type="hitter",
        dk_positions=["OF"], salary=4000, mlb_player_id=mlb_id, opponent=opponent, game_id=game_id,
        match_status=match_status,
    )


def _research_pitcher(game_id, player_id, team_abbr="BOS"):
    return {"player_id": player_id, "name": "X", "team_id": "1", "team_abbr": team_abbr,
            "opponent_team_id": "2", "opponent_abbr": "TOR", "game_id": game_id, "status": "probable"}


def _research_batter(game_id, player_id, team_abbr, batting_order):
    return {"player_id": player_id, "name": "Y", "team_id": "1", "team_abbr": team_abbr,
            "opponent_team_id": "2", "opponent_abbr": "TOR", "game_id": game_id,
            "batting_order": batting_order, "status": "starting_lineup"}


def test_starting_pitcher_eligible():
    players = [_pitcher("d1", "p1", "g1")]
    compute_eligibility(players, [_research_pitcher("g1", "p1")], [])
    assert players[0].eligibility_status == STARTING_PITCHER
    assert players[0].optimizer_eligible is True


def test_relief_pitcher_excluded():
    """A matched real MLB pitcher who is NOT today's probable starter for
    this game -- must be RELIEF_PITCHER, not eligible."""
    players = [_pitcher("d1", "relief_id", "g1")]
    compute_eligibility(players, [_research_pitcher("g1", "someone_else")], [])
    assert players[0].eligibility_status == RELIEF_PITCHER
    assert players[0].optimizer_eligible is False


def test_sp_not_actual_starter_for_this_game_excluded():
    """A pitcher who IS a probable starter -- but for a DIFFERENT game --
    must not be eligible for this DK row's game."""
    players = [_pitcher("d1", "p1", "g1")]
    compute_eligibility(players, [_research_pitcher("g2", "p1")], [])  # p1 starts g2, not g1
    assert players[0].eligibility_status == RELIEF_PITCHER
    assert players[0].optimizer_eligible is False


def test_confirmed_hitter_eligible():
    players = [_hitter("d1", "h1", "g1", team="BOS")]
    compute_eligibility(players, [], [_research_batter("g1", "h1", "BOS", 3)])
    assert players[0].eligibility_status == STARTING_HITTER
    assert players[0].optimizer_eligible is True
    assert players[0].batting_order == 3


def test_bench_hitter_excluded():
    """Team's lineup HAS posted (another player from the same team+game
    is in the batter research list), but this specific player is not."""
    players = [_hitter("d1", "bench_id", "g1", team="BOS")]
    compute_eligibility(players, [], [_research_batter("g1", "someone_else", "BOS", 1)])
    assert players[0].eligibility_status == BENCH
    assert players[0].optimizer_eligible is False


def test_lineup_unconfirmed_hitter_preserved_and_not_eligible():
    """No batter research records at all for this team+game -- the
    lineup hasn't posted. Row is preserved (still in the list) but not
    eligible."""
    players = [_hitter("d1", "h1", "g1", team="BOS")]
    compute_eligibility(players, [], [])  # no lineups posted anywhere
    assert players[0].eligibility_status == LINEUP_UNCONFIRMED
    assert players[0].optimizer_eligible is False


def test_unmatched_hitter_with_unposted_lineup_is_lineup_unconfirmed_not_unmatched():
    """Live-validation-discovered case (2026-08-19 LAD @ COL): dfs/
    player_resolver.py's identity canonical index only ever contains
    POSTED-lineup hitters -- a hitter whose team's lineup hasn't posted
    yet is EXPECTED to fail identity match entirely (match_status=
    "unmatched"), not because their identity is genuinely unknowable.
    game_id/team are still resolved at the game level independent of
    player-identity match, so this must read as LINEUP_UNCONFIRMED, the
    same as a matched-but-not-in-lineup hitter -- never a bare UNMATCHED
    that would hide the real reason (waiting on a lineup) from an admin."""
    players = [_hitter("d1", None, "g1", team="LAD", match_status="unmatched")]
    compute_eligibility(players, [], [])  # no lineups posted anywhere for g1/LAD
    assert players[0].eligibility_status == LINEUP_UNCONFIRMED
    assert players[0].optimizer_eligible is False


def test_unmatched_hitter_with_posted_lineup_stays_unmatched():
    """The team's lineup HAS posted, but this specific DK row still
    couldn't be identity-matched to any of it -- a genuinely unresolvable
    row (e.g. a name/team mismatch), not merely "waiting." Must stay
    UNMATCHED, never guessed into BENCH without a confirmed identity."""
    players = [_hitter("d1", None, "g1", team="BOS", match_status="unmatched")]
    compute_eligibility(players, [], [_research_batter("g1", "someone_else", "BOS", 1)])
    assert players[0].eligibility_status == UNMATCHED
    assert players[0].optimizer_eligible is False


def test_raw_dk_rows_never_deleted():
    """Every DK row survives compute_eligibility regardless of status --
    only labeled, never dropped."""
    players = [
        _pitcher("d1", "p1", "g1"),          # starter
        _pitcher("d2", "relief", "g1"),      # reliever
        _hitter("d3", "h1", "g1", "BOS"),    # confirmed
        _hitter("d4", "bench", "g1", "BOS"), # bench
        _hitter("d5", "unc", "g2", "TOR"),   # unconfirmed
        DFSPlayer(dk_player_id="d6", name="Nobody", team="BOS", player_type="hitter",
                  dk_positions=["OF"], salary=3000, match_status="unmatched"),  # unmatched
    ]
    compute_eligibility(
        players,
        [_research_pitcher("g1", "p1")],
        [_research_batter("g1", "h1", "BOS", 1), _research_batter("g1", "bench", "BOS", None)],
    )
    assert len(players) == 6
    assert [p.dk_player_id for p in players] == ["d1", "d2", "d3", "d4", "d5", "d6"]
    assert players[5].eligibility_status == UNMATCHED
    assert players[5].optimizer_eligible is False


def test_unmatched_and_ambiguous_never_eligible():
    unmatched = DFSPlayer(dk_player_id="d1", name="X", team="BOS", player_type="hitter",
                           dk_positions=["OF"], salary=3000, match_status="unmatched")
    ambiguous = DFSPlayer(dk_player_id="d2", name="Y", team="BOS", player_type="hitter",
                           dk_positions=["OF"], salary=3000, match_status="ambiguous")
    players = [unmatched, ambiguous]
    compute_eligibility(players, [], [])
    assert players[0].eligibility_status == UNMATCHED
    assert players[1].eligibility_status == AMBIGUOUS
    assert players[0].optimizer_eligible is False
    assert players[1].optimizer_eligible is False


def test_scratch_removes_eligibility():
    """A player who WAS STARTING_PITCHER as of the previous build, but is
    no longer the confirmed starter now, becomes SCRATCHED."""
    players = [_pitcher("d1", "p1", "g1")]
    # This build: p1 is no longer the probable starter for g1 (someone else is).
    compute_eligibility(players, [_research_pitcher("g1", "someone_else")], [],
                         previous_eligibility_by_dk_id={"d1": STARTING_PITCHER})
    assert players[0].eligibility_status == SCRATCHED
    assert players[0].optimizer_eligible is False


def test_scratch_applies_to_hitters_too():
    players = [_hitter("d1", "h1", "g1", team="BOS")]
    compute_eligibility(players, [], [_research_batter("g1", "someone_else", "BOS", 1)],
                         previous_eligibility_by_dk_id={"d1": STARTING_HITTER})
    assert players[0].eligibility_status == SCRATCHED


def test_refresh_promotes_hitter_to_starter():
    """Previously LINEUP_UNCONFIRMED (no prior STARTING_* status to
    scratch from) -- once the lineup posts, the same player becomes
    STARTING_HITTER on the next compute_eligibility call. No scratch
    override applies since the prior status wasn't a confirmed one."""
    players = [_hitter("d1", "h1", "g1", team="BOS")]
    compute_eligibility(players, [], [_research_batter("g1", "h1", "BOS", 2)],
                         previous_eligibility_by_dk_id={"d1": LINEUP_UNCONFIRMED})
    assert players[0].eligibility_status == STARTING_HITTER
    assert players[0].optimizer_eligible is True


def test_refresh_marks_bench_once_lineup_posts():
    players = [_hitter("d1", "not_picked", "g1", team="BOS")]
    compute_eligibility(players, [], [_research_batter("g1", "someone_else", "BOS", 1)],
                         previous_eligibility_by_dk_id={"d1": LINEUP_UNCONFIRMED})
    assert players[0].eligibility_status == BENCH


def test_doubleheader_game_specific_starter():
    """The same real pitcher starts Game 1 (g1) but not Game 2 (g2) --
    each DK row for a distinct game_id must be evaluated independently."""
    game1_row = _pitcher("d1", "p1", "g1")
    game2_row = _pitcher("d2", "p1", "g2")  # same mlb_player_id, different game
    players = [game1_row, game2_row]
    compute_eligibility(players, [_research_pitcher("g1", "p1")], [])  # p1 only confirmed for g1
    assert players[0].eligibility_status == STARTING_PITCHER
    assert players[1].eligibility_status == RELIEF_PITCHER


def test_same_name_identity_safety_uses_game_id_and_player_id_not_name():
    """Two different real players who happen to share a DK-visible name,
    on different teams/games -- eligibility must never bleed across them
    since joins are keyed by (game_id, mlb_player_id), never by name."""
    player_a = _pitcher("d1", "mlb_111", "gameA", team="LAD")
    player_b = _pitcher("d2", "mlb_222", "gameB", team="NYY")
    players = [player_a, player_b]
    # Only mlb_111 (gameA) is a confirmed starter; mlb_222 (gameB) is not,
    # even though both DK rows are named "Pitcher d1"/"Pitcher d2" and
    # nothing here disambiguates by name at all.
    compute_eligibility(players, [_research_pitcher("gameA", "mlb_111")], [])
    assert players[0].eligibility_status == STARTING_PITCHER
    assert players[1].eligibility_status == RELIEF_PITCHER


def test_eligibility_counts_breakdown():
    players = [
        _pitcher("d1", "p1", "g1"),
        _pitcher("d2", "relief", "g1"),
        _hitter("d3", "h1", "g1", "BOS"),
        _hitter("d4", "bench_id", "g1", "BOS"),
        _hitter("d5", "unc", "g2", "TOR"),
    ]
    compute_eligibility(
        players, [_research_pitcher("g1", "p1")],
        [_research_batter("g1", "h1", "BOS", 1)],  # only h1 is in the posted BOS lineup; bench_id is not
    )
    counts = eligibility_counts(players)
    assert counts["raw_dk_players"] == 5
    assert counts["starting_pitchers"] == 1
    assert counts["relief_pitchers"] == 1
    assert counts["confirmed_hitters"] == 1
    assert counts["bench_hitters"] == 1
    assert counts["waiting_for_lineups"] == 1
    assert counts["optimizer_eligible"] == 2
