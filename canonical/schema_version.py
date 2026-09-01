"""M1L -- the single authoritative schemaVersion constant for the
canonical NORMALIZED slate artifact shape (CanonicalSlateArtifact, see
canonical/models.py).

Same versioning philosophy as historical_nfl's SCHEMA_VERSION pattern
(nfl-dfs-engine/historical_nfl/raw_contract.py, read-only reference --
NOT imported, since this package must not create a dependency on the
separate NFL repository): a plain, hand-bumped string, bumped only on a
real breaking shape change, never silently reinterpreted. An artifact
tagged with an older schemaVersion must be read by the parsing code
path that matches ITS version, never assumed to match the newest one.
"""

SLATE_NORMALIZED_V1 = "slate_normalized_v1"

# The version newly normalized artifacts are stamped with today. Update
# this alias (and add a new SLATE_NORMALIZED_VN constant above, leaving
# the old one in place) when a future milestone introduces a breaking
# shape change -- never repoint an existing version string at new field
# semantics.
CURRENT_SLATE_SCHEMA_VERSION = SLATE_NORMALIZED_V1

KNOWN_SLATE_SCHEMA_VERSIONS = frozenset({SLATE_NORMALIZED_V1})


def is_known_schema_version(version: str) -> bool:
    """True if this package has a parsing path for `version`. Callers
    encountering an unknown version must treat the artifact as
    unreadable-by-this-code (and say so explicitly), never guess at its
    shape by assuming it matches CURRENT_SLATE_SCHEMA_VERSION."""
    return version in KNOWN_SLATE_SCHEMA_VERSIONS
