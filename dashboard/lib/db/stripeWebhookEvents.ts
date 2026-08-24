import { getExecutor } from "./executor";
import type { StripeWebhookEvent, StripeWebhookEventStatus } from "./types";

function nowIso(): string {
  return new Date().toISOString();
}

function mapEvent(row: Record<string, unknown> | undefined): StripeWebhookEvent | null {
  if (!row) return null;
  return row as unknown as StripeWebhookEvent;
}

/** Webhook idempotency, built around a single atomic operation: the
 * Stripe event ID (globally unique, evt_...) is the table's PRIMARY KEY,
 * so "has anyone already claimed this event" is answered by whether an
 * INSERT succeeds or fails -- never by a separate SELECT-then-INSERT
 * (which races under concurrent delivery: Stripe explicitly documents
 * that duplicate webhook deliveries happen).
 *
 * If the INSERT succeeds, THIS call owns processing.
 * If it fails (a row already exists -- a real primary-key violation on
 * both SQLite and Postgres, just with different Error shapes, which is
 * why this only checks "did the INSERT throw," never the error's own
 * message/code):
 *   - status='processed' -> a true duplicate delivery of a fully-handled
 *     event. Return shouldProcess:false; the caller no-ops and returns
 *     200 without touching subscription state twice.
 *   - status='processing' or 'failed' -> either a concurrent in-flight
 *     delivery of the SAME event, or a prior delivery that crashed/threw
 *     before finishing. Re-claim it (flip back to 'processing') and let
 *     this call process it. This is safe even in the rare true-race case
 *     because every webhook handler applies the FULL authoritative state
 *     from the Stripe object (never an incremental delta) -- reprocessing
 *     is idempotent by construction, not just "usually fine." */
export async function claimWebhookEvent(eventId: string, type: string): Promise<{ shouldProcess: boolean }> {
  const db = getExecutor();
  try {
    await db.run("INSERT INTO stripe_webhook_events (id, type, status, received_at) VALUES (?, ?, 'processing', ?)", [
      eventId,
      type,
      nowIso(),
    ]);
    return { shouldProcess: true };
  } catch {
    const existing = await db.get<{ status: StripeWebhookEventStatus }>("SELECT status FROM stripe_webhook_events WHERE id = ?", [
      eventId,
    ]);
    if (existing?.status === "processed") {
      return { shouldProcess: false };
    }
    await db.run("UPDATE stripe_webhook_events SET status = 'processing', error = NULL WHERE id = ?", [eventId]);
    return { shouldProcess: true };
  }
}

export async function markWebhookEventProcessed(eventId: string): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE stripe_webhook_events SET status = 'processed', processed_at = ?, error = NULL WHERE id = ?", [nowIso(), eventId]);
}

export async function markWebhookEventFailed(eventId: string, error: string): Promise<void> {
  const db = getExecutor();
  await db.run("UPDATE stripe_webhook_events SET status = 'failed', error = ? WHERE id = ?", [error, eventId]);
}

/** SQLite has a built-in monotonic `rowid`; Postgres does not, so the
 * 0009 migration added a real `seq BIGSERIAL` column here for the same
 * reason as lib/db/subscriptions.ts -- see that migration's docstring. */
function insertionOrderColumn(backend: "sqlite" | "postgres"): string {
  return backend === "postgres" ? "seq" : "rowid";
}

export async function listRecentWebhookEvents(limit = 50): Promise<StripeWebhookEvent[]> {
  const db = getExecutor();
  const rows = await db.all<Record<string, unknown>>(
    `SELECT * FROM stripe_webhook_events ORDER BY received_at DESC, ${insertionOrderColumn(db.backend)} DESC LIMIT ?`,
    [limit],
  );
  return rows as unknown as StripeWebhookEvent[];
}

export async function countWebhookEventsByStatus(): Promise<Record<StripeWebhookEventStatus, number>> {
  const db = getExecutor();
  const rows = await db.all<{ status: StripeWebhookEventStatus; c: number }>(
    "SELECT status, COUNT(*) as c FROM stripe_webhook_events GROUP BY status",
  );
  const result: Record<StripeWebhookEventStatus, number> = { processing: 0, processed: 0, failed: 0 };
  for (const row of rows) result[row.status] = Number(row.c);
  return result;
}

export async function getLastSuccessfulWebhookEvent(): Promise<StripeWebhookEvent | null> {
  const db = getExecutor();
  const row = await db.get<Record<string, unknown>>(
    `SELECT * FROM stripe_webhook_events WHERE status = 'processed' ORDER BY processed_at DESC, ${insertionOrderColumn(db.backend)} DESC LIMIT 1`,
  );
  return mapEvent(row);
}
