"""Research Engine: orchestrates Collect -> Normalize -> Validate -> Save
-> Report for one slate date.

This is the single entry point future agents (and today, the CLI) call to
get a research package. It performs no DFS analysis of its own — it only
gathers, organizes, and validates baseball information.
"""

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from research import collector, normalizer, storage, validator
from research.models import ResearchMetadata, ResearchReport, SlateIndex

VERSION = "0.1.0"

# Research-package categories from the milestone spec that don't yet have
# a dedicated collector/file. Listed explicitly (not omitted) so a reader
# of slate.json knows the gap is a known, tracked limitation rather than
# an oversight.
UNCOLLECTED_CATEGORY_NOTES = [
    "bullpens: not yet collected (no bullpen-usage collector built yet)",
    "statcast_metadata: not yet collected (Baseball Savant/Statcast integration is a future milestone)",
    "schedules: represented via games.json for this slate; a season-level schedule collector doesn't exist yet",
    "player_metadata: partially represented (pitcher throwing hand only) via pitchers.json; full bios not yet collected",
]


def _build_slate_index(slate_date: str, games, teams, pitchers, batters, files) -> SlateIndex:
    return SlateIndex(
        slate_date=slate_date,
        game_ids=sorted(g.game_id for g in games),
        team_ids=sorted(t.team_id for t in teams),
        counts={
            "games": len(games),
            "teams": len(teams),
            "pitchers": len(pitchers),
            "batters": len(batters),
        },
        files={k: v for k, v in files.items() if k != "slate"},
        bullpens=[],
        statcast_metadata=[],
        notes=list(UNCOLLECTED_CATEGORY_NOTES),
    )


def build_research_package(date: str, output_root: str = "research_output") -> ResearchReport:
    start = time.time()

    raw = collector.collect(date)
    package = normalizer.normalize(raw)
    issues = validator.validate(package.games, package.teams, package.pitchers, package.batters, date)

    warnings: List[str] = list(raw.warnings) + list(package.warnings) + [i.message for i in issues if i.level == "warning"]
    errors: List[str] = list(raw.errors) + [i.message for i in issues if i.level == "error"]

    # Write files first (without final duration/warnings baked into slate.json
    # counts — those don't depend on timing), then compute duration for metadata.
    folder = Path(output_root) / date
    placeholder_files = {
        "games": str(folder / "games.json"),
        "teams": str(folder / "teams.json"),
        "pitchers": str(folder / "pitchers.json"),
        "batters": str(folder / "batters.json"),
        "metadata": str(folder / "metadata.json"),
    }
    slate_index = _build_slate_index(date, package.games, package.teams, package.pitchers, package.batters, placeholder_files)

    # Metadata is written to disk as part of the package, so its own
    # pipeline_duration_seconds can only cover collect/normalize/validate,
    # not the save it's included in. The CLI-facing duration below covers
    # the full run, including the save.
    metadata = ResearchMetadata(
        slate_date=date,
        generated_at=datetime.now(timezone.utc).isoformat(),
        sources_used=raw.sources_used,
        version=VERSION,
        pipeline_duration_seconds=round(time.time() - start, 3),
        warnings=warnings,
        errors=errors,
    )

    files_written = storage.save_package(
        Path(output_root), date, package.games, package.teams, package.pitchers, package.batters, slate_index, metadata
    )

    duration_seconds = round(time.time() - start, 3)

    return ResearchReport(
        slate_date=date,
        games_found=len(package.games),
        teams_found=len(package.teams),
        pitchers_found=len(package.pitchers),
        batters_found=len(package.batters),
        warnings=warnings,
        errors=errors,
        files_written=files_written,
        duration_seconds=duration_seconds,
    )
