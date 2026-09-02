// Row shapes for lib/db/migrations/0001_init.sql. Every query module in
// lib/db/ returns these types, never a raw node:sqlite row (which
// carries SQLOutputValue's null-prototype/bigint quirks).

export type Role = "MEMBER" | "ADMIN";

export interface User {
  id: string;
  email: string;
  password_hash: string;
  role: string;
  display_name: string | null;
  email_verified_at: string | null;
  disabled_at: string | null;
  stripe_customer_id: string | null;
  trial_consumed_at: string | null;
  created_at: string;
  updated_at: string;
  /** Milestone 30: non-null means this user may use the member product
   * while PRIVATE_BETA=true, even without an active subscription. See
   * lib/auth/betaAccess.ts. */
  beta_access_granted_at: string | null;
  beta_access_granted_by: string | null;
}

export interface Session {
  id: string;
  token_hash: string;
  user_id: string;
  user_agent: string | null;
  created_at: string;
  expires_at: string;
}

export interface EmailVerificationToken {
  id: string;
  user_id: string;
  token_hash: string;
  expires_at: string;
  consumed_at: string | null;
  created_at: string;
}

export interface PasswordResetToken {
  id: string;
  user_id: string;
  token_hash: string;
  expires_at: string;
  consumed_at: string | null;
  created_at: string;
}

export type SportStatus = "LIVE" | "COMING_SOON";

export interface Sport {
  code: string;
  name: string;
  status: SportStatus;
  sort_order: number;
}

export type BillingInterval = "WEEKLY" | "MONTHLY";

export interface Plan {
  id: string;
  name: string;
  price_cents: number;
  billing_interval: BillingInterval;
  trial_days: number;
  is_active: number;
  created_at: string;
}

export type SubscriptionStatus = "trialing" | "active" | "past_due" | "canceled" | "expired" | "complimentary";

export type BillingProviderName = "dev" | "stripe";

export interface Subscription {
  id: string;
  user_id: string;
  plan_id: string;
  status: SubscriptionStatus;
  provider: BillingProviderName;
  provider_subscription_id: string | null;
  provider_price_id: string | null;
  trial_ends_at: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  /** 0 or 1 (SQLite has no native boolean) -- true once the user has
   * requested cancellation but access continues through current_period_end. */
  cancel_at_period_end: number;
  /** ISO timestamp of the Stripe event.created that last wrote this row --
   * an out-of-order/stale-webhook-delivery guard, not a display field. */
  last_stripe_event_at: string | null;
  canceled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Entitlement {
  key: string;
  sport_code: string;
  label: string;
}

export interface UserEntitlement {
  id: string;
  user_id: string;
  entitlement_key: string;
  granted_by: string | null;
  reason: string | null;
  created_at: string;
  expires_at: string | null;
}

export type FeatureFlagState = "PRODUCTION" | "BETA" | "ADMIN_ONLY" | "DISABLED";

export interface FeatureFlag {
  key: string;
  sport_code: string;
  label: string;
  state: FeatureFlagState;
  updated_at: string;
  updated_by: string | null;
}

export interface UsageEvent {
  id: string;
  user_id: string | null;
  event_type: string;
  metadata_json: string | null;
  created_at: string;
}

export type StripeWebhookEventStatus = "processing" | "processed" | "failed";

export interface StripeWebhookEvent {
  id: string;
  type: string;
  status: StripeWebhookEventStatus;
  error: string | null;
  received_at: string;
  processed_at: string | null;
}

export interface AdminAuditLogEntry {
  id: string;
  actor_user_id: string | null;
  actor_label: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata_json: string | null;
  created_at: string;
}

// Milestone 29: admin slate publishing lifecycle.
export type SlateLifecycleStatus = "DRAFT" | "PROCESSING" | "READY" | "PUBLISHED" | "PARTIAL" | "ERROR" | "ARCHIVED";

export interface SlateStatusRow {
  id: string;
  slate_date: string;
  slate_id: string;
  slate_label: string | null;
  status: SlateLifecycleStatus;

  pool_path: string | null;
  match_report_path: string | null;
  ownership_path: string | null;
  native_snapshot_path: string | null;
  ai_snapshot_path: string | null;
  vegas_snapshot_path: string | null;
  research_snapshot_path: string | null;
  source_hash: string | null;
  source_provenance: string | null;
  validation_json: string | null;
  // M32.7: the Admin Change Report (lib/slateChangeReport.ts) from the
  // most recent Process/Refresh run, JSON-encoded -- null if no run has
  // completed one since this column was added.
  change_report_json: string | null;
  last_processed_at: string | null;
  last_refreshed_at: string | null;

  published_version: number | null;
  published_at: string | null;
  published_by: string | null;
  published_pool_path: string | null;
  published_match_report_path: string | null;
  published_ownership_path: string | null;
  published_native_snapshot_path: string | null;
  published_ai_snapshot_path: string | null;
  published_vegas_snapshot_path: string | null;
  published_research_snapshot_path: string | null;
  published_source_hash: string | null;

