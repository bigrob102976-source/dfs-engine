"""Milestone 31.2 -- backs the admin DraftKings Development Data
Explorer (dashboard/app/admin/draftkings-unofficial). Prints a single
JSON line. Unlike scripts/audit_draftkings_unofficial.py (a human-
readable multi-section report for a terminal), this is a machine-
readable summary the dashboard's API route parses.

    python scripts/dk_unofficial_explorer.py --sport MLB
    python scripts/dk_unofficial_explorer.py --sport MLB --draft-group-id 152389 --game-type-id 2

Every live call this script makes is explicit and admin-triggered
(the dashboard only calls this when an admin opens/refreshes the
explorer page) -- never on a schedule, never for every member page
load. Gated by DK_UNOFFICIAL_ENABLED like the provider itself, so the
explorer can't be used to route around the same opt-in gate."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dfs.providers.draftkings_unofficial_provider import is_enabled  # noqa: E402
from draftkings_unofficial import collector, identity, quality  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Data source for the admin DraftKings Development Data Explorer.")
    parser.add_argument("--sport", required=True)
    parser.add_argument("--draft-group-id", type=int, default=None)
    parser.add_argument("--game-type-id", type=int, default=None)
    args = parser.parse_args()

    if not is_enabled():
        print(json.dumps({"status": "not_enabled", "detail": "Set DK_UNOFFICIAL_ENABLED=true to use the DraftKings Development Data Explorer."}))
        return

    sports_result = collector.collect_sports()
    sports = [s.to_dict() for s in sports_result.sports]

    universe = collector.collect_sport_universe(args.sport.upper())
    if universe.status == collector.STATUS_NO_ACTIVE_SLATE:
        print(json.dumps({"status": "no_active_slate", "sport": args.sport.upper(), "sports": sports}))
        return
    if universe.status != collector.STATUS_OK:
        print(json.dumps({"status": universe.status, "sport": args.sport.upper(), "error": universe.error, "sports": sports}))
        return

    slates = [s.to_dict() for s in universe.slates]
    contests = [c.to_dict() for c in universe.contests]

    result = {
        "status": "ok", "sport": args.sport.upper(), "sports": sports,
        "slates": slates, "contests": contests, "game_types": [g.to_dict() for g in universe.game_types],
    }

    if args.draft_group_id is not None:
        detail = collector.collect_slate_detail(args.draft_group_id, args.sport.upper(), game_type_id=args.game_type_id)
        if detail.status != collector.STATUS_OK:
            result["slate_detail"] = {"status": detail.status, "error": detail.error, "schema_check": detail.schema_check}
        else:
            id_summary = identity.identity_match_summary(detail.identity_matches)
            q = quality.build_quality_report(
                len(sports), universe.contests, [s for s in universe.slates if s.draft_group_id == args.draft_group_id],
                detail.draftables, detail.identity_matches,
            )
            result["slate_detail"] = {
                "status": "ok", "games": [g.to_dict() for g in detail.games],
                "draftables": [d.to_dict() for d in detail.draftables],
                "roster_rules": detail.roster_rules.to_dict() if detail.roster_rules else None,
                "identity_match_summary": id_summary, "quality": q, "skipped": detail.skipped,
            }

    print(json.dumps(result))


if __name__ == "__main__":
    main()
