import { getDb } from "./client";
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
 * If it fails (a row already exists):
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
export function claimWebhookEvent(eventId: string, type: string): { shouldProcess: boolean } {
  const db = getDb();
  try {
    db.prepare("INSERT INTO stripe_webhook_events (id, type, status, received_at) VALUES (?, ?, 'processing', ?)").run(
      eventId,
      type,
      nowIso(),
    );
    return { shouldProcess: true };
  } catch {
    const existing = db.prepare("SELECT status FROM stripe_webhook_events WHERE id = ?").get(eventId) as
      | { status: StripeWebhookEventStatus }
      | undefined;
    if (existing?.status === "processed") {
      return { shouldProcess: false };
    }
    db.prepare("UPDATE stripe_webhook_events SET status = 'processing', error = NULL WHERE id = ?").run(eventId);
    return { shouldProcess: true };
  }
}

export function markWebhookEventProcessed(eventId: string): void {
  const db = getDb();
  db.prepare("UPDATE stripe_webhook_events SET status = 'processed', processed_at = ?, error = NULL WHERE id = ?").run(nowIso(), eventId);
}

export function markWebhookEventFailed(eventId: string, error: string): void {
  const db = getDb();
  db.prepare("UPDATE stripe_webhook_events SET status = 'failed', error = ? WHERE id = ?").run(error, eventId);
}

export function listRecentWebhookEvents(limit = 50): StripeWebhookEvent[] {
  const db = getDb();
  const rows = db.prepare("SELECT * FROM stripe_webhook_events ORDER BY received_at DESC, rowid DESC LIMIT ?").all(limit);
  return rows as unknown as StripeWebhookEvent[];
}

export function countWebhookEventsByStatus(): Record<StripeWebhookEventStatus, number> {
  const db = getDb();
  const rows = db.prepare("SELECT status, COUNT(*) as c FROM stripe_webhook_events GROUP BY status").all() as Array<{
    status: StripeWebhookEventStatus;
    c: number;
  }>;
  const result: Record<StripeWebhookEventStatus, number> = { processing: 0, processed: 0, failed: 0 };
  for (const row of rows) result[row.status] = row.c;
  return result;
}

export function getLastSuccessfulWebhookEvent(): StripeWebhookEvent | null {
  const db = getDb();
  const row = db
    .prepare("SELECT * FROM stripe_webhook_events WHERE status = 'processed' ORDER BY processed_at DESC, rowid DESC LIMIT 1")
    .get();
  return mapEvent(row as Record<string, unknown> | undefined);
}