  created_at: string;
  updated_at: string;
}

export type SlatePublishEvent = "PUBLISHED" | "UNPUBLISHED" | "ARCHIVED";

export interface SlatePublishHistoryRow {
  id: string;
  slate_date: string;
  slate_id: string;
  slate_label: string | null;
  data_version: number;
  event: SlatePublishEvent;
  published_at: string;
  published_by: string | null;
  source_hash: string | null;
  pool_path: string | null;
  match_report_path: string | null;
  ownership_path: string | null;
  native_snapshot_path: string | null;
  ai_snapshot_path: string | null;
  vegas_snapshot_path: string | null;
  research_snapshot_path: string | null;
}

/** The pinned artifact paths a member-facing loader should read for a
 * currently-published slate -- see lib/db/slateStatus.ts::getPublishedVersion(). */
export interface PublishedSlateVersion {
  slateDate: string;
  slateId: string;
  dataVersion: number;
  publishedAt: string;
  poolPath: string | null;
  matchReportPath: string | null;
  ownershipPath: string | null;
  nativeSnapshotPath: string | null;
  aiSnapshotPath: string | null;
  vegasSnapshotPath: string | null;
  researchSnapshotPath: string | null;
  sourceHash: string | null;
}

// Milestone 30: background job persistence (lib/jobs/*).
export type JobType = "PROCESS_SLATE" | "REFRESH_SLATE" | "BUILD_LINEUPS" | "RESULTS_COLLECTION" | "MODEL_EVALUATION";
export type JobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELED";

export interface JobRow {
  id: string;
  job_type: JobType;
  slate_date: string | null;
  slate_id: string | null;
  status: JobStatus;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  progress: number;
  current_step: string | null;
  error_code: string | null;
  safe_error_message: string | null;
  worker_id: string | null;
  attempt_count: number;
  max_attempts: number;
  payload_json: string | null;
}

export type WorkerHealthStatus = "ONLINE" | "STALE" | "OFFLINE";

export interface WorkerHeartbeatRow {
  worker_id: string;
  last_seen_at: string;
  status: string;
  metadata_json: string | null;
}

// M1: canonical slate + player identity foundation
// (lib/db/migrations/0009_slate_identity_foundation.sql /
// migrations-postgres/0010_slate_identity_foundation.sql). ADDITIVE
// FOUNDATION ONLY -- no production query module reads/writes these
// tables yet; see canonical/ (Python) for the mirrored dataclasses.

export type ReviewStatus = "AUTO_APPROVED" | "NEEDS_REVIEW" | "REVIEWED_APPROVED" | "REVIEWED_REJECTED";

export interface PlayerRow {
  internal_player_id: string;
  sport: string;
  canonical_name: string;
  normalized_name: string;
  current_team: string | null;
  position: string | null;
  active: number;
  created_at: string;
  updated_at: string;
}

export interface PlayerExternalIdRow {
  id: string;
  internal_player_id: string;
  sport: string;
  provider: string;
  external_id: string;
  external_id_type: string;
  match_method: string;
  match_confidence: number;
  review_status: ReviewStatus;
  is_current: number;
  valid_from: string;
  valid_to: string | null;
  created_at: string;
  updated_at: string;
}

export type SlateValidationState = "PENDING" | "VALID" | "REJECTED";

export interface CanonicalSlateRow {
  internal_slate_id: string;
  sport: string;
  site: string;
  provider: string;
  provider_slate_id: string;
  slate_name: string | null;
  slate_date: string;
  first_game_start_utc: string;
  game_count: number | null;
  game_ids_json: string | null;
  salary_cap: number | null;
  roster_template_json: string | null;
  source_provenance: string;
  validation_state: SlateValidationState;
  validation_findings_json: string | null;
  schema_version: string;
  raw_hash: string | null;
  normalized_hash: string | null;
  fetched_at: string | null;
  // M2H: additive promotion metadata (migrations/0010_canonical_slate_promotion_metadata.sql).
  current_normalized_artifact_path: string | null;
  current_raw_artifact_path: string | null;
  promoted_at: string | null;
  // M3E: shadow ingestion status/observability (migrations/0011_canonical_shadow_status.sql).
  last_attempt_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  consecutive_failures: number;
  last_error_type: string | null;
  last_error_summary: string | null;
  player_count: number | null;
  resolved_identity_count: number | null;
  unresolved_identity_count: number | null;
  review_required_count: number | null;
  is_semantic_duplicate: number | null;
  created_at: string;
  updated_at: string;
}

export type SlatePlayerIdentityStatus = "RESOLVED" | "UNRESOLVED" | "REVIEW_REQUIRED";

export interface CanonicalSlatePlayerRow {
  internal_slate_id: string;
  provider_player_id: string;
  internal_player_id: string | null;
  provider_draftable_ids_json: string | null;
  name: string;
  team: string;
  opponent: string | null;
  game_id: string | null;
  salary: number;
  position_eligibility_json: string | null;
  roster_slot_eligibility_json: string | null;
  identity_status: SlatePlayerIdentityStatus;
  // M6D: additive real-MLB-lineup-eligibility columns (migrations/
  // 0013_canonical_slate_player_eligibility.sql). NULL/null means "not
  // yet computed" -- a distinct, honest state from any real
  // dfs/eligibility.py status; never treated as assumed-eligible.
  eligibility_status: string | null;
  optimizer_eligible: number | null;
  batting_order: number | null;
  eligibility_computed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type IdentityReviewQueueStatus = "PENDING" | "RESOLVED" | "REJECTED";

export interface IdentityReviewQueueRow {
  id: string;
  sport: string;
  provider: string;
  external_id: string;
  provider_player_name: string;
  provider_team: string | null;
  provider_position: string | null;
  candidate_internal_player_id: string | null;
  reason: string;
  status: IdentityReviewQueueStatus;
  resolved_internal_player_id: string | null;
  resolved_by: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}
