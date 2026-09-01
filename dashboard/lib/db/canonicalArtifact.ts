// M2 -- TypeScript mirror of canonical/models.py::CanonicalSlateArtifact's
// to_dict() shape (Python), the handoff document canonical_ingestion/
// normalized_storage.py writes to the NORMALIZED R2 namespace and this
// module's promotion logic (canonicalPromotion.ts) reads back.

export type SlateValidationState = "PENDING" | "VALID" | "REJECTED";
export type SlatePlayerIdentityStatus = "RESOLVED" | "UNRESOLVED" | "REVIEW_REQUIRED";

export interface CanonicalSlateDocument {
  internalSlateId: string;
  sport: string;
  site: string;
  provider: string;
  providerSlateId: string;
  slateName: string | null;
  slateDate: string;
  firstGameStartUtc: string;
  gameCount: number | null;
  gameIds: string[];
  salaryCap: number | null;
  rosterTemplate: Record<string, number> | null;
  sourceProvenance: string;
  validationState: SlateValidationState;
  validationFindings: string[];
  fetchedAt: string | null;
}

export interface CanonicalSlatePlayerDocument {
  internalSlateId: string;
  internalPlayerId: string | null;
  providerPlayerId: string;
  providerDraftableIds: string[];
  name: string;
  team: string;
  opponent: string | null;
  gameId: string | null;
  salary: number;
  positionEligibility: string[];
  rosterSlotEligibility: string[];
  identityStatus: SlatePlayerIdentityStatus;
}

export interface IdentityMatchDocument {
  identityStatus: SlatePlayerIdentityStatus;
  matchMethod: string | null;
  matchConfidence: number | null;
  externalIdHints: Array<{ provider: string; externalId: string; externalIdType: string }>;
  candidateMlbPlayerIds: string[];
  reason: string | null;
}

export interface CanonicalSlateArtifactDocument {
  schemaVersion: string;
  rawHash: string | null;
  normalizedHash: string | null;
  slate: CanonicalSlateDocument;
  players: CanonicalSlatePlayerDocument[];
  identityMatches: Record<string, IdentityMatchDocument>;
  isSemanticDuplicate?: boolean;
  duplicateOfKey?: string | null;
}

/** This module's only known-readable schema version -- mirrors
 * canonical/schema_version.py::KNOWN_SLATE_SCHEMA_VERSIONS. An artifact
 * tagged with anything else is refused, never guessed at. */
export const KNOWN_SLATE_SCHEMA_VERSIONS = new Set(["slate_normalized_v1"]);
