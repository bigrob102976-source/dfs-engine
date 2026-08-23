"""Orchestrates one BlueCollar projection fetch for a real DK slate:

    BlueCollarProvider.list_slates()
        -> match_dk_slate_to_bluecollar() (bluecollar/slate_matcher.py)
        -> BlueCollarProvider.get_projections()
        -> match_bluecollar_players() (bluecollar/player_matcher.py, MLB identity)
        -> zero-value handling (this module)
        -> a single BlueCollarSnapshot, ready to save (bluecollar/persistence.py)

BlueCollar remains fully OPTIONAL and never raises out of
build_bluecollar_snapshot(): every failure mode (not configured, auth
rejected, rate limited, unavailable, slate match ambiguous/missing, no
research package yet) is returned as a structured
{"status": ..., "error": ...} result instead, so a caller (the admin
slate pipeline) can always continue with Big Money Native/AI/ML
regardless of what happened here -- BlueCollar must never fail the
whole slate.

ZERO-VALUE HANDLING (live finding, 2026-08-23): BlueCollar returns many
players with a raw projection of exactly 0.0 -- observed to correlate
with "not yet projected" (same players missing a confirmed lineup slot),
not a genuine "projected for zero fantasy points" call. A raw value
<= BLUECOLLAR_MIN_USABLE_PROJECTION is therefore treated as NOT
AVAILABLE (usable_projection stays None) rather than a real projection,
so it can never make a player look like a terrible play or reach the
optimizer as a fabricated zero. raw_projection is preserved on the
record regardless, for transparency -- it is never presented to a
member as "the" projection.
"""

from datetime import datetime, timezone
from typing import Optional

from bluecollar.models import BlueCollarSnapshot
from bluecollar.player_matcher import match_bluecollar_players
from bluecollar.slate_matcher import match_dk_slate_to_bluecollar
from external_projections.base import (
    ProjectionProviderAuthenticationError,
    ProjectionProviderNotConfiguredError,
    ProjectionProviderUnavailableError,
)
from external_projections.bluecollar_provider import BlueCollarProvider
from player_identity.identity_package import build_identity_package
from player_identity.persistence import load_crosswalk
from research.adapters import batter_input as batter_adapter
from research.adapters import pitcher_input as pitcher_adapter
from research.adapters.pitcher_input import ResearchPackageNotFoundError

STATUS_NOT_CONFIGURED = "not_configured"
STATUS_READY = "ready"
STATUS_NO_RESEARCH = "no_research"
STATUS_API_ERROR = "api_error"
STATUS_SLATE_MATCH_FAILED = "slate_match_failed"

# A raw BlueCollar projection at or below this value is treated as NOT
# AVAILABLE, never a genuine zero-point projection -- see module docstring.
BLUECOLLAR_MIN_USABLE_PROJECTION = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_research_package(date: str, research_output_root: str) -> Optional[dict]:
    try:
        pitcher_pkg = pitcher_adapter.load_research_package(research_output_root, date)
    except ResearchPackageNotFoundError:
        return None
    batter_pkg = batter_adapter.load_research_package(research_output_root, date)
    return {"games": pitcher_pkg["games"], "teams": pitcher_pkg["teams"], "pitchers": pitcher_pkg["pitchers"], "batters": batter_pkg["batters"]}


def build_bluecollar_snapshot(
    dk_slate: dict, date: str, research_output_root: str = "research_output",
    provider: Optional[BlueCollarProvider] = None, identity_crosswalk_path: Optional[str] = None,
) -> dict:
    """`dk_slate` is one entry from a real provider_slate_<ts>.json's
    `slates` list. Returns {"status": str, "snapshot": BlueCollarSnapshot | None, "error": str | None}.

    `identity_crosswalk_path` (Canonical MLB Player Identity Foundation):
    optional override for the roster-derived crosswalk file (see
    dfs/pool_builder.py::build_pool's identical parameter) -- widens
    which BlueCollar-reported players can resolve an mlb_player_id
    (identity resolution only; never changes a projection value -- see
    this module's own zero-value handling below, which is untouched)."""
    provider = provider if provider is not None else BlueCollarProvider()
    dk_slate_id = dk_slate.get("slate_id") or dk_slate.get("slateId") or ""

    if not provider.is_configured():
        return {"status": STATUS_NOT_CONFIGURED, "snapshot": None, "error": None}

    try:
        bluecollar_slates = provider.list_slates(date)
    except ProjectionProviderNotConfiguredError:
        return {"status": STATUS_NOT_CONFIGURED, "snapshot": None, "error": None}
    except (ProjectionProviderAuthenticationError, ProjectionProviderUnavailableError) as exc:
        return {"status": STATUS_API_ERROR, "snapshot": None, "error": str(exc)}

    slate_match = match_dk_slate_to_bluecollar(dk_slate, bluecollar_slates)
    if slate_match.status != "matched":
        return {
            "status": STATUS_SLATE_MATCH_FAILED, "snapshot": None,
            "error": f"BLUECOLLAR_SLATE_MATCH_{slate_match.status.upper()}: {slate_match.reason}",
        }

    package = _load_research_package(date, research_output_root)
    if package is None:
        return {"status": STATUS_NO_RESEARCH, "snapshot": None, "error": f"No research package found for {date} under {research_output_root}/."}

    try:
        raw_players = provider.get_projections(slate_match.bluecollar_slate_id)
    except (ProjectionProviderAuthenticationError, ProjectionProviderUnavailableError) as exc:
        return {"status": STATUS_API_ERROR, "snapshot": None, "error": str(exc)}

    # Canonical MLB Player Identity Foundation: widen identity matching
    # with the roster-derived crosswalk, same as dfs/pool_builder.py.
    # This is IDENTITY resolution only -- the zero-value/usable_projection
    # handling below is completely untouched by it.
    identity_crosswalk = load_crosswalk(identity_crosswalk_path) if identity_crosswalk_path else load_crosswalk()
    identity_package = build_identity_package(package, identity_crosswalk)
    matched_players = match_bluecollar_players(raw_players, identity_package)

    bluecollar_updated = raw_players[0].updated_at if raw_players else None
    for p in matched_players:
        if p.raw_projection is not None and p.raw_projection > BLUECOLLAR_MIN_USABLE_PROJECTION:
            p.usable_projection = p.raw_projection
        # else: stays None -- NOT AVAILABLE, never a fabricated zero.

    snapshot = BlueCollarSnapshot(
        slate_date=date,
        dk_slate_id=dk_slate_id,
        bluecollar_slate_id=slate_match.bluecollar_slate_id,
        bluecollar_slate_name=slate_match.bluecollar_slate_name,
        bluecollar_updated=bluecollar_updated,
        retrieved_at=_now_iso(),
        slate_match_status=slate_match.status,
        slate_match_reason=slate_match.reason,
        player_count=len(matched_players),
        matched_count=sum(1 for p in matched_players if p.match_status == "matched"),
        usable_projection_count=sum(1 for p in matched_players if p.usable_projection is not None),
        players=matched_players,
    )
    return {"status": STATUS_READY, "snapshot": snapshot, "error": None}
