-- Milestone 33.1: Postgres has no equivalent of SQLite's implicit
-- `rowid` (a monotonic per-row insertion-order counter every rowid table
-- gets for free). Two tables genuinely depend on it for PRIMARY, not
-- merely tie-breaking, ordering:
--
--   subscriptions        lib/db/subscriptions.ts::getCurrentSubscriptionForUser
--                         and LATEST_ROW_PER_USER_SUBQUERY answer "this
--                         user's current subscription" as "the row with
--                         the highest rowid for this user_id" -- two rows
--                         inserted in the same millisecond (e.g. an admin
--                         cancels then immediately re-subscribes someone)
--                         would otherwise make "most recent" ambiguous
--                         from created_at alone.
--   stripe_webhook_events lib/db/stripeWebhookEvents.ts::listRecentWebhookEvents
--                         and getLastSuccessfulWebhookEvent order by
--                         received_at/processed_at with rowid as the
--                         tiebreaker for the same reason.
--
-- `seq BIGSERIAL` gives Postgres the same guarantee explicitly: a real,
-- indexed, monotonically-increasing insertion-order column. SQLite's own
-- migrations are NOT touched -- SQLite already has rowid natively for
-- both tables (no WITHOUT ROWID table exists in this schema), so no
-- SQLite-side schema change is needed; lib/db/*.ts branches its SQL text
-- per `executor.backend` for these two queries only (see this
-- milestone's compatibility-matrix report for the exact list).

ALTER TABLE subscriptions ADD COLUMN seq BIGSERIAL;
CREATE INDEX idx_subscriptions_seq ON subscriptions(seq);

ALTER TABLE stripe_webhook_events ADD COLUMN seq BIGSERIAL;
CREATE INDEX idx_stripe_webhook_events_seq ON stripe_webhook_events(seq);
