-- Milestone 22: Stripe billing integration.
--
-- subscriptions.provider had a CHECK (provider IN ('dev')) constraint from
-- Milestone 21 -- SQLite cannot ALTER a CHECK constraint in place, so the
-- table is rebuilt (create-new / copy / drop / rename) to widen it to
-- ('dev','stripe') and add the columns a real Stripe-backed subscription
-- needs: provider_price_id, current_period_start, cancel_at_period_end,
-- and last_stripe_event_at (an out-of-order-webhook-delivery guard -- see
-- lib/billing/webhookHandlers.ts's applyStripeSubscription()). All existing
-- columns/data/indexes are preserved exactly.

CREATE TABLE subscriptions_new (
  id                       TEXT PRIMARY KEY,
  user_id                  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id                  TEXT NOT NULL REFERENCES plans(id),
  status                   TEXT NOT NULL CHECK (status IN ('trialing','active','past_due','canceled','expired','complimentary')),
  provider                 TEXT NOT NULL DEFAULT 'dev' CHECK (provider IN ('dev','stripe')),
  provider_subscription_id TEXT,
  provider_price_id        TEXT,
  trial_ends_at            TEXT,
  current_period_start     TEXT,
  current_period_end       TEXT,
  cancel_at_period_end     INTEGER NOT NULL DEFAULT 0 CHECK (cancel_at_period_end IN (0,1)),
  last_stripe_event_at     TEXT,
  canceled_at              TEXT,
  created_at               TEXT NOT NULL,
  updated_at               TEXT NOT NULL
);

INSERT INTO subscriptions_new (
  id, user_id, plan_id, status, provider, provider_subscription_id,
  trial_ends_at, current_period_end, canceled_at, created_at, updated_at
)
SELECT
  id, user_id, plan_id, status, provider, provider_subscription_id,
  trial_ends_at, current_period_end, canceled_at, created_at, updated_at
FROM subscriptions;

DROP TABLE subscriptions;
ALTER TABLE subscriptions_new RENAME TO subscriptions;

CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
-- Partial unique index: many historical rows will have a NULL
-- provider_subscription_id (every 'dev'-provider row, ever), so the
-- uniqueness constraint only applies once a real Stripe subscription ID
-- is present -- this is the DB-level backstop against ever inserting two
-- local rows for the same Stripe subscription (webhook idempotency is the
-- primary defense; this is defense in depth).
CREATE UNIQUE INDEX idx_subscriptions_provider_subscription_id ON subscriptions(provider_subscription_id) WHERE provider_subscription_id IS NOT NULL;

-- Stripe Customer ID lives on the user, not the subscription: a user's
-- Stripe customer identity is stable for their lifetime even though their
-- individual subscription rows churn (cancel, resubscribe, switch plans).
ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;
CREATE UNIQUE INDEX idx_users_stripe_customer_id ON users(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

-- One-trial policy: set exactly once, the first time Stripe (or the dev
-- provider) confirms a real trial was granted -- never cleared, never
-- reset by canceling/resubscribing/switching plans. See
-- lib/billing/webhookHandlers.ts and lib/billing/devBillingProvider.ts.
ALTER TABLE users ADD COLUMN trial_consumed_at TEXT;

-- Webhook idempotency ledger. The Stripe event ID itself (evt_...) is
-- globally unique and is used directly as the primary key -- claiming an
-- event is a single atomic INSERT (see lib/db/stripeWebhookEvents.ts),
-- not a separate check-then-insert (which would race under concurrent
-- delivery).
CREATE TABLE stripe_webhook_events (
  id           TEXT PRIMARY KEY,
  type         TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('processing','processed','failed')) DEFAULT 'processing',
  error        TEXT,
  received_at  TEXT NOT NULL,
  processed_at TEXT
);
CREATE INDEX idx_stripe_webhook_events_type ON stripe_webhook_events(type);
CREATE INDEX idx_stripe_webhook_events_received_at ON stripe_webhook_events(received_at);
