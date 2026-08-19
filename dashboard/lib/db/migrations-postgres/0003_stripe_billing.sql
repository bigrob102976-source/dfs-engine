-- Milestone 30: PostgreSQL dialect port of
-- lib/db/migrations/0003_stripe_billing.sql. The SQLite original had to
-- rebuild the whole subscriptions table (create-new/copy/drop/rename)
-- because SQLite cannot alter a CHECK constraint in place -- Postgres
-- can, so this reaches the identical end schema with plain ALTER TABLE
-- statements instead. Same columns, same indexes, same semantics.

ALTER TABLE subscriptions DROP CONSTRAINT subscriptions_provider_check;
ALTER TABLE subscriptions ADD CONSTRAINT subscriptions_provider_check CHECK (provider IN ('dev','stripe'));

ALTER TABLE subscriptions ADD COLUMN provider_price_id TEXT;
ALTER TABLE subscriptions ADD COLUMN current_period_start TEXT;
ALTER TABLE subscriptions ADD COLUMN cancel_at_period_end INTEGER NOT NULL DEFAULT 0 CHECK (cancel_at_period_end IN (0,1));
ALTER TABLE subscriptions ADD COLUMN last_stripe_event_at TEXT;

CREATE UNIQUE INDEX idx_subscriptions_provider_subscription_id ON subscriptions(provider_subscription_id) WHERE provider_subscription_id IS NOT NULL;

ALTER TABLE users ADD COLUMN stripe_customer_id TEXT;
CREATE UNIQUE INDEX idx_users_stripe_customer_id ON users(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;

ALTER TABLE users ADD COLUMN trial_consumed_at TEXT;

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
