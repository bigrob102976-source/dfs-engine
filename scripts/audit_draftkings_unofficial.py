"""Milestone 31.2 -- live audit of the unofficial DraftKings provider.

Makes a SMALL, bounded number of live requests (never one per slate
across every sport) and prints a comprehensive human-readable report.
Normal unit tests never call live endpoints -- this script is the one
explicit place that does.

    python scripts/audit_draftkings_unofficial.py --sport MLB
    python scripts/audit_draftkings_unofficial.py --all-sports
    python scripts/audit_draftkings_unofficial.py --sport MLB --compare-csv PATH_TO_DK_CSV

For --sport, this collects the FULL detail (games/draftables/rules) for
every distinct game type found (Classic, Showdown, ...) so Captain/
Showdown handling gets exercised, not just Classic. For --all-sports,
each active sport gets exactly ONE representative slate's full detail
(the slate with the most games) to keep total live calls bounded --
per-sport summary counts (contests/draft groups) come from the single
contest-discovery call already made for that sport, not an extra call.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.draftkings_parser import DraftKingsCSVFormatError, parse_salary_csv  # noqa: E402
from dfs.pool_builder import ensure_research_package  # noqa: E402
from draftkings_unofficial import collector, comparison, identity, quality  # noqa: E402
from draftkings_unofficial.models import DkContest, DkDraftable, DkSlate  # noqa: E402


def _print_section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _collect_one_sport(sport_code: str, full_detail: bool = True):
    """Returns (universe, slate_details: {draft_group_id: SlateDetailResult}, research_package_or_None)."""
    universe = collector.collect_sport_universe(sport_code)
    print(f"\n{sport_code}: {universe.status} -- contests={len(universe.contests)} draft_groups={len(universe.slates)} game_types={len(universe.game_types)}")
    if universe.status != collector.STATUS_OK:
        return universe, {}, None

    research_package = None
    if sport_code == "MLB":
        # Best-effort only: identity matching is a bonus for this audit,
        # not a requirement -- reuses whatever research package already
        # exists on disk for today's most-recently-built date rather than
        # triggering an expensive rebuild (ensure_research_package would
        # do a live MLB Stats API fetch, which this audit's "small number
        # of DraftKings requests" scope doesn't cover).
        research_dates = sorted((d.name for d in Path("research_output").glob("*") if d.is_dir()), reverse=True)
        if research_dates:
            try:
                research_package = ensure_research_package(research_dates[0], "research_output")
            except Exception:  # noqa: BLE001
                research_package = None

    if not full_detail:
        # One representative slate: prefer a real salary-cap format
        # (Classic-equivalent) over a Tiers/Snake/"Sit & Go"/pick'em
        # format -- confirmed live that DraftKings' own game-type
        # metadata (draftType) distinguishes these, and a salary-less
        # format has NO `salary` field on its draftables at all (every
        # record is correctly skipped by the normalizer's required-field
        # check, per this milestone's "never invent a field" rule --
        # NOT a bug, but picking one as "the representative slate" would
        # make a perfectly healthy sport look like it has zero salary
        # coverage). Among salary-cap-format slates, the one with the
        # most games is still the tiebreaker.
        salary_cap_game_type_ids = {gt.game_type_id for gt in universe.game_types if gt.draft_type == "SalaryCap"}
        candidates = [s for s in universe.slates if s.game_type_id in salary_cap_game_type_ids] or universe.slates
        chosen = max(candidates, key=lambda s: (s.game_count or 0)) if candidates else None
        details = {}
        if chosen is not None:
            details[chosen.draft_group_id] = collector.collect_slate_detail(chosen.draft_group_id, sport_code, game_type_id=chosen.game_type_id, research_package=research_package)
        return universe, details, research_package

    # Full detail: one slate PER distinct game type present, so
    # Classic/Showdown/Captain handling all get exercised.
    seen_game_types = set()
    details = {}
    for slate in sorted(universe.slates, key=lambda s: -(s.game_count or 0)):
        if slate.game_type_id in seen_game_types:
            continue
        seen_game_types.add(slate.game_type_id)
        details[slate.draft_group_id] = collector.collect_slate_detail(slate.draft_group_id, sport_code, game_type_id=slate.game_type_id, research_package=research_package)
    return universe, details, research_package


def _sport_table_row(sport_code: str, universe, details) -> dict:
    active = universe.status == collector.STATUS_OK
    total_draftables = sum(len(d.draftables) for d in details.values())
    with_salary = sum(1 for d in details.values() for dr in d.draftables if dr.salary)
    salary_cov = round(100.0 * with_salary / total_draftables, 1) if total_draftables else None
    status = "OK" if active else universe.status.upper()
    if universe.status == collector.STATUS_NO_ACTIVE_SLATE:
        status = "NO ACTIVE SLATE"
    return {
        "sport": sport_code, "active": active, "slates": len(universe.slates) if active else 0,
        "games": sum(len(d.games) for d in details.values()),
        "draftables": total_draftables, "salary_coverage": salary_cov, "status": status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Live audit of the unofficial DraftKings provider.")
    parser.add_argument("--sport", default=None, help="e.g. MLB, NFL, NBA")
    parser.add_argument("--all-sports", action="store_true")
    parser.add_argument("--compare-csv", default=None, help="Path to a real DK salary CSV to compare against the matching MLB DraftGroup.")
    args = parser.parse_args()

    if not args.sport and not args.all_sports:
        parser.error("Specify --sport SPORT or --all-sports.")

    _print_section("SPORTS DISCOVERY")
    sports_result = collector.collect_sports()
    print(f"Status: {sports_result.status}")
    print(f"Sports discovered: {len(sports_result.sports)}")
    for s in sports_result.sports:
        print(f"  {s.sport_id:>3} {s.code:<8} {s.full_name:<28} hasPublicContests={s.has_public_contests} isEnabled={s.is_enabled}")

    all_contests: List[DkContest] = []
    all_slates: List[DkSlate] = []
    all_draftables: List[DkDraftable] = []
    all_identity_matches = []
    sport_rows = []

    if args.sport:
        _print_section(f"SPORT DETAIL -- {args.sport.upper()}")
        universe, details, _ = _collect_one_sport(args.sport.upper(), full_detail=True)
        all_contests.extend(universe.contests)
        all_slates.extend(universe.slates)
        for dg_id, detail in details.items():
            if detail.status != collector.STATUS_OK:
                print(f"  DraftGroup {dg_id}: {detail.status} ({detail.error})")
                continue
            all_draftables.extend(detail.draftables)
            all_identity_matches.extend(detail.identity_matches)
            print(f"\n  DraftGroup {dg_id}: games={len(detail.games)} draftables={len(detail.draftables)} skipped={len(detail.skipped)}")
            if detail.roster_rules:
                r = detail.roster_rules
                print(f"    Game type: {r.name} | salary_cap={r.salary_cap} | roster_slots={[s.name for s in r.roster_slots]}")
                multipliers = {s.name: s.scoring_multiplier for s in r.roster_slots if s.scoring_multiplier}
                if multipliers:
                    print(f"    Scoring multipliers found: {multipliers}")
            id_summary = identity.identity_match_summary(detail.identity_matches) if detail.identity_matches else None
            if id_summary:
                print(f"    Identity match: {id_summary}")
        sport_rows.append(_sport_table_row(args.sport.upper(), universe, details))

        if args.compare_csv:
            _print_section("DK CSV vs API COMPARISON")
            try:
                csv_rows = parse_salary_csv(args.compare_csv)
            except (DraftKingsCSVFormatError, FileNotFoundError) as e:
                print(f"Could not parse comparison CSV: {e}")
            else:
                # A real DraftKings salary CSV upload is always a Classic
                # (10-man roster) export for ONE specific set of games --
                # DraftKings' live lobby exposes MANY same-day Classic
                # DraftGroups at once (Featured/Turbo/Early/Night/Late
                # Night, spanning anywhere from 2 to the full day's worth
                # of games -- confirmed live: 10 distinct Classic
                # DraftGroups for MLB on one day during this milestone's
                # audit). Comparing against the wrong one -- or against a
                # non-Classic format (Showdown/Tiers/Snake) entirely --
                # produces a misleading result. The CSV's own distinct
                # Game Info count is the best available signal for which
                # Classic DraftGroup it actually came from (closest
                # game_count match), NOT row count (a DraftGroup's live
                # roster grows/shrinks between CSV capture and this audit
                # from adds/scratches).
                classic_slates = [s for s in universe.slates if s.game_type_id == 2]
                if not classic_slates:
                    print("No Classic DraftGroup discovered for this sport -- cannot compare a Classic CSV.")
                else:
                    csv_game_count = len({row.game_info for row in csv_rows if row.game_info})
                    best_slate = min(classic_slates, key=lambda s: abs((s.game_count or 0) - csv_game_count))
                    print(f"Comparing against DraftGroup {best_slate.draft_group_id} "
                          f"({best_slate.tag or ''}{best_slate.label or ''}, {best_slate.game_count} games -- "
                          f"CSV covers {csv_game_count} distinct games).")
                    if best_slate.draft_group_id in details and details[best_slate.draft_group_id].status == collector.STATUS_OK:
                        best = details[best_slate.draft_group_id]
                    else:
                        best = collector.collect_slate_detail(best_slate.draft_group_id, args.sport.upper(), game_type_id=2)
                    if best.status != collector.STATUS_OK:
                        print(f"Could not collect DraftGroup {best_slate.draft_group_id}: {best.status} ({best.error})")
                    else:
                        result = comparison.compare_csv_to_api(csv_rows, best.draftables)
                        print(json.dumps(result.to_dict(), indent=2)[:4000])

    if args.all_sports:
        _print_section("ALL ACTIVE SPORTS")
        for s in sports_result.sports:
            if not s.has_public_contests:
                print(f"\n{s.code}: NO ACTIVE SLATE (hasPublicContests=False)")
                sport_rows.append({"sport": s.code, "active": False, "slates": 0, "games": 0, "draftables": 0, "salary_coverage": None, "status": "NO ACTIVE SLATE"})
                continue
            universe, details, _ = _collect_one_sport(s.code, full_detail=False)
            for dg_id, detail in details.items():
                if detail.status == collector.STATUS_OK:
                    all_draftables.extend(detail.draftables)
            all_contests.extend(universe.contests)
            all_slates.extend(universe.slates)
            sport_rows.append(_sport_table_row(s.code, universe, details))

    _print_section("DATA QUALITY REPORT")
    q = quality.build_quality_report(len(sports_result.sports), all_contests, all_slates, all_draftables, all_identity_matches)
    print(json.dumps(q, indent=2))

    _print_section("SPORT TABLE")
    print(f"{'SPORT':<8}{'ACTIVE':<8}{'SLATES':<8}{'GAMES':<8}{'DRAFTABLES':<12}{'SALARY_COV':<12}{'STATUS':<20}")
    for row in sport_rows:
        cov = f"{row['salary_coverage']}%" if row["salary_coverage"] is not None else "--"
        print(f"{row['sport']:<8}{str(row['active']):<8}{row['slates']:<8}{row['games']:<8}{row['draftables']:<12}{cov:<12}{row['status']:<20}")

    print(json.dumps({"status": "ready", "sports_discovered": len(sports_result.sports), "sport_rows": sport_rows, "quality": q}))


if __name__ == "__main__":
    main()
