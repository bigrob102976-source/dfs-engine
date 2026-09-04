"""NFL M6C Phase 3/5/6/7/9/10 -- builds the normalized NflUsageRecord
list for one season/week from M6A's raw weekly_player_stats/play_by_play
plus M6C's own raw snap_counts/participation, joined through the M6B
identity crosswalk.

Denominator/derivation audit trail (Phase 7 -- real numbers, 2025 Week 1,
team BUF):
  - carries: nflreadpy.load_player_stats()'s own `carries` field for BUF
    summed to 31, IDENTICAL to play-by-play `rush_attempt==1` INCLUDING
    qb_kneel plays (also 31) -- NOT the kneel-excluded count (28). This
    means nflverse's own weekly "carries" stat quietly counts kneels as
    carries. Using it as a carry_share DENOMINATOR would dilute every
    real ball-carrier's share with garbage-time kneel-downs. carry_share
    is therefore computed entirely from play-by-play with qb_kneel
    excluded on both the player numerator and the team denominator --
    never mixed with the raw `carries` stat, which is preserved
    unmodified (nflverse's familiar, official number) precisely because
    changing its meaning would be its own kind of dishonesty.
  - targets: BUF's weekly_player_stats targets summed to 45; play-by-play
    rows with a non-null receiver_player_id numbered 48 -- a real,
    unreconciled ~7% gap (likely penalty-negated plays, laterals, or
    two-point attempts; not confirmed which). Rather than build a
    denominator from a play-by-play proxy with an unexplained
    discrepancy, target_share uses nflverse's own official `targets`
    field on BOTH sides (player targets / SUM of every player's targets
    on that team+week) -- self-consistent, shares sum to 1.0 exactly,
    and matches the number every other system already calls "targets."
  - snap_share: taken directly from nflreadpy.load_snap_counts()'s own
    `offense_pct` (Pro-Football-Reference's own computed share) --
    never re-derived, since PFR already has the correct denominator.

Routes / route_participation (Phase 8): nflreadpy.load_participation()'s
real schema (confirmed live, 2016-2025) has NO per-player "ran a route"
flag -- `offense_players` is a semicolon-delimited GSIS list of everyone
on the field for that play (blockers included), and `route` is a SINGLE
play-level route-type string (e.g. "SLANT", "GO") with no field
attributing it to one of those players. Attributing that label to a
specific player would require either (a) assuming it always describes
whichever `offense_players` entry was the targeted receiver -- which
would require joining to play-by-play's own receiver_player_id, still
only capturing "targeted routes," not real total route participation
-- or (b) assuming every eligible-position player in `offense_players`
"ran a route" on every pass play, which silently fabricates data for
blocking tight ends/backs who did not release. Per this milestone's
explicit "do not infer route counts from targets, do not fabricate
routes from snaps" instruction, NEITHER is done: routes and
route_participation are left None on every M6C record, and the real
gap is reported by usage_quality.py rather than papered over.

NFL M8 adds reception_share (team_reception_share), derived exactly like
target_share above (player receptions / SUM of every player's receptions
on that team+week, both from load_player_stats()'s own `receptions`
field -- self-consistent, never a play-by-play proxy), plus real
box-score passthroughs (pass_attempts/completions/passing_yards/
passing_tds/rushing_yards/rushing_tds/receiving_yards/receiving_tds),
all DIRECT columns on load_player_stats() (confirmed live, 2025 Week 1)
-- never derived, never invented.

Red zone / goal line (Phase 9): defined here as yardline_100 <= 20
(red zone -- "at or inside the opponent's 20") and yardline_100 <= 5
(goal line -- "at or inside the opponent's 5"), using play-by-play's
own real, confirmed field semantics (yardline_100 = 0 at the opponent's
goal line, verified live against real rushing touchdowns). This is a
fixed-yardline convention, deliberately NOT nflverse's own `goal_to_go`
flag, which measures a different thing (whether a first down is
impossible without scoring, not physical distance) and would misclassify
e.g. a 3rd-and-8 snap from the 15 (a real red-zone play) as not
goal-to-go. Kneel plays are excluded from red_zone_carries/
goal_line_carries the same way they are from carry_share, for the same
reason."""

