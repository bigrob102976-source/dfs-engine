"""Milestone 31.2C -- read-only discovery of which nearby calendar dates
the DraftKings unofficial development provider currently has usable
Classic/SalaryCap DraftGroups for, so the dashboard never has to guess
whether "today" (America/Chicago) is the right date to browse, or which
DraftGroup on a given date is the best default pick.

Deliberately DOES NOT call collect_slate_detail() (which fetches full
draftables) for every candidate -- it makes exactly the one
collect_sport_universe() call the provider's own get_slate() already
makes internally, and buckets/ranks the resulting lightweight DkSlate
list. No new DraftKings endpoints are touched beyond what M31.2 already
uses; no extra network calls are added per candidate date.

Milestone M1: DraftKings Unofficial is the permanent DEFAULT provider,
so this does real work whenever dfs/providers/config.py's own cascade
would resolve to it -- mirrored here rather than imported to avoid a
real network probe just to answer "is it active": no explicit
DFS_SALARY_PROVIDER override naming a DIFFERENT provider, Mock Mode not
explicitly enabled (it wins before DraftKings Unofficial is even
attempted, same as the real cascade), and its own DK_UNOFFICIAL_ENABLED
kill switch not set to an explicit "off" value. For any other provider
configuration this prints status "not_applicable" immediately, with
zero network calls: this script has no meaning for CSV/mock providers,
which have no comparable "available dates" concept.

Always prints exactly one line of JSON to stdout and exits 0, even on
provider failure -- callers branch on the "status" field, matching
scripts/list_dfs_slates.py's convention.

Usage:
    python scripts/discover_dk_slate_dates.py --sport MLB
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.runtime_settings import is_mock_mode_enabled
from dfs.providers.draftkings_unofficial_provider import is_enabled as dk_unofficial_enabled
from draftkings_unofficial import collector
from draftkings_unofficial.models import DkSlate

# Contest/DraftGroup formats that are never a "Classic" SalaryCap
# candidate even when their draft_type happens to be "SalaryCap" (DK's
# Showdown/Captain Mode format is salary-capped too, but is a
# fundamentally different single-game CPT/UTIL roster, not this
# discovery's concern -- see M31.2B's "avoid Showdown/Tiers/Snake"
# instruction).
_EXCLUDE_KEYWORDS = ("showdown", "captain", "single game", "tiers", "snake", "arcade")


def _is_dk_unofficial_active() -> bool:
    """Mirrors dfs/providers/config.py::get_configured_provider()'s own
    cascade decision (Milestone M1) without making a network call:
    DraftKings Unofficial is active unless an explicit
    DFS_SALARY_PROVIDER override names a different provider, Mock Mode
    is explicitly enabled (checked first, same as the real cascade), or
    its own DK_UNOFFICIAL_ENABLED kill switch is off."""
    provider_name = (os.environ.get("DFS_SALARY_PROVIDER") or "").strip().lower()
    if provider_name and provider_name != "draftkings_unofficial":
        return False
    if is_mock_mode_enabled():
        return False
    return dk_unofficial_enabled()


def _classic_candidate(slate: DkSlate, salary_cap_game_type_ids: set) -> bool:
    if slate.game_type_id not in salary_cap_game_type_ids:
        return False
    if not (slate.game_count or 0) > 0:
        return False
    text = f"{slate.tag or ''} {slate.label or ''} {slate.game_type_name or ''}".lower()
    return not any(k in text for k in _EXCLUDE_KEYWORDS)


def _rank(slate: DkSlate) -> tuple:
    """Lower sorts first. Preference order (matches the M31.2B live
    validation's manual selection): Featured/Main Classic > Night
    Classic > Late Night Classic > Turbo Classic; within the same tier,
    prefer more games."""
    text = f"{slate.tag or ''} {slate.label or ''}".lower()
    if "featured" in text:
        tier = 0
    elif "late" in text and "night" in text:
        tier = 3
    elif "turbo" in text:
        tier = 4
    elif "night" in text:
        tier = 2
    else:
        tier = 1  # untagged/bare "Main Classic", or any other classic variant
    return (tier, -(slate.game_count or 0))


def _date_entry(date: str, slates: List[DkSlate], salary_cap_game_type_ids: set) -> dict:
    candidates = sorted((s for s in slates if _classic_candidate(s, salary_cap_game_type_ids)), key=_rank)
    best = candidates[0] if candidates else None
    return {
        "date": date,
        "slate_count": len(slates),
        "salary_cap_slate_count": len(candidates),
        "has_usable_slate": best is not None,
        "best_slate_id": f"dkunofficial-{best.draft_group_id}" if best else None,
        "best_slate_label": (best.tag or best.label or best.game_type_name) if best else None,
        "best_game_count": best.game_count if best else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover which nearby dates the DK unofficial provider has usable Classic slates for (read-only).")
    parser.add_argument("--sport", default="MLB")
    args = parser.parse_args()

    if not _is_dk_unofficial_active():
        print(json.dumps({"status": "not_applicable", "provider_name": None, "reason": "DK unofficial provider is not the active provider.", "dates": []}))
        return

    universe = collector.collect_sport_universe(args.sport.upper())
    if universe.status == collector.STATUS_NO_ACTIVE_SLATE:
        print(json.dumps({"status": "no_active_slate", "provider_name": "draftkings_unofficial", "reason": f"No active slate for sport={args.sport!r}.", "dates": []}))
        return
    if universe.status != collector.STATUS_OK:
        print(json.dumps({
            "status": "unavailable", "provider_name": "draftkings_unofficial",
            "reason": f"DraftKings unofficial contest discovery failed: {universe.status} ({universe.error}).", "dates": [],
        }))
        return

    salary_cap_game_type_ids = {gt.game_type_id for gt in universe.game_types if gt.draft_type == "SalaryCap"}

    by_date: Dict[str, List[DkSlate]] = {}
    for slate in universe.slates:
        local_date: Optional[str] = collector.slate_local_date(slate)
        if not local_date:
            continue
        by_date.setdefault(local_date, []).append(slate)

    dates = [_date_entry(d, slates, salary_cap_game_type_ids) for d, slates in sorted(by_date.items())]
    print(json.dumps({"status": "ok", "provider_name": "draftkings_unofficial", "reason": None, "dates": dates}))


if __name__ == "__main__":
    main()
