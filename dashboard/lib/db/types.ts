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