from typing import Dict, List, Optional, Tuple

from historical_nfl.usage_models import SOURCE_PBP_DERIVED, SOURCE_SNAP_COUNTS, SOURCE_WEEKLY_STATS_DERIVED, NflUsageRecord

RED_ZONE_YARDLINE_100 = 20
GOAL_LINE_YARDLINE_100 = 5


def _team_field_totals(weekly_stats_rows: List[dict], field: str) -> Dict[str, int]:
    """{team -> sum(field)} keyed just by team (one week's worth of rows
    is always pre-filtered to a single season/week by the caller). Reused
    for both target_share (field="targets") and NFL M8's reception_share
    (field="receptions") -- same self-consistent "player's own stat /
    SUM of every player's same stat on that team+week" derivation."""
    totals: Dict[str, int] = {}
    for row in weekly_stats_rows:
        team = row.get("team")
        value = row.get(field)
        if team is None or value is None:
            continue
        totals[team] = totals.get(team, 0) + value
    return totals


def _pbp_carry_counts(pbp_rows: List[dict]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Returns (team_carries, player_carries), both excluding qb_kneel."""
    team_carries: Dict[str, int] = {}
    player_carries: Dict[str, int] = {}
    for row in pbp_rows:
        if row.get("rush_attempt") != 1 or row.get("qb_kneel") == 1:
            continue
        team = row.get("posteam")
        if team:
            team_carries[team] = team_carries.get(team, 0) + 1
        rusher = row.get("rusher_player_id")
        if rusher:
            player_carries[rusher] = player_carries.get(rusher, 0) + 1
    return team_carries, player_carries


def _pbp_redzone_goalline(pbp_rows: List[dict]) -> Dict[str, dict]:
    """{gsis_id -> {"red_zone_targets": int, "red_zone_carries": int, "goal_line_carries": int}}"""
    result: Dict[str, dict] = {}

    def _bump(gsis_id: str, field: str) -> None:
        bucket = result.setdefault(gsis_id, {"red_zone_targets": 0, "red_zone_carries": 0, "goal_line_carries": 0})
        bucket[field] += 1

    for row in pbp_rows:
        yardline_100 = row.get("yardline_100")
        if yardline_100 is None:
            continue
        in_red_zone = yardline_100 <= RED_ZONE_YARDLINE_100
        in_goal_line = yardline_100 <= GOAL_LINE_YARDLINE_100

        receiver = row.get("receiver_player_id")
        if receiver and in_red_zone:
            _bump(receiver, "red_zone_targets")

        if row.get("rush_attempt") == 1 and row.get("qb_kneel") != 1:
            rusher = row.get("rusher_player_id")
            if rusher and in_red_zone:
                _bump(rusher, "red_zone_carries")
            if rusher and in_goal_line:
                _bump(rusher, "goal_line_carries")

    return result


def _snap_lookup_by_gsis(snap_counts_rows: List[dict], pfr_gsis_bridge: Dict[str, str]) -> Dict[str, dict]:
    """{gsis_id -> {offense_snaps, offense_pct, defense_snaps, st_snaps}}
    for every snap_counts row whose pfr_player_id resolves through the
    real PFR<->GSIS bridge. Unresolved rows are simply absent here --
    reported separately by the caller, never guessed."""
    lookup: Dict[str, dict] = {}
    for row in snap_counts_rows:
        gsis_id = pfr_gsis_bridge.get(row.get("pfr_player_id"))
        if not gsis_id:
            continue
        lookup[gsis_id] = {
            "offense_snaps": row.get("offense_snaps"), "offense_pct": row.get("offense_pct"),
            "defense_snaps": row.get("defense_snaps"), "st_snaps": row.get("st_snaps"),
        }
    return lookup


def build_usage_records(
    season: int, week: int,
    weekly_stats_rows: List[dict], snap_counts_rows: List[dict], pbp_rows: List[dict],
    pfr_gsis_bridge: Dict[str, str], gsis_to_canonical: Dict[str, Optional[str]],
    fetched_at: str,
) -> Tuple[List[NflUsageRecord], List[str]]:
    """Returns (records, unresolved_canonical_gsis_ids) -- the latter is
    every real GSIS ID in this week's usage that has no M6B canonical
    mapping yet (Phase 5: reported, never discarded, never guessed)."""
    team_targets = _team_field_totals(weekly_stats_rows, "targets")
    team_receptions = _team_field_totals(weekly_stats_rows, "receptions")
    team_carries, player_carries = _pbp_carry_counts(pbp_rows)
    redzone_goalline = _pbp_redzone_goalline(pbp_rows)
    snaps_by_gsis = _snap_lookup_by_gsis(snap_counts_rows, pfr_gsis_bridge)

    records: List[NflUsageRecord] = []
    unresolved: List[str] = []

    for row in weekly_stats_rows:
        gsis_id = row.get("player_id")
        if not gsis_id:
            continue  # never invent an identity for a row with none

        team = row.get("team")
        targets = row.get("targets")
        target_share = None
        team_total_targets = team_targets.get(team) if team else None
        if targets is not None and team_total_targets:
            target_share = round(targets / team_total_targets, 4)

        receptions = row.get("receptions")
        reception_share = None
        team_total_receptions = team_receptions.get(team) if team else None
        if receptions is not None and team_total_receptions:
            reception_share = round(receptions / team_total_receptions, 4)

        # A player absent from player_carries genuinely had zero
        # non-kneel rush attempts this week (every real play-by-play row
        # was scanned) -- a real, confirmed 0, not a missing value. Only
        # the DENOMINATOR being unavailable makes carry_share itself
        # unknown (None).
        carry_share = None
        player_carry_count = player_carries.get(gsis_id, 0)
        team_carry_count = team_carries.get(team) if team else None
        if team_carry_count:
            carry_share = round(player_carry_count / team_carry_count, 4)

        # Every real play-by-play row for the week was scanned, so
        # absence here is a confirmed real 0 (never touched the red
        # zone/goal line), not a missing value -- same reasoning as
        # carry_share above.
        rz = redzone_goalline.get(gsis_id, {"red_zone_targets": 0, "red_zone_carries": 0, "goal_line_carries": 0})
        snap = snaps_by_gsis.get(gsis_id, {})

        canonical_player_id = gsis_to_canonical.get(gsis_id)
        if canonical_player_id is None:
            unresolved.append(gsis_id)

        records.append(NflUsageRecord(
            canonical_player_id=canonical_player_id, gsis_id=gsis_id,
            season=season, week=week, game_id=row.get("game_id"),
            team=team, opponent=row.get("opponent_team"), position=row.get("position"),
            offensive_snaps=snap.get("offense_snaps"), defensive_snaps=snap.get("defense_snaps"),
            special_teams_snaps=snap.get("st_snaps"), snap_share=snap.get("offense_pct"),
            targets=targets, target_share=target_share,
            receptions=receptions, reception_share=reception_share,
            carries=row.get("carries"), carry_share=carry_share,
            routes=None, route_participation=None,
            red_zone_targets=rz.get("red_zone_targets"), red_zone_carries=rz.get("red_zone_carries"),
            goal_line_carries=rz.get("goal_line_carries"),
            pass_attempts=row.get("attempts"), completions=row.get("completions"),
            passing_yards=row.get("passing_yards"), passing_tds=row.get("passing_tds"),
            rushing_yards=row.get("rushing_yards"), rushing_tds=row.get("rushing_tds"),
            receiving_yards=row.get("receiving_yards"), receiving_tds=row.get("receiving_tds"),
            source=SOURCE_WEEKLY_STATS_DERIVED,
            source_provenance=f"{SOURCE_WEEKLY_STATS_DERIVED}+{SOURCE_SNAP_COUNTS}+{SOURCE_PBP_DERIVED}",
            event_time=None, available_at=None, ingested_at=fetched_at,
        ))

    return records, unresolved
