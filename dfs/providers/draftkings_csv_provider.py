"""Real DraftKings salary provider (Milestone 19): builds a
ProviderSlateResult from official DraftKings salary-export CSVs the
user has uploaded for today (dfs/providers/draftkings_csv_storage.py) --
NOT a live network call. dfs/providers/base.py's module docstring
forbids scraping DraftKings HTML, automating a DraftKings login, or
depending on undocumented/private DraftKings endpoints; the official,
documented way a third-party tool gets real DK salary data is the same
CSV export DraftKings gives every contest entrant, which the user
downloads themselves and uploads here.

Each upload is tagged with a slate label (Main/Turbo/Night/Late/
Afternoon/Showdown/...) at upload time -- DraftKings' own CSV export has
no field that names the slate -- so a single date can expose several
real DK slates at once, exactly like DraftKings' own lobby does. Only
the newest upload per label is used (immutable-snapshot "newest wins",
same rule every other artifact type in this project follows).

Reuses dfs/draftkings_parser.py::parse_salary_csv verbatim -- the exact
same real-CSV-format validation/parsing the pre-existing manual
scripts/build_dk_player_pool.py path has always used. A single
malformed/empty upload is skipped with a warning rather than failing
every other upload for the date.
"""

from typing import Dict, List, Optional

from dfs.draftkings_parser import DraftKingsCSVFormatError, parse_salary_csv
from dfs.providers.base import DFSSalaryProvider, ProviderNoSlateError, ProviderUnavailableError
from dfs.providers.draftkings_csv_storage import DEFAULT_DFS_INPUT_ROOT, DraftKingsUpload, list_uploads
from dfs.providers.models import ProviderPlayer, ProviderSlateInfo, ProviderSlateResult
from dfs.providers.source_provenance import classify_source_provenance
from dfs.providers.source_realism import check_source_realism
from dfs.slate_validation import resolve_game_ids


def _opponent_from_game_info(team: str, game_info: str) -> Optional[str]:
    """DraftKings' real "Game Info" column starts "AWAY@HOME ..." --
    derives the opponent for `team` from that real pairing. Never
    guessed: returns None if `team` doesn't match either side."""
    if not game_info or "@" not in game_info:
        return None
    pair = game_info.split(" ", 1)[0]
    if "@" not in pair:
        return None
    away, home = pair.split("@", 1)
    if team == away:
        return home
    if team == home:
        return away
    return None


def _latest_per_label(uploads: List[DraftKingsUpload]) -> List[DraftKingsUpload]:
    latest: Dict[str, DraftKingsUpload] = {}
    for u in uploads:
        existing = latest.get(u.slate_label)
        if existing is None or u.uploaded_at > existing.uploaded_at:
            latest[u.slate_label] = u
    return list(latest.values())


class DraftKingsCsvProvider(DFSSalaryProvider):
    name = "draftkings_csv"
    requires_api_key = False

    def __init__(self, dfs_input_root: str = str(DEFAULT_DFS_INPUT_ROOT)):
        self.dfs_input_root = dfs_input_root

    def get_slate(
        self, date: str, sport: str = "MLB", site: str = "draftkings", research_games: Optional[List[dict]] = None
    ) -> ProviderSlateResult:
        if sport.upper() != "MLB":
            raise ProviderNoSlateError(f"DraftKingsCsvProvider only supports MLB, got sport={sport!r}.")

        uploads = _latest_per_label(list_uploads(date, output_root=self.dfs_input_root))
        if not uploads:
            raise ProviderUnavailableError(
                f"No DraftKings salary CSV has been uploaded for {date} yet. "
                f"Download today's export from draftkings.com and upload it."
            )

        slates: List[ProviderSlateInfo] = []
        players_by_slate: Dict[str, List[ProviderPlayer]] = {}
        warnings: List[str] = []
        retrieved_at_latest = max(u.uploaded_at for u in uploads)

        for upload in sorted(uploads, key=lambda u: u.slate_label):
            try:
                dk_rows = parse_salary_csv(upload.path)
            except (DraftKingsCSVFormatError, FileNotFoundError) as e:
                warnings.append(f"Skipped upload {upload.original_filename!r} ({upload.slate_label}): {e}")
                continue
            if not dk_rows:
                warnings.append(f"Upload {upload.original_filename!r} ({upload.slate_label}) has zero players.")
                continue

            slate_id = f"dkcsv-{upload.slate_label.lower().replace(' ', '-')}-{date}"
            games = {row.game_info for row in dk_rows if row.game_info}
            game_ids = resolve_game_ids(list(games), research_games) if research_games else []

            realism = check_source_realism(dk_rows, game_count=len(games))
            provenance = classify_source_provenance(upload.source_provenance, realism)
            if realism.blocked:
                warnings.append(
                    f"Upload {upload.original_filename!r} ({upload.slate_label}) failed source realism checks "
                    f"and has been reclassified {provenance} -- see realism_findings for this slate."
                )
            for finding in realism.findings:
                warnings.append(f"[{upload.slate_label}] [{finding.level}] {finding.message}")

            slates.append(ProviderSlateInfo(
                slate_id=slate_id, slate_name=upload.slate_label, site=site, sport=sport,
                start_time=None, game_count=len(games), game_ids=game_ids, player_count=len(dk_rows),
                source_provenance=provenance, realism_blocked=realism.blocked,
                realism_findings=[f.message for f in realism.findings],
            ))
            players_by_slate[slate_id] = [
                ProviderPlayer(
                    external_player_id=row.dk_player_id, name=row.name, team=row.team_abbrev,
                    opponent=_opponent_from_game_info(row.team_abbrev, row.game_info), game=row.game_info or None,
                    salary=row.salary, position_eligibility=row.dk_positions, slate_id=slate_id,
                    slate_name=upload.slate_label, start_time=None, source=self.name,
                    retrieved_at=upload.uploaded_at,
                )
                for row in dk_rows
            ]

        if not slates:
            raise ProviderUnavailableError(
                f"{len(uploads)} DraftKings CSV upload(s) found for {date}, but none could be parsed. "
                + " ".join(warnings)
            )

        return ProviderSlateResult(
            slates=slates, players_by_slate=players_by_slate, source=self.name,
            retrieved_at=retrieved_at_latest, warnings=warnings,
        )
