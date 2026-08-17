-- Milestone 21: membership + admin foundation schema.
--
-- TEXT UUID primary keys (crypto.randomUUID(), generated in application
-- code before INSERT) for every transactional table. Small reference/
-- catalog tables (sports, plans, entitlements, feature_flags) use a
-- stable natural-key TEXT primary key instead ('MLB', 'weekly',
-- 'mlb.optimizer') so seeds and joins stay human-readable.
--
-- Timestamps are ISO-8601 UTC TEXT (matches the existing artifact-JSON
-- convention used throughout the Python pipeline's generated_at_utc
-- fields), not INTEGER unix epoch.
--
-- Session/verification/reset tokens store ONLY a SHA-256 hash of the
-- raw token, never the raw value itself -- the raw value exists only
-- in the httpOnly cookie / the one-time link shown to the user.

PRAGMA foreign_keys = ON;

-- schema_migrations itself is created defensively by lib/db/migrate.ts
-- before this file ever runs (it has to exist to know THIS file hasn't
-- run yet), so it is intentionally not created here too.

CREATE TABLE users (
  id                TEXT PRIMARY KEY,
  email             TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash     TEXT NOT NULL,
  role              TEXT NOT NULL DEFAULT 'MEMBER',
  display_name      TEXT,
  email_verified_at TEXT,
  disabled_at       TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE TABLE sessions (
  id         TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  user_agent TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX idx_sessions_user_id ON sessions(user_id);

CREATE TABLE email_verification_tokens (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  TEXT NOT NULL UNIQUE,
  expires_at  TEXT NOT NULL,
  consumed_at TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_evt_user_id ON email_verification_tokens(user_id);

CREATE TABLE password_reset_tokens (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash  TEXT NOT NULL UNIQUE,
  expires_at  TEXT NOT NULL,
  consumed_at TEXT,
  created_at  TEXT NOT NULL
);
CREATE INDEX idx_prt_user_id ON password_reset_tokens(user_id);

CREATE TABLE sports (
  code       TEXT PRIMARY KEY,
  name       TEXT NOT NULL,
  status     TEXT NOT NULL CHECK (status IN ('LIVE','COMING_SOON')) DEFAULT 'COMING_SOON',
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE plans (
  id               TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  price_cents      INTEGER NOT NULL,
  billing_interval TEXT NOT NULL CHECK (billing_interval IN ('WEEKLY','MONTHLY')),
  trial_days       INTEGER NOT NULL DEFAULT 0,
  is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  created_at       TEXT NOT NULL
);

CREATE TABLE subscriptions (
  id                       TEXT PRIMARY KEY,
  user_id                  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  plan_id                  TEXT NOT NULL REFERENCES plans(id),
  status                   TEXT NOT NULL CHECK (status IN ('trialing','active','past_due','canceled','expired','complimentary')),
  provider                 TEXT NOT NULL DEFAULT 'dev' CHECK (provider IN ('dev')),
  provider_subscription_id TEXT,
  trial_ends_at            TEXT,
  current_period_end       TEXT,
  canceled_at              TEXT,
  created_at               TEXT NOT NULL,
  updated_at                TEXT NOT NULL
);
CREATE INDEX idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

CREATE TABLE entitlements (
  key        TEXT PRIMARY KEY,
  sport_code TEXT NOT NULL REFERENCES sports(code),
  label      TEXT NOT NULL
);

CREATE TABLE user_entitlements (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  entitlement_key TEXT NOT NULL REFERENCES entitlements(key),
  granted_by      TEXT REFERENCES users(id),
  reason          TEXT,
  created_at      TEXT NOT NULL,
  expires_at      TEXT,
  UNIQUE(user_id, entitlement_key)
);
CREATE INDEX idx_user_entitlements_user_id ON user_entitlements(user_id);

CREATE TABLE feature_flags (
  key        TEXT PRIMARY KEY,
  sport_code TEXT NOT NULL REFERENCES sports(code),
  label      TEXT NOT NULL,
  state      TEXT NOT NULL CHECK (state IN ('PRODUCTION','BETA','ADMIN_ONLY','DISABLED')) DEFAULT 'PRODUCTION',
  updated_at TEXT NOT NULL,
  updated_by TEXT REFERENCES users(id)
);

CREATE TABLE usage_events (
  id            TEXT PRIMARY KEY,
  user_id       TEXT REFERENCES users(id) ON DELETE SET NULL,
  event_type    TEXT NOT NULL,
  metadata_json TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_usage_events_user_id ON usage_events(user_id);
CREATE INDEX idx_usage_events_created_at ON usage_events(created_at);
CREATE INDEX idx_usage_events_type ON usage_events(event_type);

CREATE TABLE admin_audit_log (
  id            TEXT PRIMARY KEY,
  actor_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  actor_label   TEXT NOT NULL,
  action        TEXT NOT NULL,
  target_type   TEXT,
  target_id     TEXT,
  metadata_json TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX idx_audit_created_at ON admin_audit_log(created_at);
CREATE INDEX idx_audit_action ON admin_audit_log(action);
CREATE INDEX idx_audit_actor ON admin_audit_log(actor_user_id);
