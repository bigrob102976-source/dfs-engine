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
