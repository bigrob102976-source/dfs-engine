"""M1J / M1K -- rawHash and normalizedHash.

rawHash: SHA-256 of the EXACT bytes a provider returned, for dedup and
audit ("prove exactly what DraftKings returned at time T"). The M0
audit found the one existing hash concept in this codebase
(DKSalaryRow.source_sha256) is real for CSV imports but confirmed NULL
for 100% of live DraftKings-Unofficial-sourced rows in production --
this closes that gap at the foundation layer. M1 does NOT wire this
into the live capture path (see canonical/__init__.py).

normalizedHash: SHA-256 of a deterministic, field-ordered serialization
of the DFS-relevant NORMALIZED content only -- the signal a future
milestone can use to decide whether downstream research/projections
need to re-run, without caring about serialization/fetch-time noise.
"""

import hashlib
import json
from typing import Any, Dict, Iterable, List


def compute_raw_hash(raw_bytes: bytes) -> str:
    """SHA-256 of the exact provider response bytes, lowercase hex.
    Deliberately takes `bytes`, not a parsed object or string that would
    require re-encoding -- re-serializing before hashing would hash this
    codebase's interpretation of the payload, not the payload DraftKings
    (or a future provider) actually sent."""
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise TypeError(f"compute_raw_hash requires raw bytes, got {type(raw_bytes).__name__}")
    return hashlib.sha256(raw_bytes).hexdigest()


# Fields intentionally excluded from the normalizedHash payload -- these
# change on every fetch merely because time passed, or are themselves
# hash outputs, and must never cause an unchanged slate to appear to
# have "new" DFS-relevant content.
_VOLATILE_SLATE_FIELDS = frozenset({
    "fetchedAt", "rawHash", "normalizedHash", "retrievedAt", "validationFindings",
    "validationState", "internalSlateId", "createdAt", "updatedAt",
})

_VOLATILE_PLAYER_FIELDS = frozenset({
    "internalPlayerId", "internalSlateId", "identityStatus", "createdAt", "updatedAt",
})


def _strip_volatile(payload: Dict[str, Any], volatile_keys: Iterable[str]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if k not in volatile_keys}


def _canonicalize(value: Any) -> Any:
    """Recursively normalizes a JSON-able structure so that semantically
    equivalent content always serializes identically regardless of
    input key/list order: dict keys are sorted (json.dumps(sort_keys=True)
    handles this at dump time), and lists of primitives are sorted so
    that e.g. positionEligibility=["OF","1B"] and ["1B","OF"] hash the
    same. Lists of dicts are handled by the caller (player ordering is
    normalized explicitly in build_normalized_hash_payload, keyed on a
    stable identifier, since dicts aren't orderable)."""
    if isinstance(value, dict):
        return {k: _canonicalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [_canonicalize(v) for v in value]
        if items and all(isinstance(v, (str, int, float, bool)) or v is None for v in items):
            try:
                return sorted(items, key=lambda v: (str(type(v)), v))
            except TypeError:
                return items
        return items
    return value


def build_normalized_hash_payload(slate: Dict[str, Any], players: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds the exact structure normalizedHash is computed over, from
    plain dict representations of a CanonicalSlate and its
    CanonicalSlatePlayer rows (e.g. via dataclasses.asdict). Player
    ordering is normalized by sorting on providerPlayerId so that
    identical rosters supplied in different input order always produce
    the same payload."""
    slate_content = _strip_volatile(dict(slate), _VOLATILE_SLATE_FIELDS)
    player_contents = [_strip_volatile(dict(p), _VOLATILE_PLAYER_FIELDS) for p in players]
    player_contents.sort(key=lambda p: str(p.get("providerPlayerId", "")))
    return {
        "slate": _canonicalize(slate_content),
        "players": [_canonicalize(p) for p in player_contents],
    }


def compute_normalized_hash(slate: Dict[str, Any], players: List[Dict[str, Any]]) -> str:
    """SHA-256 of the deterministic normalized-content payload. Two
    calls with the same DFS-relevant content -- regardless of dict key
    order, list order, or player order in the input -- produce the same
    hash; any real change to salary, eligibility, team, game membership,
    roster template, salary cap, provider IDs, or draftable IDs produces
    a different hash."""
    payload = build_normalized_hash_payload(slate, players)
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
